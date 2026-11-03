import customtkinter as ctk
from tkinter import ttk, messagebox
import sqlite3
import pandas as pd
from datetime import datetime
import os

# Podesavanja izgleda
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
DB_NAME = "magacin.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS delovi (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        part_number TEXT UNIQUE,
                        naziv TEXT,
                        kategorija TEXT,
                        stanje INTEGER,
                        min_stanje INTEGER,
                        max_stanje INTEGER,
                        cena REAL,
                        dobavljac TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS transakcije (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        part_id INTEGER,
                        kolicina INTEGER,
                        tip TEXT,
                        korisnik TEXT,
                        datum DATETIME,
                        napomena TEXT,
                        FOREIGN KEY(part_id) REFERENCES delovi(id))''')
    
    cursor.execute("SELECT COUNT(*) FROM delovi")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO delovi (part_number, naziv, kategorija, stanje, min_stanje, max_stanje, cena, dobavljac) VALUES ('SMT-N01', 'Nozla za selektivno lemljenje', 'Mehanika', 2, 5, 10, 4500, 'Weller')")
        cursor.execute("INSERT INTO delovi (part_number, naziv, kategorija, stanje, min_stanje, max_stanje, cena, dobavljac) VALUES ('VIS-SC30', 'Kamera SC3000X (Vision Senzor)', 'Elektronika', 1, 1, 3, 25000, 'Hikrobot')")
        cursor.execute("INSERT INTO delovi (part_number, naziv, kategorija, stanje, min_stanje, max_stanje, cena, dobavljac) VALUES ('LUB-001', 'Kartuša masti za mazalicu (vođice)', 'Potrošni', 5, 2, 10, 1200, 'Fuchs')")
        conn.commit()
    conn.close()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Evidencija Rezervnih Delova")
        self.geometry("1024x768")
        init_db()
        self.show_login()

    def show_login(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.login_frame = ctk.CTkFrame(self)
        self.login_frame.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(self.login_frame, text="Prijava u sistem", font=("Arial", 24, "bold")).pack(pady=20, padx=40)
        self.entry_user = ctk.CTkEntry(self.login_frame, placeholder_text="Korisničko ime", width=200, font=("Arial", 16))
        self.entry_user.pack(pady=10)
        self.entry_pass = ctk.CTkEntry(self.login_frame, placeholder_text="Lozinka", show="*", width=200, font=("Arial", 16))
        self.entry_pass.pack(pady=10)
        ctk.CTkButton(self.login_frame, text="Prijavi se", font=("Arial", 16), command=self.check_login).pack(pady=20)
        ctk.CTkButton(self.login_frame, text="Uđi kao Gost (Samo pregled)", fg_color="gray", font=("Arial", 14), command=lambda: self.load_main("gost")).pack(pady=10)

    def check_login(self):
        u, p = self.entry_user.get(), self.entry_pass.get()
        if u == "tehnicar" and p == "tehnicar": self.load_main("tehnicar")
        elif u == "admin" and p == "admin": self.load_main("admin")
        else: messagebox.showerror("Greška", "Pogrešno korisničko ime ili lozinka!")

    def load_main(self, role):
        self.role = role
        self.username = "Admin" if role == "admin" else ("Tehničar" if role == "tehnicar" else "Gost")
        for widget in self.winfo_children(): widget.destroy()

        header = ctk.CTkFrame(self, height=50)
        header.pack(fill="x", side="top", pady=5, padx=5)
        ctk.CTkLabel(header, text=f"Prijavljeni ste kao: {self.username}", font=("Arial", 16, "bold")).pack(side="left", padx=20)
        ctk.CTkButton(header, text="Odjavi se", width=100, fg_color="red", command=self.show_login).pack(side="right", padx=20)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_pregled = self.tabview.add("Pregled Stanja")
        self.tab_analitika = self.tabview.add("Analitika")
        if self.role == "admin": self.tab_admin = self.tabview.add("Admin Panel")

        self.setup_pregled_tab()
        self.setup_analitika_tab()
        if self.role == "admin": self.setup_admin_tab()

    def setup_pregled_tab(self):
        toolbar = ctk.CTkFrame(self.tab_pregled)
        toolbar.pack(fill="x", pady=5)
        
        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(toolbar, textvariable=self.search_var, placeholder_text="Pretraga po Part No. ili Nazivu...", width=300)
        search_entry.pack(side="left", padx=10)
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_table())

        if self.role in ["tehnicar", "admin"]:
            ctk.CTkButton(toolbar, text="Uzmi deo (Izlaz)", fg_color="#d35400", command=self.izlaz_dela).pack(side="right", padx=5)
            ctk.CTkButton(toolbar, text="Dodaj na stanje (Ulaz)", fg_color="#27ae60", command=self.ulaz_dela).pack(side="right", padx=5)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2b2b2b", foreground="white", fieldbackground="#2b2b2b", rowheight=40, font=("Arial", 13))
        style.configure("Treeview.Heading", font=("Arial", 14, "bold"))
        style.map('Treeview', background=[('selected', '#1f538d')])

        self.tree = ttk.Treeview(self.tab_pregled, columns=("id", "part", "naziv", "kategorija", "stanje", "min", "max"), show="headings", selectmode="browse")
        headings = {"id": "ID", "part": "Part No", "naziv": "Naziv Dela", "kategorija": "Kategorija", "stanje": "Stanje", "min": "Min", "max": "Max"}
        for col, text in headings.items(): self.tree.heading(col, text=text)
        for col in ["id", "stanje", "min", "max"]: self.tree.column(col, width=60, anchor="center")

        self.tree.tag_configure("red", background="#c0392b", foreground="white")
        self.tree.tag_configure("yellow", background="#f39c12", foreground="white")
        self.tree.tag_configure("green", background="#229954", foreground="white")

        self.tree.pack(fill="both", expand=True, pady=10)
        self.refresh_table()

    def refresh_table(self):
        for row in self.tree.get_children(): self.tree.delete(row)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        search = f"%{self.search_var.get()}%"
        cursor.execute("SELECT id, part_number, naziv, kategorija, stanje, min_stanje, max_stanje FROM delovi WHERE naziv LIKE ? OR part_number LIKE ?", (search, search))
        for row in cursor.fetchall():
            stanje, min_s = row[4], row[5]
            tag = "red" if stanje <= min_s else ("yellow" if stanje <= min_s * 1.5 else "green")
            self.tree.insert("", "end", values=row, tags=(tag,))
        conn.close()

    def izlaz_dela(self):
        selected = self.tree.focus()
        if not selected: return messagebox.showwarning("Upozorenje", "Izaberite deo iz tabele!")
        item = self.tree.item(selected)['values']
        dialog = ctk.CTkInputDialog(text=f"Koliko komada uzimaš?\n(Na stanju: {item[4]})", title="Izlaz dela")
        try:
            kol_str = dialog.get_input()
            if not kol_str: return
            kol = int(kol_str)
            if kol > item[4] or kol <= 0: return messagebox.showerror("Greška", "Neispravna količina!")
            conn = sqlite3.connect(DB_NAME)
            conn.execute("UPDATE delovi SET stanje = stanje - ? WHERE id = ?", (kol, item[0]))
            conn.execute("INSERT INTO transakcije (part_id, kolicina, tip, korisnik, datum) VALUES (?, ?, 'IZLAZ', ?, datetime('now', 'localtime'))", (item[0], kol, self.username))
            conn.commit(); conn.close()
            self.refresh_table()
        except Exception as e: pass

    def ulaz_dela(self):
        selected = self.tree.focus()
        if not selected: return messagebox.showwarning("Upozorenje", "Izaberite deo iz tabele!")
        item = self.tree.item(selected)['values']
        dialog = ctk.CTkInputDialog(text="Koliko komada dodaješ?", title="Ulaz dela")
        try:
            kol_str = dialog.get_input()
            if not kol_str: return
            kol = int(kol_str)
            if kol <= 0: return
            conn = sqlite3.connect(DB_NAME)
            conn.execute("UPDATE delovi SET stanje = stanje + ? WHERE id = ?", (kol, item[0]))
            conn.execute("INSERT INTO transakcije (part_id, kolicina, tip, korisnik, datum) VALUES (?, ?, 'ULAZ', ?, datetime('now', 'localtime'))", (item[0], kol, self.username))
            conn.commit(); conn.close()
            self.refresh_table()
        except Exception as e: pass

    def setup_analitika_tab(self):
        self.txt_analitika = ctk.CTkTextbox(self.tab_analitika, width=800, height=400, font=("Arial", 16))
        self.txt_analitika.pack(pady=10)
        ctk.CTkButton(self.tab_analitika, text="Osveži Analitiku", command=self.osvezi_analitiku).pack()
        self.osvezi_analitiku()

    def osvezi_analitiku(self):
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT d.naziv, SUM(t.kolicina) as ukupno FROM transakcije t JOIN delovi d ON t.part_id = d.id WHERE t.tip = 'IZLAZ' GROUP BY d.id ORDER BY ukupno DESC LIMIT 10", conn)
        conn.close()
        self.txt_analitika.delete("0.0", "end")
        self.txt_analitika.insert("end", "Top 10 najviše potrošenih delova:\n\n")
        if df.empty:
            self.txt_analitika.insert("end", "Nema podataka o potrošnji.")
        else:
            for i, row in df.iterrows(): self.txt_analitika.insert("end", f"{i+1}. {row['naziv']} - Potrošeno: {row['ukupno']} kom\n")

    def setup_admin_tab(self):
        btn_add = ctk.CTkButton(self.tab_admin, text="Dodaj novi deo u bazu", font=("Arial", 16), command=self.dodaj_novi_deo)
        btn_add.pack(pady=20)
        btn_exp = ctk.CTkButton(self.tab_admin, text="Eksportuj Listu za Nabavku (Excel)", fg_color="green", font=("Arial", 16), command=self.eksportuj_nabavku)
        btn_exp.pack(pady=20)

    def dodaj_novi_deo(self):
        win = ctk.CTkToplevel(self)
        win.title("Novi deo")
        win.geometry("400x550")
        entries = {}
        for f in ["Part Number", "Naziv", "Kategorija", "Min Stanje", "Max Stanje", "Cena", "Dobavljač"]:
            ctk.CTkLabel(win, text=f, font=("Arial", 14)).pack(pady=2)
            e = ctk.CTkEntry(win, width=250, font=("Arial", 14)); e.pack(pady=5); entries[f] = e
        def sacuvaj():
            try:
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO delovi (part_number, naziv, kategorija, stanje, min_stanje, max_stanje, cena, dobavljac) VALUES (?, ?, ?, 0, ?, ?, ?, ?)",
                             (entries["Part Number"].get(), entries["Naziv"].get(), entries["Kategorija"].get(), int(entries["Min Stanje"].get()), int(entries["Max Stanje"].get()), float(entries["Cena"].get()), entries["Dobavljač"].get()))
                conn.commit(); conn.close()
                self.refresh_table(); win.destroy()
                messagebox.showinfo("Uspeh", "Deo uspešno dodat u bazu!")
            except Exception as e: messagebox.showerror("Greška", "Proverite da li ste uneli ispravne brojeve. (Part Number mora biti jedinstven)\n" + str(e))
        ctk.CTkButton(win, text="Sačuvaj Deo", fg_color="green", font=("Arial", 16), command=sacuvaj).pack(pady=20)

    def eksportuj_nabavku(self):
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT part_number as 'Part No', naziv as 'Naziv', stanje as 'Trenutno Stanje', min_stanje as 'Minimum', dobavljac as 'Dobavljač' FROM delovi WHERE stanje <= min_stanje", conn)
        conn.close()
        if df.empty: return messagebox.showinfo("Info", "Nema delova ispod minimuma! Magacin je pun.")
        filename = f"Nabavka_Lista_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        df.to_excel(filename, index=False)
        messagebox.showinfo("Uspeh", f"Lista uspešno generisana!\nFajl je sačuvan kao: {filename}\n(Nalazi se u istom folderu gde je i aplikacija)")

if __name__ == "__main__":
    app = App()
    app.mainloop()
