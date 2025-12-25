import atexit
import pickle
import signal
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from queue import Queue, Empty

from cryptography.hazmat.primitives.asymmetric import ec

from blockchain.blockchain import Blockchain, Transaction, TxTypes
from blockchain.network import P2PNetwork


class BlockchainPeerUI:
    def __init__(self, root, port: int = 6000):
        self._cleaning_up = False
        self.root = root
        self.port = port
        self.root.title(f"Blockchain Peer - Port {port}")
        self.root.geometry("900x700")

        # Blockchain setup
        self.snap_path = Path.home().joinpath('.databox', 'material', 'blx.pkl')
        self.snap_path.parent.mkdir(parents=True, exist_ok=True)

        self.priv_key = ec.generate_private_key(ec.SECP256R1())
        self.pub_key = self.priv_key.public_key()

        # Load or create chain
        self.chain = self._load_chain()

        # P2P Network
        self.p2p = P2PNetwork(host="0.0.0.0", port=port)
        self._setup_network_callbacks()
        self.p2p.start()

        # Message queue for thread-safe UI updates
        self.message_queue = Queue()

        # Track last state for smart updates
        self._last_chain_length = 0
        self._last_peer_count = 0

        # Setup UI
        self._create_ui()

        # Start background threads
        self._start_background_tasks()

        # Register cleanup
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, lambda s, f: self.cleanup())
        signal.signal(signal.SIGTERM, lambda s, f: self.cleanup())

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.exit_application)

        # Start message processor
        self._process_messages()

    def _load_chain(self):
        """Load blockchain from disk or create new"""
        if self.snap_path.exists():
            with open(self.snap_path, 'rb') as fh:
                try:
                    return pickle.load(fh)
                except Exception as e:
                    self.log_message(f"Failed to load chain: {e}")
                    return Blockchain()
        return Blockchain()

    def _create_ui(self):
        """Create the UI layout"""
        # Create menubar
        self._create_menubar()

        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky='nsew')

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # === Left Panel: Actions ===
        left_frame = ttk.LabelFrame(main_frame, text="Batch Operations", padding="10")
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        left_frame.rowconfigure(3, weight=1)

        # Instructions
        instructions = ttk.Label(
            left_frame,
            text="Double-click items in Overview tab to add here",
            font=('TkDefaultFont', 8),
            foreground='gray',
            wraplength=180
        )
        instructions.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # Item entry for manual add
        ttk.Label(left_frame, text="Or enter manually:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))

        entry_frame = ttk.Frame(left_frame)
        entry_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=5)
        entry_frame.columnconfigure(0, weight=1)

        self.item_id_entry = ttk.Entry(entry_frame)
        self.item_id_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        # Action selector
        self.action_var = tk.StringVar(value="REQUEST")
        action_combo = ttk.Combobox(entry_frame, textvariable=self.action_var, values=["REQUEST", "RELEASE"],
                                    state="readonly", width=10)
        action_combo.pack(side=tk.LEFT)

        # Bind Enter to add
        self.item_id_entry.bind('<Return>', lambda e: self.add_to_batch_manual())

        ttk.Button(left_frame, text="Add to Batch", command=self.add_to_batch_manual).grid(
            row=3, column=0, columnspan=2, sticky='ew', pady=(0, 15))

        # Batch list with action indicators
        ttk.Label(left_frame, text="Batch Queue:", font=('TkDefaultFont', 9, 'bold')).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=5, column=0, columnspan=2, sticky='nsew', pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        list_scroll = ttk.Scrollbar(list_frame)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.batch_listbox = tk.Listbox(list_frame, yscrollcommand=list_scroll.set)
        self.batch_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.config(command=self.batch_listbox.yview)

        # Store batch items with actions
        self.batch_items = []  # List of (action, item_id) tuples

        # Delete key to remove
        self.batch_listbox.bind('<Delete>', lambda e: self.remove_from_batch())
        self.batch_listbox.bind('<BackSpace>', lambda e: self.remove_from_batch())

        # Control buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=6, column=0, columnspan=2, sticky='ew', pady=5)

        ttk.Button(btn_frame, text="Remove", command=self.remove_from_batch, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_batch, width=12).pack(side=tk.LEFT, padx=2)

        # Execute batch
        self.execute_btn = ttk.Button(left_frame, text="Execute Batch", command=self.execute_batch)
        self.execute_btn.grid(row=7, column=0, columnspan=2, sticky='ew', pady=(5, 0))
        self.update_execute_button()

        # === Right Panel: Tabs ===
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky='nsew')
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        # Status indicators
        status_frame = ttk.LabelFrame(right_frame, text="Status", padding="10")
        status_frame.grid(row=0, column=0, sticky='ew', pady=(0, 5))
        status_frame.columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Chain Length:").grid(row=0, column=0, sticky=tk.W)
        self.chain_length_label = ttk.Label(status_frame, text="0", font=('TkDefaultFont', 10, 'bold'))
        self.chain_length_label.grid(row=0, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="Peers:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        self.peers_label = ttk.Label(status_frame, text="0", font=('TkDefaultFont', 10, 'bold'))
        self.peers_label.grid(row=0, column=3, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="Integrity:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.integrity_label = ttk.Label(status_frame, text="OK", font=('TkDefaultFont', 10, 'bold'),
                                         foreground='green')
        self.integrity_label.grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)

        ttk.Label(status_frame, text="Reserved:").grid(row=1, column=2, sticky=tk.W, padx=(20, 0), pady=5)
        self.reserved_label = ttk.Label(status_frame, text="0", font=('TkDefaultFont', 10, 'bold'))
        self.reserved_label.grid(row=1, column=3, sticky=tk.W, padx=10, pady=5)

        # Tabbed notebook
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.grid(row=1, column=0, sticky='nsew')

        # === Tab 1: Overview ===
        self._create_overview_tab()

        # === Tab 2: Peers ===
        self._create_peers_tab()

        # === Tab 3: Blockchain ===
        self._create_blockchain_tab()

        # === Tab 4: Activity Log ===
        self._create_log_tab()

        # Initial log message
        self.log_message(f"🌐 Blockchain Peer started on port {self.port}")

    def _create_menubar(self):
        """Create the application menubar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Exit", command=self.exit_application, accelerator="Ctrl+Q")

        # Network menu
        network_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Network", menu=network_menu)
        network_menu.add_command(label="Connect to Peer...", command=self.show_connect_dialog, accelerator="Ctrl+N")
        network_menu.add_separator()
        network_menu.add_command(label="Sync Chain", command=self.sync_chain, accelerator="Ctrl+S")

        # Bind keyboard shortcuts
        self.root.bind('<Control-q>', lambda e: self.exit_application())
        self.root.bind('<Control-n>', lambda e: self.show_connect_dialog())
        self.root.bind('<Control-s>', lambda e: self.sync_chain())

    def _create_overview_tab(self):
        """Create overview tab with items"""
        overview_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(overview_frame, text="Overview")

        overview_frame.columnconfigure(0, weight=1)
        overview_frame.columnconfigure(1, weight=1)
        overview_frame.rowconfigure(1, weight=1)

        # Headers with instructions
        reserved_header = ttk.Label(
            overview_frame,
            text="Reserved Items (double-click to release)",
            font=('TkDefaultFont', 9, 'bold')
        )
        reserved_header.grid(row=0, column=0, sticky=tk.W, padx=5)

        available_header = ttk.Label(
            overview_frame,
            text="Available Items (double-click to request)",
            font=('TkDefaultFont', 9, 'bold')
        )
        available_header.grid(row=0, column=1, sticky=tk.W, padx=5)

        # Reserved listbox
        reserved_frame = ttk.Frame(overview_frame)
        reserved_frame.grid(row=1, column=0, sticky='nsew', pady=5, padx=5)

        reserved_scrollbar = ttk.Scrollbar(reserved_frame)
        reserved_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.reserved_listbox = tk.Listbox(reserved_frame, yscrollcommand=reserved_scrollbar.set,
                                           selectmode=tk.SINGLE)
        self.reserved_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        reserved_scrollbar.config(command=self.reserved_listbox.yview)

        # Double-click to add to batch for release
        self.reserved_listbox.bind('<Double-Button-1>', lambda e: self.add_reserved_to_batch())

        # Available listbox
        available_frame = ttk.Frame(overview_frame)
        available_frame.grid(row=1, column=1, sticky='nsew', pady=5, padx=5)

        available_scrollbar = ttk.Scrollbar(available_frame)
        available_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.available_listbox = tk.Listbox(available_frame, yscrollcommand=available_scrollbar.set,
                                            selectmode=tk.SINGLE)
        self.available_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        available_scrollbar.config(command=self.available_listbox.yview)

        # Double-click to add to batch for request
        self.available_listbox.bind('<Double-Button-1>', lambda e: self.add_available_to_batch())

    def _create_peers_tab(self):
        """Create peers tab with connected peer details"""
        peers_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(peers_frame, text="Peers")

        peers_frame.columnconfigure(0, weight=1)
        peers_frame.rowconfigure(0, weight=1)

        # Peers treeview
        tree_frame = ttk.Frame(peers_frame)
        tree_frame.grid(row=0, column=0, sticky='nsew')
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.peers_tree = ttk.Treeview(
            tree_frame,
            columns=('address', 'status', 'blocks', 'txs', 'msgs', 'uptime'),
            show='tree headings',
            yscrollcommand=tree_scroll.set
        )
        self.peers_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.peers_tree.yview)

        # Configure columns
        self.peers_tree.heading('#0', text='Peer')
        self.peers_tree.heading('address', text='Address')
        self.peers_tree.heading('status', text='Status')
        self.peers_tree.heading('blocks', text='Blocks Recv')
        self.peers_tree.heading('txs', text='Txs Recv')
        self.peers_tree.heading('msgs', text='Messages')
        self.peers_tree.heading('uptime', text='Connected')

        self.peers_tree.column('#0', width=80)
        self.peers_tree.column('address', width=180)
        self.peers_tree.column('status', width=100)
        self.peers_tree.column('blocks', width=90)
        self.peers_tree.column('txs', width=90)
        self.peers_tree.column('msgs', width=100)
        self.peers_tree.column('uptime', width=120)

    def _create_blockchain_tab(self):
        """Create blockchain ledger tab"""
        blockchain_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(blockchain_frame, text="Blockchain")

        blockchain_frame.columnconfigure(0, weight=1)
        blockchain_frame.rowconfigure(0, weight=1)

        # Blockchain treeview
        tree_frame = ttk.Frame(blockchain_frame)
        tree_frame.grid(row=0, column=0, sticky='nsew')
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.blockchain_tree = ttk.Treeview(
            tree_frame,
            columns=('hash', 'timestamp', 'txs', 'nonce'),
            show='tree headings',
            yscrollcommand=tree_scroll.set
        )
        self.blockchain_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.blockchain_tree.yview)

        # Configure columns
        self.blockchain_tree.heading('#0', text='Block')
        self.blockchain_tree.heading('hash', text='Hash')
        self.blockchain_tree.heading('timestamp', text='Timestamp')
        self.blockchain_tree.heading('txs', text='Transactions')
        self.blockchain_tree.heading('nonce', text='Nonce')

        self.blockchain_tree.column('#0', width=100)
        self.blockchain_tree.column('hash', width=200)
        self.blockchain_tree.column('timestamp', width=150)
        self.blockchain_tree.column('txs', width=100)
        self.blockchain_tree.column('nonce', width=100)

    def _create_log_tab(self):
        """Create activity log tab"""
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text="Activity Log")

        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky='nsew')

    def log_message(self, message: str):
        """Add message to log (thread-safe)"""
        self.message_queue.put(('log', message))

    def update_status(self):
        """Update status displays (thread-safe)"""
        self.message_queue.put(('status', None))

    def _process_messages(self):
        """Process queued messages for UI updates"""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()

                if msg_type == 'log':
                    timestamp = time.strftime("%H:%M:%S")
                    self.log_text.insert(tk.END, f"[{timestamp}] {data}\n")
                    self.log_text.see(tk.END)

                elif msg_type == 'status':
                    self._update_status_displays()

        except Empty:
            pass

        # Schedule next check
        self.root.after(100, self._process_messages)

    def _update_status_displays(self):
        """Update all status displays"""
        # Chain length
        current_chain_length = len(self.chain.chain)
        self.chain_length_label.config(text=str(current_chain_length))

        # Peers
        current_peer_count = len(self.p2p.peers)
        self.peers_label.config(text=str(current_peer_count))

        # Integrity
        ok = self.chain.integrity_check()
        self.integrity_label.config(
            text="OK" if ok else "CORRUPT",
            foreground="green" if ok else "red"
        )

        # Reserved count
        reserved = self.chain.allocation()
        self.reserved_label.config(text=str(len(reserved)))

        # Update listboxes while preserving selections
        # Save reserved selection
        reserved_selection = None
        if self.reserved_listbox.curselection():
            idx = self.reserved_listbox.curselection()[0]
            reserved_selection = self.reserved_listbox.get(idx)

        # Update reserved list
        self.reserved_listbox.delete(0, tk.END)
        reserved_list = sorted(reserved)
        for item in reserved_list:
            self.reserved_listbox.insert(tk.END, item)

        # Restore reserved selection
        if reserved_selection and reserved_selection in reserved_list:
            idx = reserved_list.index(reserved_selection)
            self.reserved_listbox.selection_set(idx)

        # Save available selection
        available_selection = None
        if self.available_listbox.curselection():
            idx = self.available_listbox.curselection()[0]
            available_selection = self.available_listbox.get(idx)

        # Update available list
        available = self.chain.get_available()
        self.available_listbox.delete(0, tk.END)
        available_list = sorted(available)
        for item in available_list:
            self.available_listbox.insert(tk.END, item)

        # Restore available selection
        if available_selection and available_selection in available_list:
            idx = available_list.index(available_selection)
            self.available_listbox.selection_set(idx)

        # Only update peers tree if peer count changed
        if current_peer_count != self._last_peer_count:
            self._update_peers_tree()
            self._last_peer_count = current_peer_count

        # Only update blockchain tree if chain length changed
        if current_chain_length != self._last_chain_length:
            self._update_blockchain_tree()
            self._last_chain_length = current_chain_length

    def _update_peers_tree(self):
        """Update peers treeview while preserving selections"""
        # Save current selections
        selected_addresses = set()
        for item in self.peers_tree.selection():
            values = self.peers_tree.item(item, 'values')
            if values:
                selected_addresses.add(values[0])  # Address is first value

        # Clear existing
        for item in self.peers_tree.get_children():
            self.peers_tree.delete(item)

        # Add peers
        current_time = time.time()
        peer_items = {}

        for i, peer in enumerate(self.p2p.peers, 1):
            status = "Connected" if peer.connected else "Disconnected"

            # Calculate uptime
            uptime_seconds = int(current_time - peer.connected_at)
            if uptime_seconds < 60:
                uptime = f"{uptime_seconds}s"
            elif uptime_seconds < 3600:
                uptime = f"{uptime_seconds // 60}m"
            else:
                hours = uptime_seconds // 3600
                mins = (uptime_seconds % 3600) // 60
                uptime = f"{hours}h {mins}m"

            # Message stats
            msg_stats = f"{peer.messages_received}↓ {peer.messages_sent}↑"

            peer_id = self.peers_tree.insert(
                '',
                'end',
                text=f"Peer {i}",
                values=(
                    peer.address,
                    status,
                    peer.blocks_received,
                    peer.transactions_received,
                    msg_stats,
                    uptime
                )
            )

            peer_items[peer.address] = peer_id

        # Restore selections
        items_to_select = []
        for address in selected_addresses:
            if address in peer_items:
                items_to_select.append(peer_items[address])

        if items_to_select:
            self.peers_tree.selection_set(items_to_select)

    def _update_blockchain_tree(self):
        """Update blockchain treeview while preserving state"""
        # Save current state
        expanded_blocks = set()
        selected_items = set()

        for item in self.blockchain_tree.get_children():
            # Get block index from item text
            item_text = self.blockchain_tree.item(item, 'text')
            if 'Block #' in item_text:
                block_idx = item_text.split('#')[1]

                # Check if expanded
                if self.blockchain_tree.item(item, 'open'):
                    expanded_blocks.add(block_idx)

                # Check if selected
                if item in self.blockchain_tree.selection():
                    selected_items.add(('block', block_idx))

                # Check child transactions for selection
                for child in self.blockchain_tree.get_children(item):
                    if child in self.blockchain_tree.selection():
                        child_text = self.blockchain_tree.item(child, 'text')
                        selected_items.add(('tx', block_idx, child_text))

        # Clear existing
        for item in self.blockchain_tree.get_children():
            self.blockchain_tree.delete(item)

        # Add blocks in reverse order (newest first)
        block_items = {}
        for block in reversed(self.chain.chain):
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(block.timestamp))
            hash_short = block.hash[:16] + "..." if block.hash and len(block.hash) > 16 else block.hash or "N/A"
            block_idx_str = str(block.index)

            block_id = self.blockchain_tree.insert(
                '',
                'end',
                text=f"Block #{block.index}",
                values=(hash_short, timestamp, len(block.transactions), block.nonce)
            )

            block_items[block_idx_str] = block_id

            # Add transactions as children
            for tx in block.transactions:
                tx_type = "REQUEST" if tx.tx_type == TxTypes.REQUEST else "RELEASE"
                requester_short = tx.requester[:16] + "..." if len(tx.requester) > 16 else tx.requester
                tx_time = time.strftime("%H:%M:%S", time.localtime(tx.timestamp))
                tx_text = f"{tx_type}: {tx.uid}"

                self.blockchain_tree.insert(
                    block_id,
                    'end',
                    text=tx_text,
                    values=(requester_short, tx_time, "", "")
                )

        # Restore expanded state
        for block_idx in expanded_blocks:
            if block_idx in block_items:
                self.blockchain_tree.item(block_items[block_idx], open=True)

        # Restore selections
        items_to_select = []
        for selection in selected_items:
            if selection[0] == 'block':
                block_idx = selection[1]
                if block_idx in block_items:
                    items_to_select.append(block_items[block_idx])
            elif selection[0] == 'tx':
                block_idx = selection[1]
                tx_text = selection[2]
                if block_idx in block_items:
                    block_id = block_items[block_idx]
                    for child in self.blockchain_tree.get_children(block_id):
                        if self.blockchain_tree.item(child, 'text') == tx_text:
                            items_to_select.append(child)
                            break

        if items_to_select:
            self.blockchain_tree.selection_set(items_to_select)

    def add_to_batch_manual(self):
        """Add item manually to batch with selected action"""
        uid = self.item_id_entry.get().strip()
        if not uid:
            return

        action = self.action_var.get()
        self._add_to_batch(action, uid)
        self.item_id_entry.delete(0, tk.END)
        self.item_id_entry.focus_set()

    def add_reserved_to_batch(self):
        """Add selected reserved item to batch for release"""
        selection = self.reserved_listbox.curselection()
        if not selection:
            return

        uid = self.reserved_listbox.get(selection[0])
        self._add_to_batch("RELEASE", uid)

    def add_available_to_batch(self):
        """Add selected available item to batch for request"""
        selection = self.available_listbox.curselection()
        if not selection:
            return

        uid = self.available_listbox.get(selection[0])
        self._add_to_batch("REQUEST", uid)

    def _add_to_batch(self, action, uid):
        """Internal method to add item to batch"""
        # Check for duplicates
        for existing_action, existing_uid in self.batch_items:
            if existing_uid == uid:
                self.log_message(f"⚠️ '{uid}' already in batch")
                return

        # Add to internal list
        self.batch_items.append((action, uid))

        # Add to visual list
        display_text = f"{action}: {uid}"
        self.batch_listbox.insert(tk.END, display_text)

        count = len(self.batch_items)
        self.log_message(f"Added '{uid}' to batch ({count} item{'s' if count != 1 else ''})")
        self.update_execute_button()

    def remove_from_batch(self):
        """Remove selected item from batch"""
        selection = self.batch_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        action, uid = self.batch_items[idx]

        # Remove from both lists
        self.batch_items.pop(idx)
        self.batch_listbox.delete(idx)

        count = len(self.batch_items)
        self.log_message(f"Removed '{uid}' from batch ({count} item{'s' if count != 1 else ''} remaining)")
        self.update_execute_button()

    def clear_batch(self):
        """Clear all items from batch"""
        count = len(self.batch_items)
        if count == 0:
            return

        if messagebox.askyesno("Clear Batch", f"Remove all {count} item{'s' if count != 1 else ''} from batch?"):
            self.batch_items.clear()
            self.batch_listbox.delete(0, tk.END)
            self.log_message("Batch cleared")
            self.update_execute_button()

    def update_execute_button(self):
        """Update execute button text based on batch contents"""
        count = len(self.batch_items)
        if count == 0:
            self.execute_btn.config(text="Execute Batch", state=tk.DISABLED)
        elif count == 1:
            action, uid = self.batch_items[0]
            self.execute_btn.config(text=f"{action.title()} 1 Item", state=tk.NORMAL)
        else:
            self.execute_btn.config(text=f"Execute Batch ({count} items)", state=tk.NORMAL)

    def execute_batch(self):
        """Execute batch operations - smart handling of single vs multiple"""
        if len(self.batch_items) == 0:
            return

        # Group by action type
        requests = []
        releases = []

        for action, uid in self.batch_items:
            tx = Transaction(self.pub_key, uid, tx_type=TxTypes.REQUEST if action == "REQUEST" else TxTypes.RELEASE)
            tx.sign(self.priv_key)

            if action == "REQUEST":
                requests.append((uid, tx))
            else:
                releases.append((uid, tx))

        # Execute operations
        try:
            # Process requests
            if requests:
                txs = [tx for _, tx in requests]
                self.chain.add_block(txs)

                if len(requests) == 1:
                    self.log_message(f"✅ Requested {requests[0][0]}")
                else:
                    items_str = ", ".join(uid for uid, _ in requests)
                    self.log_message(f"✅ Requested {len(requests)} items: {items_str}")

                self.p2p.announce_new_block(self.chain.chain[-1].to_full_dict())
                self.chain.snapshot(self.snap_path)

            # Process releases
            if releases:
                txs = [tx for _, tx in releases]
                self.chain.add_block(txs)

                if len(releases) == 1:
                    self.log_message(f"✅ Released {releases[0][0]}")
                else:
                    items_str = ", ".join(uid for uid, _ in releases)
                    self.log_message(f"✅ Released {len(releases)} items: {items_str}")

                self.p2p.announce_new_block(self.chain.chain[-1].to_full_dict())
                self.chain.snapshot(self.snap_path)

            # Clear batch on success
            self.batch_items.clear()
            self.batch_listbox.delete(0, tk.END)
            self.update_execute_button()
            self.update_status()

        except ValueError as e:
            self.log_message(f"❌ {e}")
            messagebox.showerror("Error", str(e))

    def show_connect_dialog(self):
        """Show modal dialog for connecting to peer"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Connect to Peer")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # Dialog content
        content_frame = ttk.Frame(dialog, padding="20")
        content_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(content_frame, text="Enter peer connection details:", font=('TkDefaultFont', 10, 'bold')).pack(
            pady=(0, 20))

        # Host
        host_frame = ttk.Frame(content_frame)
        host_frame.pack(fill=tk.X, pady=5)
        ttk.Label(host_frame, text="Host:", width=10).pack(side=tk.LEFT)
        host_entry = ttk.Entry(host_frame, width=30)
        host_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        host_entry.insert(0, "localhost")

        # Port
        port_frame = ttk.Frame(content_frame)
        port_frame.pack(fill=tk.X, pady=5)
        ttk.Label(port_frame, text="Port:", width=10).pack(side=tk.LEFT)
        port_entry = ttk.Entry(port_frame, width=30)
        port_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        port_entry.insert(0, "6001")

        # Buttons
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(pady=(20, 0))

        def on_connect():
            host = host_entry.get().strip()
            port_str = port_entry.get().strip()

            if not host or not port_str:
                messagebox.showwarning("Input Required", "Please enter host and port", parent=dialog)
                return

            try:
                port = int(port_str)
                self.p2p.connect_to_peer(host, port)
                self.log_message(f"🔗 Connecting to {host}:{port}...")
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid port number", parent=dialog)

        def on_cancel():
            dialog.destroy()

        ttk.Button(button_frame, text="Connect", command=on_connect).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)

        # Bind Enter key to connect
        dialog.bind('<Return>', lambda e: on_connect())
        dialog.bind('<Escape>', lambda e: on_cancel())

        # Focus on host entry
        host_entry.focus_set()
        host_entry.select_range(0, tk.END)

    def sync_chain(self):
        """Manually trigger chain sync"""
        if len(self.p2p.peers) == 0:
            messagebox.showinfo("No Peers", "Please connect to at least one peer first.")
            return

        self.log_message("📡 Manually requesting chain sync from peers...")
        self.p2p.request_chain_from_peers()

    def exit_application(self):
        """Exit the application"""
        if messagebox.askokcancel("Exit", "Are you sure you want to exit?"):
            self.cleanup()
            self.root.quit()

    def _setup_network_callbacks(self):
        """Setup P2P network callbacks"""

        def handle_new_block(block_data: dict):
            try:
                from blockchain.blockchain import Block, deserialize_pubkey

                txs = []
                for tx_dict in block_data.get('transactions', []):
                    pub = deserialize_pubkey(tx_dict['requester'])
                    tx = Transaction(
                        pub,
                        tx_dict['uid'],
                        tx_dict['type'],
                        tx_dict.get('timestamp'),
                        tx_dict.get('signature')
                    )
                    txs.append(tx)

                if len(self.chain.chain) == block_data['index']:
                    self.chain.add_block(txs)
                    self.log_message(f"📦 Received block #{block_data['index']}")
                    self.chain.snapshot(self.snap_path)
                    self.update_status()

            except Exception as e:
                self.log_message(f"❌ Failed to process block: {e}")

        def handle_chain_request():
            return {
                'chain': [b.to_full_dict() for b in self.chain.chain],
                'length': len(self.chain.chain)
            }

        def handle_chain_response(response_data: dict):
            try:
                peer_chain = response_data.get('chain', [])
                peer_length = response_data.get('length', 0)

                self.log_message(f"📡 Received chain (length {peer_length}) vs ours ({len(self.chain.chain)})")

                if self.chain.replace_chain(peer_chain):
                    self.log_message(f"✅ Adopted longer chain ({peer_length} blocks)")
                    self.chain.snapshot(self.snap_path)
                    self.update_status()
                else:
                    if peer_length > len(self.chain.chain):
                        self.log_message(f"❌ Peer chain failed validation")
                    else:
                        self.log_message(f"ℹ️ Kept current chain (already longest)")

            except Exception as e:
                self.log_message(f"❌ Error processing chain: {e}")

        self.p2p.on_new_block = handle_new_block
        self.p2p.on_chain_request = handle_chain_request
        self.p2p.on_chain_response = handle_chain_response

    def _start_background_tasks(self):
        """Start background monitoring threads"""

        # Integrity monitor
        def integrity_monitor():
            last_ok = None
            while True:
                ok = self.chain.integrity_check()
                if last_ok is None or ok != last_ok:
                    if ok:
                        self.log_message("😁 Chain integrity: OK")
                    else:
                        self.log_message("⚠️ Corruption detected - repairing...")
                        if self.chain.repair():
                            self.log_message("✅ Repair completed")
                        else:
                            self.log_message("❌ Repair failed")
                    last_ok = ok
                    self.update_status()
                time.sleep(10)

        # Status updater
        def status_updater():
            while True:
                self.update_status()
                time.sleep(5)

        # Auto sync
        def auto_sync():
            time.sleep(10)  # Initial delay
            while True:
                if len(self.p2p.peers) > 0:
                    self.p2p.request_chain_from_peers()
                time.sleep(30)  # Sync every 30 seconds

        threading.Thread(target=integrity_monitor, daemon=True).start()
        threading.Thread(target=status_updater, daemon=True).start()
        threading.Thread(target=auto_sync, daemon=True).start()

    def cleanup(self):
        """Cleanup on exit"""
        if hasattr(self, '_cleaning_up'):
            return
        self._cleaning_up = True

        self.chain.snapshot(self.snap_path)
        self.p2p.stop()
        self.log_message("Shutting down...")
        print("Blockchain peer shut down cleanly.")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 6000

    root = tk.Tk()
    app = BlockchainPeerUI(root, port)
    root.mainloop()


if __name__ == "__main__":
    main()
