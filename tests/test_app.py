import streamlit as st
from streamlit.testing.v1 import AppTest

from magacin_backend.db import ROOT
from magacin_backend.service import uid


def field(elements, label):
    return next(e for e in elements if e.label == label)


def open_app(monkeypatch, svc):
    monkeypatch.setenv('DATABASE_URL', svc.engine.url.render_as_string(hide_password=False))
    st.cache_resource.clear()
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=20).run()
    field(app.text_input, 'Korisničko ime').set_value('admin')
    field(app.text_input, 'Lozinka').set_value('test-admin-password-2026')
    field(app.button, 'Prijavi se').click().run()
    assert not app.exception
    return app


def test_forms_write_and_second_session_reads(monkeypatch, warehouse):
    svc, token = warehouse
    app = open_app(monkeypatch, svc)
    field(app.text_input, 'Part number').set_value('UI-001')
    field(app.text_input, 'Naziv').set_value('Deo unet preko forme')
    field(app.text_input, 'Kategorija').set_value('Mehanika')
    field(app.number_input, 'Referentna cena (RSD)').set_value(2.50)
    field(app.button, 'Sačuvaj deo').click().run()
    assert not app.exception
    assert not app.error
    pid = svc.list_parts(token)[0]['id']
    app.sidebar.radio[0].set_value('Ulaz i povrat').run()
    field(app.number_input, 'Količina').set_value(5)
    field(app.button, 'Upiši u zajedničku bazu').click().run()
    assert not app.exception
    assert not app.error
    assert svc.list_parts(token)[0]['stock'] == 5
    app.sidebar.radio[0].set_value('Izdavanje / nalozi').run()
    field(app.number_input, 'Količina za nalog').set_value(2)
    field(app.button, 'Dodaj na nalog').click().run()
    field(app.button, 'Potvrdi izdavanje').click().run()
    assert not app.exception
    assert not app.error
    assert svc.list_parts(token)[0]['stock'] == 3
    second = open_app(monkeypatch, svc)
    assert second.dataframe[0].value.iloc[0]['stock'] == 3
    assert second.dataframe[0].value.iloc[0]['part_number'] == 'UI-001'


def test_all_pages_and_pm_form(monkeypatch, warehouse):
    svc, token = warehouse
    line = svc.save_maintenance(token, uid(), 'line', 'Linija')['id']
    machine = svc.save_maintenance(token, uid(), 'machine', 'Mašina', parent_id=line)['id']
    svc.save_maintenance(token, uid(), 'task', 'Provera senzora', parent_id=machine, period='Dnevno')
    app = open_app(monkeypatch, svc)
    for page in ['Ulaz i povrat', 'Izdavanje / nalozi', 'Budžet', 'Preventivno održavanje',
                 'Istorija', 'Moj nalog', 'Administracija']:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page
        assert not app.error, page
    app.sidebar.radio[0].set_value('Preventivno održavanje').run()
    field(app.checkbox, 'Potvrđujem da je zadatak izvršen danas').set_value(True)
    field(app.button, 'Evidentiraj izvršenje').click().run()
    assert not app.exception
    assert not app.error
    assert svc.maintenance_report(token)[0]['last_done'] is not None

