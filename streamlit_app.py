import csv
import io
import logging
from datetime import date
from decimal import Decimal

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from magacin_backend.db import engine_for, identity
from magacin_backend.service import Warehouse, BusinessError, PERIODS, now, LOCAL_TZ, uid

st.set_page_config(page_title='Magacin — centralna evidencija', layout='wide')
log = logging.getLogger('magacin')


@st.cache_resource
def backend():
    engine = engine_for()
    with engine.connect() as c:
        version = c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if version != '001':
            raise RuntimeError('Verzija baze nije odgovarajuća. Pokrenite migracije.')
    return Warehouse(engine)


def request_id(key):
    return st.session_state.setdefault('request_' + key, uid())


def perform(key, callback, message='Promena je sačuvana u zajedničkoj bazi.', after=None):
    try:
        result = callback(request_id(key))
    except BusinessError as exc:
        st.error(str(exc))
        return
    except SQLAlchemyError:
        # Do not expose connection URLs, SQL parameters, or credentials to browsers/logs.
        log.error('Database operation failed: %s', key)
        st.error('Veza sa bazom nije uspela. Pokušajte ponovo; isti zahtev neće biti dupliran.')
        return
    st.session_state['request_' + key] = uid()
    st.session_state['flash'] = message
    if after:
        after(result)
    st.rerun()


def csv_bytes(rows):
    if not rows:
        return b''
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), delimiter=';')
    writer.writeheader()
    for row in rows:
        # Avoid spreadsheet formulas in user-supplied names/notes on CSV export.
        clean = {k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v)
                 for k, v in row.items()}
        writer.writerow(clean)
    return output.getvalue().encode('utf-8-sig')


def table(rows, key, export=True):
    if not rows:
        st.info('Nema zapisa.')
        return
    st.dataframe(rows, hide_index=True, width='stretch')
    if export:
        st.download_button('Preuzmi CSV', csv_bytes(rows), file_name=f'{key}_{date.today()}.csv',
                           mime='text/csv', key='download_' + key)


def select_record(label, rows, labeler, key, optional=False, initial_id=None):
    by_id = {r['id']: r for r in rows}
    options = ([None] if optional else []) + list(by_id)
    if not options:
        st.info(f'{label}: nema dostupnih stavki.')
        return None
    rid = st.selectbox(label, options, index=options.index(initial_id) if initial_id in options else 0,
        format_func=lambda i: 'Novi zapis' if i is None else labeler(by_id[i]), key=key)
    return by_id.get(rid)


def password_page(svc, token):
    st.subheader('Promena lozinke')
    with st.form('password', clear_on_submit=True):
        old = st.text_input('Trenutna lozinka', type='password')
        new = st.text_input('Nova lozinka (najmanje 12 znakova)', type='password')
        confirm = st.text_input('Ponovite novu lozinku', type='password')
        submit = st.form_submit_button('Sačuvaj novu lozinku')
    if submit:
        if new != confirm:
            st.error('Lozinke se ne podudaraju.')
        else:
            try:
                svc.change_password(token, old, new)
                st.session_state.clear()
                st.session_state['flash'] = 'Lozinka je promenjena. Prijavite se ponovo.'
                st.rerun()
            except BusinessError as exc:
                st.error(str(exc))


def inventory_page(svc, token, actor):
    st.header('Zalihe')
    rows = svc.list_parts(token, include_inactive=actor['role'] == 'admin')
    search = st.text_input('Pretraga po šifri, nazivu ili kategoriji').casefold()
    only_low = st.checkbox('Samo delovi na minimumu ili ispod minimuma')
    display = [r for r in rows if search in f'{r["part_number"]} {r["name"]} {r["category"]}'.casefold()
               and (not only_low or (r['active'] and r['stock'] <= r['minimum']))]
    table(display, 'zalihe')
    if actor['role'] != 'admin':
        return
    with st.expander('Novi deo / izmena dela'):
        chosen = select_record('Deo za izmenu', rows, lambda r: f'{r["part_number"]} — {r["name"]}', 'edit_part', True)
        base = chosen or {}
        form_key = 'part_' + str(base.get('id', 'new'))
        with st.form(form_key):
            pn = st.text_input('Part number', base.get('part_number', ''), max_chars=150)
            name = st.text_input('Naziv', base.get('name', ''))
            category = st.text_input('Kategorija', base.get('category', ''))
            minimum = st.number_input('Minimalna zaliha', min_value=0, value=base.get('minimum', 0), step=1)
            price = st.number_input('Referentna cena (RSD)', min_value=0.0, value=float(base.get('price', 0)), step=0.01)
            supplier = st.text_input('Dobavljač', base.get('supplier', ''))
            active = st.checkbox('Aktivan', value=base.get('active', True))
            submit = st.form_submit_button('Sačuvaj deo')
        if submit:
            perform(form_key, lambda rid: svc.save_part(token, rid, pn, name, category, minimum, price,
                    supplier, part_id=base.get('id'), active=active))


def receipts_page(svc, token):
    st.header('Ulaz i povrat')
    rows = svc.list_parts(token)
    part = select_record('Deo', rows, lambda r: f'{r["part_number"]} — {r["name"]} (stanje {r["stock"]})', 'receive_part')
    if not part:
        return
    kind = st.radio('Operacija', ['Nabavka / ulaz', 'Povrat'], horizontal=True)
    key = 'receive_' + part['id'] + kind
    with st.form(key):
        qty = st.number_input('Količina', min_value=1, step=1)
        price = st.number_input('Stvarna nabavna cena po komadu (RSD)', min_value=0.0, value=float(part['price']), step=0.01)
        supplier = st.text_input('Dobavljač', part['supplier'])
        note = st.text_area('Napomena / razlog povrata')
        submit = st.form_submit_button('Upiši u zajedničku bazu')
    if submit:
        if kind == 'Povrat':
            perform(key, lambda rid: svc.return_stock(token, rid, part['id'], qty, note))
        else:
            perform(key, lambda rid: svc.receive(token, rid, part['id'], qty, price, supplier, note))


def orders_page(svc, token, actor):
    st.header('Izdavanje i radni nalozi')
    parts = svc.list_parts(token)
    names = {r['id']: f'{r["part_number"]} — {r["name"]}' for r in parts}
    cart = st.session_state.setdefault('cart', [])
    part = select_record('Deo za izdavanje', parts,
        lambda r: f'{r["part_number"]} — {r["name"]} (stanje {r["stock"]})', 'issue_part')
    if part:
        with st.form('cart_add', clear_on_submit=True):
            qty = st.number_input('Količina za nalog', min_value=1, step=1)
            add = st.form_submit_button('Dodaj na nalog')
        if add:
            cart.append({'part_id': part['id'], 'quantity': qty})
            st.rerun()
    if cart:
        st.subheader('Stavke naloga')
        st.dataframe([{'Deo': names.get(r['part_id'], r['part_id']), 'Količina': r['quantity']} for r in cart], hide_index=True)
        if st.button('Isprazni stavke'):
            st.session_state['cart'] = []
            st.rerun()
        with st.form('issue_order'):
            note = st.text_area('Napomena naloga')
            issue = st.form_submit_button('Potvrdi izdavanje')
        if issue:
            perform('issue_order', lambda rid: svc.issue_order(token, rid, cart, note),
                    after=lambda result: st.session_state.update(cart=[]))
    st.subheader('Svi radni nalozi')
    orders = svc.read_table(token, 'orders')
    table(orders, 'nalozi')
    selected = select_record('Pregled / obrada naloga', orders, lambda r: f'{r["number"]} — {r["status"]}', 'order_action')
    if selected:
        items = [r for r in svc.read_table(token, 'order_items') if r['order_id'] == selected['id']]
        table([{**r, 'part': names.get(r['part_id'], r['part_id'])} for r in items], 'stavke_naloga')
        history = [r for r in svc.read_table(token, 'history') if r['order_id'] == selected['id']]
        table([{**r, 'part': names.get(r['part_id'], r['part_id'])} for r in history], 'promene_naloga')
    if selected and actor['role'] == 'admin' and selected['status'] == 'Otvoren':
        with st.form('order_action_form'):
            action = st.radio('Akcija', ['Zatvori', 'Storniraj i vrati robu'])
            reason = st.text_input('Razlog storna')
            confirm = st.checkbox('Potvrđujem izabranu operaciju')
            submit = st.form_submit_button('Obradi nalog')
        if submit and confirm:
            perform('order_action', lambda rid: svc.order_action(token, rid, selected['id'],
                    'close' if action == 'Zatvori' else 'cancel', reason))


def budget_page(svc, token, actor):
    st.header('Budžet i nabavke')
    year = st.number_input('Godina budžeta', min_value=2000, max_value=2200,
                           value=now().astimezone(LOCAL_TZ).year, step=1)
    table(svc.budget_report(token, year), 'budzet')
    if actor['role'] == 'admin':
        with st.form('budget_form'):
            category = st.text_input('Kategorija budžeta')
            approved = st.number_input('Odobreno (RSD)', min_value=0.0, step=1000.0)
            submit = st.form_submit_button('Sačuvaj budžet za izabranu godinu')
        if submit:
            perform('budget', lambda rid: svc.save_budget(token, rid, year, category, approved))
    st.subheader('Nabavke za izabranu godinu')
    purchases = [r for r in svc.read_table(token, 'purchases') if r['created_at'].astimezone(LOCAL_TZ).year == year]
    table(purchases, 'nabavke')
    if actor['role'] == 'admin':
        chosen = select_record('Nabavka za storno', [r for r in purchases if not r['cancelled']],
            lambda r: f'{r["item_name"]} — {r["quantity"]} kom — {r["created_at"]:%Y-%m-%d %H:%M}', 'purchase_cancel')
        if chosen:
            with st.form('cancel_purchase'):
                reason = st.text_input('Razlog storna nabavke')
                confirm = st.checkbox('Potvrđujem storno nabavke i umanjenje zalihe')
                submit = st.form_submit_button('Storniraj nabavku')
            if submit and confirm:
                perform('cancel_purchase', lambda rid: svc.cancel_purchase(token, rid, chosen['id'], reason))


def maintenance_page(svc, token, actor):
    st.header('Preventivno održavanje')
    report = svc.maintenance_report(token)
    table(report, 'pm_izvestaj')
    task = select_record('Zadatak za evidenciju', report,
        lambda r: f'{r["line"]} / {r["machine"]} — {r["description"]}', 'complete_task')
    if task:
        with st.form('complete_task_form'):
            note = st.text_area('Napomena o izvršenju')
            confirm = st.checkbox('Potvrđujem da je zadatak izvršen danas')
            submit = st.form_submit_button('Evidentiraj izvršenje')
        if submit and confirm:
            perform('complete_task', lambda rid: svc.complete_task(token, rid, task['id'], note))
    if actor['role'] != 'admin':
        return
    with st.expander('Podešavanje linija, mašina i zadataka'):
        kind_label = st.selectbox('Vrsta stavke', ['Linija', 'Mašina', 'Zadatak'])
        kind = {'Linija': 'line', 'Mašina': 'machine', 'Zadatak': 'task'}[kind_label]
        rows = svc.read_table(token, {'line': 'lines', 'machine': 'machines', 'task': 'tasks'}[kind])
        chosen = select_record('Izmena ili novi zapis', rows,
            lambda r: r.get('name', r.get('description', '')), 'pm_edit_' + kind, True)
        parent = None
        if kind != 'line':
            parents = svc.read_table(token, 'lines' if kind == 'machine' else 'machines')
            parent = select_record('Nadređena linija' if kind == 'machine' else 'Nadređena mašina', parents,
                lambda r: r['name'], 'pm_parent_' + kind + str((chosen or {}).get('id', 'new')),
                initial_id=(chosen or {}).get('line_id' if kind == 'machine' else 'machine_id'))
        base = chosen or {}
        key = 'pm_' + kind + str(base.get('id', 'new'))
        with st.form(key):
            name = st.text_input('Naziv / opis', base.get('name', base.get('description', '')))
            period = st.selectbox('Periodika', PERIODS, index=PERIODS.index(base.get('period', PERIODS[0]))) if kind == 'task' else None
            active = st.checkbox('Aktivna stavka', value=base.get('active', True))
            submit = st.form_submit_button('Sačuvaj PM stavku')
        if submit:
            perform(key, lambda rid: svc.save_maintenance(token, rid, kind, name,
                parent_id=parent['id'] if parent else None, period=period, entity_id=base.get('id'), active=active))
        with st.form('pm_start'):
            start = st.date_input('Početni rok za zadatke bez evidencije')
            submit = st.form_submit_button('Sačuvaj početni datum')
        if submit:
            perform('pm_start', lambda rid: svc.set_pm_start(token, rid, start))
    with st.expander('Istorija održavanja / poništavanje evidencije'):
        logs = svc.read_table(token, 'maintenance')
        table(logs, 'pm_istorija')
        chosen = select_record('Evidencija za poništavanje', [r for r in logs if not r['voided']],
            lambda r: f'{r["task_id"]} — {r["created_at"]} — {r["actor"]}', 'void_pm')
        if chosen:
            with st.form('void_pm_form'):
                reason = st.text_input('Razlog poništavanja evidencije')
                submit = st.form_submit_button('Poništi evidenciju uz očuvanje istorije')
            if submit:
                perform('void_pm', lambda rid: svc.void_maintenance(token, rid, chosen['id'], reason))


def admin_page(svc, token):
    st.header('Administracija')
    st.caption('Zajednička baza: ' + identity(svc.engine))
    table(svc.read_table(token, 'users'), 'korisnici')
    with st.form('user_form', clear_on_submit=True):
        username = st.text_input('Korisničko ime (postojeće ime = reset pristupa)')
        password = st.text_input('Privremena lozinka, najmanje 12 znakova', type='password')
        role = st.selectbox('Uloga', ['tehnicar', 'admin'])
        active = st.checkbox('Pristup omogućen', value=True)
        submit = st.form_submit_button('Sačuvaj korisnika')
    if submit:
        perform('user', lambda rid: svc.save_user(token, rid, username, password, role, active))
    with st.expander('Revizijski trag'):
        table(svc.read_table(token, 'audit'), 'audit')
    with st.expander('Arhiva prenetih podataka (uključuje stare kvarove, rezervacije i komplete)'):
        table(svc.read_table(token, 'archive'), 'legacy_arhiva')


def main():
    try:
        svc = backend()
    except Exception as exc:
        st.error(f'Greška pri povezivanju sa bazom: {exc}')
        st.info('Proverite DATABASE_URL u Secrets podešavanjima.')
        return
    if flash := st.session_state.pop('flash', None):
        st.success(flash)
    token = st.session_state.get('token')
    if not token:
        st.title('Magacin — prijava')
        with st.form('login', clear_on_submit=True):
            username = st.text_input('Korisničko ime', max_chars=100)
            password = st.text_input('Lozinka', type='password')
            submit = st.form_submit_button('Prijavi se')
        if submit:
            try:
                st.session_state['token'] = svc.login(username, password)
                st.rerun()
            except BusinessError as exc:
                st.error(str(exc))
        return
    try:
        actor = svc.actor(token)
    except BusinessError:
        st.session_state.clear()
        st.rerun()
    st.sidebar.title('Centralni magacin')
    st.sidebar.write(f'{actor["username"]} · {actor["role"]}')
    if st.sidebar.button('Odjavi se'):
        svc.logout(token)
        st.session_state.clear()
        st.rerun()
    if actor['must_change']:
        st.warning('Pre korišćenja aplikacije promenite privremenu lozinku.')
        password_page(svc, token)
        return
    pages = ['Zalihe', 'Ulaz i povrat', 'Izdavanje / nalozi', 'Budžet', 'Preventivno održavanje', 'Istorija', 'Moj nalog']
    if actor['role'] == 'admin':
        pages.append('Administracija')
    page = st.sidebar.radio('Pregledi', pages)
    if st.sidebar.button('Osveži podatke iz baze'):
        st.rerun()
    st.sidebar.caption('Podaci se čitaju iz zajedničke baze. Sesija traje najviše 8 sati.')
    if page == 'Zalihe':
        inventory_page(svc, token, actor)
    elif page == 'Ulaz i povrat':
        receipts_page(svc, token)
    elif page == 'Izdavanje / nalozi':
        orders_page(svc, token, actor)
    elif page == 'Budžet':
        budget_page(svc, token, actor)
    elif page == 'Preventivno održavanje':
        maintenance_page(svc, token, actor)
    elif page == 'Istorija':
        table(svc.read_table(token, 'history'), 'istorija')
    elif page == 'Administracija':
        admin_page(svc, token)
    else:
        password_page(svc, token)


try:
    main()
except BusinessError as exc:
    st.error(str(exc))
except SQLAlchemyError:
    log.error('Database read failed')
    st.error('Baza trenutno nije dostupna. Pokušajte ponovo ili se obratite administratoru.')
