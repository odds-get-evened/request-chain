import tkinter as tk

from material.blockchain import Blockchain, TxTypes, Transaction


class BlockchainUI(tk.Tk):
    def __init__(self, bc: Blockchain, priv_key, pub_key):
        super().__init__()
        self.ent_rel = None
        self.ent_req = None
        self.chain = bc
        self.priv_key = priv_key
        self.pub_key = pub_key
        self.title("Item request system")
        self.make_widgets()
        self.refresh_lists()

    def make_widgets(self):
        frame_req = tk.LabelFrame(self, text="Request item")
        frame_req.pack(fill='x', padx=5, pady=5)
        self.ent_req = tk.Entry(frame_req)
        self.ent_req.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        btn_req = tk.Button(frame_req, text='Request', command=lambda : self.do_tx(self.ent_req.get(), TxTypes.REQUEST))
        btn_req.pack(side=tk.RIGHT, padx=5)

        frame_rel = tk.LabelFrame(self, text='Release item')
        frame_rel.pack(fill=tk.X, padx=5, pady=5)
        self.ent_rel = tk.Entry(frame_rel)
        self.ent_rel.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        btn_rel = tk.Button(frame_rel, text='Release item', command=lambda : self.do_tx(self.ent_rel.get(), TxTypes.RELEASE))
        btn_rel.pack(side=tk.RIGHT, padx=5)

        frame_ls = tk.Frame(self)
        frame_ls.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.lb_alloc = tk.Listbox(frame_ls)
        self.lb_alloc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.lb_avail = tk.Listbox(frame_ls)
        self.lb_avail.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        btn_refresh = tk.Button(self, text='Refresh lists', command=self.refresh_lists)
        btn_refresh.pack(pady=5)
        tk.Label(self, text='Left: Allocated | Right: Available').pack()

    def do_tx(self, uid, tx_type):
        uid = uid.strip()

        if not uid:
            return

        tx = Transaction(self.pub_key, uid, tx_type=tx_type)


    def refresh_lists(self):
        pass
