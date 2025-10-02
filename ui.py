import hashlib
import pickle
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from tkinter.ttk import Style

from tinydb import Query, where

from blockchain import Blockchain
from db import TinyDBPersisted, TBL_IDENTS, KEY_PRIV_KEY, KEY_SIG, KEY_TS, TBL_SETTINGS, KEY_CUR_KEY
from security import CryptKeeper

DB_PATH = Path.home().joinpath('.databox', 'request-chain', 'db.json')
DB_PATH.parent.mkdir(exist_ok=True, parents=True)


class IdentModalFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bd=2, relief='flat', **kwargs)
        self.txt_passwd = None
        self.txt_ident = None
        self.close_btn = None
        self.place(relx=0, rely=0, relwidth=1, relheight=1)

        # disable all other window interactions
        self.bind('<Button-1>', lambda e: 'break')

        # optionally grab focus for modal behavior
        self.grab_set()
        self.focus_set()

        self.rowconfigure(0, weight=0)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self.var_ident = tk.StringVar()
        self.var_passwd = tk.StringVar()

        # build the form
        self.build()

    def build(self):
        lbl_ident = ttk.Label(self, text='Identity')
        lbl_ident.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        self.txt_ident = ttk.Entry(self, textvariable=self.var_ident)
        self.txt_ident.grid(row=0, column=1, sticky='ew', padx=5, pady=5)
        self.txt_ident.bind('<KeyRelease>', self.on_key_release)

        lbl_passwd = ttk.Label(self, text='Passphrase')
        lbl_passwd.grid(row=1, column=0, sticky='ew', padx=5, pady=5)
        self.txt_passwd = ttk.Entry(self, textvariable=self.var_passwd)
        self.txt_passwd.grid(row=1, column=1, sticky='ew', padx=5, pady=5)
        self.txt_passwd.bind('<KeyRelease>', self.on_key_release)

        self.close_btn = ttk.Button(self, text='Generate', state='disabled', command=lambda: self.proc_gen())
        self.close_btn.grid(row=2, column=0, columnspan=2, sticky='ew', padx=5, pady=5)

    def on_key_release(self, evt):
        # print(f"{evt.keysym}: {self.var_ident.get()}, {self.var_passwd.get()}")
        ident = self.var_ident.get().strip()
        passwd = self.var_passwd.get().strip()
        is_ok = len(ident) >= 3 and len(passwd) >= 8
        st = 'disabled' if not is_ok else 'normal'
        self.close_btn.config(state=st)

    def proc_gen(self):
        ident = self.var_ident.get().strip()
        passwd = self.var_passwd.get().strip()
        self.var_passwd.set("")

        keep = CryptKeeper()
        priv_key_b = keep.export_private_key(passwd.encode('utf-8'))
        del passwd

        db = TinyDBPersisted.db()
        tbl = db.table(TBL_IDENTS)
        tbl.insert({
            KEY_PRIV_KEY: priv_key_b.decode('utf-8'),
            KEY_SIG: hashlib.sha256(priv_key_b).hexdigest(),
            KEY_TS: time.time()
        })

        self.destroy()


class KeysTreeview(ttk.Treeview):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, columns=(KEY_TS, KEY_SIG), show='headings')

        self.heading(KEY_TS, text='Created')
        self.heading(KEY_SIG, text='Signature')

        self.column(KEY_TS, width=80)
        self.column(KEY_SIG, width=300)

        self.popup_menu = tk.Menu(self, tearoff=0)
        self.popup_menu.add_command(label='Delete', command=self.delete_proc)

        KeysTreeview.populate(self)

        self.bind('<Button-3>', self.do_popup)

    def delete_proc(self):
        sel = self.selection()
        if not sel:
            pass

        for row_id in sel:
            vals = self.item(row_id, 'values')
            sig = vals[1].strip()
            # query db for this signature
            db = TinyDBPersisted.db()
            tbl = db.table(TBL_IDENTS)
            tbl.remove(Query().signature == sig)

        KeysTreeview.populate(self)

    def do_popup(self, evt):
        row_id = self.identify_row(evt.y)
        if row_id:
            if row_id not in self.selection():
                self.selection_set(row_id)

            self.popup_menu.tk_popup(evt.x_root, evt.y_root)

    @staticmethod
    def populate(tbl: ttk.Treeview):
        db = TinyDBPersisted.db()
        _tbl = db.table(TBL_IDENTS)
        recs = _tbl.all()

        [tbl.delete(i) for i in tbl.get_children()]

        for rec in recs:
            sig = rec.get(KEY_SIG, '')
            ts = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(float(rec.get(KEY_TS, '0.0'))))
            tbl.insert('', 'end', values=(ts, sig))


class KeysFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.cur_key_lbl = None
        self.gen_key_btn = None
        self.keys_tbl = None
        self.cur_key_var = tk.StringVar()

        # print current key to UI
        self.show_cur_key()

        self.build()

    def show_cur_key(self):
        db = TinyDBPersisted.db()
        tbl = db.table(TBL_SETTINGS)
        res = tbl.get(where(KEY_CUR_KEY).exists())
        self.cur_key_var.set(res[KEY_CUR_KEY].strip())

    def build(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.keys_tbl = KeysTreeview(self)
        self.keys_tbl.grid(row=0, column=0, sticky='nsew')

        scroller = ttk.Scrollbar(self, orient='vertical', command=self.keys_tbl.yview)
        self.keys_tbl.configure(yscrollcommand=scroller.set)
        scroller.grid(row=0, column=1, sticky='ns')

        self.keys_tbl.bind('<Double-1>', self.do_double_click)

        self.gen_key_btn = ttk.Button(self, text='Generate Identity', command=lambda: IdentModalFrame(self))
        self.gen_key_btn.grid(row=1, column=0, sticky='ew', columnspan=2)

        details_frame = ttk.Frame(self)
        details_frame.grid(row=2, column=0, sticky='nsew', columnspan=2)

        ttk.Label(details_frame, text='Key in use: ').grid(row=0, column=0, sticky='ew')
        self.cur_key_lbl = ttk.Label(details_frame, textvariable=self.cur_key_var)
        self.cur_key_lbl.grid(row=0, column=1, sticky='ew')

    def do_double_click(self, evt):
        iid = self.keys_tbl.identify_row(evt.y)

        if iid:
            vals = self.keys_tbl.item(iid, 'values')
            sig = vals[1].strip()
            # upsert a signature to config table
            db = TinyDBPersisted.db()
            tbl = db.table(TBL_SETTINGS)
            tbl.upsert({KEY_CUR_KEY: sig}, where(KEY_CUR_KEY).exists())

            self.cur_key_var.set(sig)


def tk_recurse_components(parent: tk.Widget):
    childs = parent.winfo_children()
    a = list(childs)

    for child in childs:
        a.extend(tk_recurse_components(child))

    return a


def tk_recurse_find(parent, obj_type):
    matches = []

    for c in parent.winfo_children():
        if isinstance(c, obj_type):
            matches.append(c)
        matches.extend(tk_recurse_find(c, obj_type))

    return matches


class ChainFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.build()

    def build(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)


class RequestChainWin(tk.Tk):
    def __init__(self, snapshot: Path):
        super().__init__()
        self.blockchain = None
        self.snapshot = snapshot
        self.tab3 = None
        self.tab2 = None
        self.tab1 = None
        self.main_panel: ttk.Notebook = None

        self.title("Request Chain v0.0.1")
        self.geometry("800x600")
        self.center_win()

        self.init_chain()

        self.protocol('WM_DELETE_WINDOW', lambda: self.on_close())

        self.build()

    def init_chain(self):
        if self.snapshot.exists():
            with open(self.snapshot, 'rb') as fh:
                self.blockchain = pickle.load(fh)
        else:
            self.blockchain = Blockchain()

        # print(self.blockchain.__str__())

    def center_win(self):
        self.update_idletasks()
        w = 640
        h = 480
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w // 2) - (w // 2)
        y = (screen_h // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.resizable(False, False)
        self.minsize(w, h)

    def build(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.main_panel = ttk.Notebook(self)
        self.main_panel.grid(row=0, column=0, sticky='nsew')
        self.main_panel.bind('<<NotebookTabChanged>>', self.tab_changed)

        # each tab should fill its parent and allow its children to expand
        self.tab1 = ChainFrame(self.main_panel)
        self.tab2 = ttk.Frame(self.main_panel)
        self.tab3 = KeysFrame(self.main_panel)

        for tab in [self.tab1, self.tab2, self.tab3]:
            tab.rowconfigure(0, weight=0)
            tab.columnconfigure(0, weight=1)

        self.main_panel.add(self.tab1, text='Request Chain')
        self.main_panel.add(self.tab2, text='Tab 2')
        self.main_panel.add(self.tab3, text='Key Management')

        # add a label to each tab for demo
        ttk.Label(self.tab2, text='This is tab two').grid(row=0, column=0, sticky='nsew')

    def tab_changed(self, evt):
        i = self.main_panel.select()
        sel = self.main_panel.index(i)

        if sel == 2:  # key management
            key_tbl = tk_recurse_find(self.main_panel, KeysTreeview)
            KeysTreeview.populate(key_tbl[0])

    def on_close(self):
        self.destroy()


def test_keys():
    crypt = CryptKeeper()
    db = TinyDBPersisted.db()
    tbl = db.table(TBL_IDENTS)

    for _ in range(31):
        priv_key = crypt.export_private_key(b'ehc121212')
        sig = hashlib.sha256(priv_key)

        tbl.insert({
            KEY_PRIV_KEY: priv_key.decode(),
            KEY_SIG: sig.hexdigest(),
            KEY_TS: time.time()
        })


def test_db():
    db = TinyDBPersisted.db()
    [print(tbl) for tbl in db.tables()]


def main():
    # blockchain path
    snap_path = Path.home().joinpath('.databox', 'material', 'blx.pkl')
    # open database (persisted)
    TinyDBPersisted.initialize(db_path=DB_PATH)

    app = RequestChainWin(snap_path)
    app.mainloop()

    # close database
    TinyDBPersisted.close()


if __name__ == "__main__":
    main()
