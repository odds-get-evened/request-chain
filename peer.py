import atexit
import pickle
import signal
import sys
import threading
import time
from enum import IntEnum
from pathlib import Path
from queue import Queue, Empty

from cryptography.hazmat.primitives.asymmetric import ec

from blockchain.blockchain import Blockchain, Transaction, TxTypes
from blockchain.network import P2PNetwork


class MenuItems(IntEnum):
    REQUEST = 1
    RELEASE = 2
    RESERVED = 3
    AVAILABLE = 4
    MULTI_REQUEST = 5
    CONNECT_PEER = 6
    LIST_PEERS = 7
    SYNC_CHAIN = 8
    STATUS = 9
    EXIT = 10


snap_path = Path.home().joinpath('.databox', 'material', 'blx.pkl')
snap_path.parent.mkdir(parents=True, exist_ok=True)

status_q = Queue()


def blockchain_monitor(chain: Blockchain, interval: float = 10.0):
    """
    only reports once when the chain toggles status
    :param chain:
    :param interval:
    :return:
    """
    last_ok: bool | None = None

    while True:
        cur_ok = chain.integrity_check()
        # if state is changed, enqueue an update
        if last_ok is None or cur_ok != last_ok:
            if cur_ok:
                status_q.put("[monitor 😁] chain is A-OK!")
            else:
                status_q.put("[monitor ⚠️] corruption detected -- repairing...")

                if chain.repair():
                    status_q.put("[monitor ✅] repair completed.")
                else:
                    status_q.put("[monitor ❌] repair failed.")

            last_ok = cur_ok

        time.sleep(interval)


def get_user_input(prompt: str) -> str:
    # drain any pending monitor messages first
    try:
        while True:
            print(status_q.get_nowait())
    except Empty:
        pass

    return input(prompt)


def cleanup(chain: Blockchain, p: Path, network: P2PNetwork):
    # always snapshot on exit
    chain.snapshot(p)
    network.stop()
    print("\nbye, bye!")


def setup_network_callbacks(network: P2PNetwork, chain: Blockchain):
    """Configure P2P network callbacks"""

    def handle_new_block(block_data: dict):
        """Handle incoming block from peer"""
        try:
            # Reconstruct block and validate
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

            # Validate and add block if it extends our chain
            if len(chain.chain) == block_data['index']:
                chain.add_block(txs)
                status_q.put(f"[network 📦] received and added block #{block_data['index']}")
                chain.snapshot(snap_path)
        except Exception as e:
            status_q.put(f"[network ❌] failed to process block: {e}")

    def handle_new_transaction(tx_data: dict):
        """Handle incoming transaction from peer"""
        status_q.put(f"[network 💳] received transaction: {tx_data.get('uid')}")

    def handle_chain_request() -> dict:
        """Send our chain to requesting peer"""
        return {
            'chain': [b.to_full_dict() for b in chain.chain],
            'length': len(chain.chain)
        }

    def handle_chain_response(response_data: dict):
        """Handle chain response from peer (consensus mechanism)"""
        try:
            peer_chain = response_data.get('chain', [])
            peer_length = response_data.get('length', 0)

            status_q.put(f"[consensus 📡] received chain (length {peer_length}) vs ours (length {len(chain.chain)})")

            # Try to replace our chain if peer's is longer and valid
            if chain.replace_chain(peer_chain):
                status_q.put(f"[consensus ✅] adopted longer chain ({peer_length} blocks)")
                chain.snapshot(snap_path)
            else:
                if peer_length > len(chain.chain):
                    status_q.put(f"[consensus ❌] peer chain failed validation")
                else:
                    status_q.put(f"[consensus ℹ️] kept current chain (already longest)")

        except Exception as e:
            status_q.put(f"[consensus ❌] error processing chain: {e}")

    network.on_new_block = handle_new_block
    network.on_new_transaction = handle_new_transaction
    network.on_chain_request = handle_chain_request
    network.on_chain_response = handle_chain_response


def main():
    # Get port from command line or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 6000

    priv_key = ec.generate_private_key(ec.SECP256R1())
    pub_key = priv_key.public_key()

    # load pickle file if it exists
    if snap_path.exists():
        with open(snap_path, 'rb') as fh:
            try:
                chain = pickle.load(fh)
            except Exception as e:
                chain = Blockchain()
    else:
        # establish a new chain
        chain = Blockchain()

    # Initialize P2P network
    p2p = P2PNetwork(host="0.0.0.0", port=port)
    setup_network_callbacks(p2p, chain)
    p2p.start()

    # register for normal and forced exits
    atexit.register(cleanup, chain, snap_path, p2p)
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    # start background monitoring
    threading.Thread(target=blockchain_monitor, args=(chain, 5.0), daemon=True).start()

    menu = f"""
    === Blockchain Node (Port {port}) ===
    1. request (single)
    2. release (single)
    3. list reserved items
    4. list available items
    5. request (multiple)
    6. connect to peer
    7. list connected peers
    8. sync chain from network (consensus)
    9. report blockchain status
    10. exit
    """

    while True:
        choice = get_user_input(menu + "\nselect > ").strip()
        choice = int(choice.strip())

        if choice == MenuItems.REQUEST:
            uid = input("item ID to request: ").strip()
            tx = Transaction(pub_key, uid, tx_type=TxTypes.REQUEST)
            tx.sign(priv_key)

            try:
                chain.add_block([tx])
                print(f"✅ requested {uid}")

                # Broadcast to network
                p2p.announce_new_block(chain.chain[-1].to_full_dict())
                chain.snapshot(snap_path)
            except ValueError as e:
                print(f"❌ {e}")

        elif choice == MenuItems.RELEASE:
            uid = input(f"item ID to release: ").strip()
            tx = Transaction(pub_key, uid, tx_type=TxTypes.RELEASE)
            tx.sign(priv_key)

            try:
                chain.add_block([tx])
                print(f"✅ released {uid}")

                # Broadcast to network
                p2p.announce_new_block(chain.chain[-1].to_full_dict())
                chain.snapshot(snap_path)
            except ValueError as e:
                print(f"❌ {e}")

        elif choice == MenuItems.RESERVED:
            allocs = chain.allocation()
            if allocs:
                print("allocated items: ")
                for uid in allocs:
                    print(f" - {uid}")
            else:
                print("all items are available")

        elif choice == MenuItems.AVAILABLE:
            a = chain.get_available()
            if a:
                print("available items: ")
                for uid in a:
                    print(f" - {uid}")
            else:
                print("no items are available")

        elif choice == MenuItems.MULTI_REQUEST:
            uids = input("enter item IDs to request: ")
            uids = [u.strip() for u in uids.split(",") if u.strip()]
            txs = []
            for uid in uids:
                tx = Transaction(pub_key, uid, tx_type=TxTypes.REQUEST)
                tx.sign(priv_key)
                txs.append(tx)

            try:
                chain.add_block(txs)
                print(f"✅ requested {', '.join(uids)}.")

                # Broadcast to network
                p2p.announce_new_block(chain.chain[-1].to_full_dict())
                chain.snapshot(snap_path)
            except ValueError as e:
                print(f"❌ {e}")

        elif choice == MenuItems.CONNECT_PEER:
            host = input("peer host (e.g. localhost): ").strip()
            peer_port = int(input("peer port (e.g. 6001): ").strip())
            p2p.connect_to_peer(host, peer_port)
            print(f"🔗 connecting to {host}:{peer_port}...")

        elif choice == MenuItems.LIST_PEERS:
            if p2p.peers:
                print(f"connected peers ({len(p2p.peers)}):")
                for peer in p2p.peers:
                    print(f" - {peer.address}")
            else:
                print("no peers connected")

        elif choice == MenuItems.SYNC_CHAIN:
            print("📡 requesting chains from all peers (consensus mechanism will choose longest valid chain)...")
            p2p.request_chain_from_peers()

        elif choice == MenuItems.STATUS:
            ok = chain.integrity_check()
            print(f"[status] blockchain is {"A-OK! 😁" if ok else "CORRUPTED! ⚠️"}")
            print(f"[status] block count: {len(chain.chain)}")
            print(f"[status] reserved items: {len(chain.allocation())}")
            print(f"[status] available items: {len(chain.get_available())}")
            print(f"[status] connected peers: {len(p2p.peers)}")

        elif choice == MenuItems.EXIT:
            break

        else:
            print("invalid option.")


if __name__ == "__main__":
    main()