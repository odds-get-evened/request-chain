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

from blockchain import Blockchain, Transaction, TxTypes


class MenuItems(IntEnum):
    REQUEST = 1
    RELEASE = 2
    RESERVED = 3
    AVAILABLE = 4
    MULTI_REQUEST = 5
    TEST = 6
    STATUS = 7
    EXIT = 8


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


def cleanup(chain: Blockchain, p: Path):
    # always snapshot on exit
    chain.snapshot(p)
    print("\nbye, bye!")


def main():
    priv_key = ec.generate_private_key(ec.SECP256R1())
    pub_key = priv_key.public_key()

    # load pickle file if it exists
    if snap_path.exists():
        with open(snap_path, 'rb') as fh:
            try:
                chain = pickle.load(fh)
            except Exception as e:
                pass
    else:
        # establish a new chain
        chain = Blockchain()

    # register for normal and forced exits
    atexit.register(cleanup, chain, snap_path)
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    # start background monitoring
    threading.Thread(target=blockchain_monitor, args=(chain, 5.0), daemon=True).start()

    menu = """
    1. request (single)
    2. release (single)
    3. list reserved items
    4. list available items
    5. request (multiple)
    6. testing...
    7. report blockchain status
    8. exit
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
            except ValueError as e:
                print(f"❌ {e}")

        elif choice == MenuItems.RELEASE:
            uid = input(f"item ID to release: ").strip()
            tx = Transaction(pub_key, uid, tx_type=TxTypes.RELEASE)
            tx.sign(priv_key)

            try:
                chain.add_block([tx])
                print(f"✅ released {uid}")
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
            except ValueError as e:
                print(f"❌ {e}")

        elif choice == MenuItems.TEST:
            print("#----- test area -----#")
            print(chain)
            print("#----- end test area -----#")

        elif choice == MenuItems.STATUS:
            ok = chain.integrity_check()
            print(f"[status] blockchain is {"A-OK! 😁" if ok else "CORRUPTED! ⚠️"}")
            print(f"[status] block count: {len(chain.chain)}")
            print(f"[status] reserved items: {len(chain.allocation())}")
            print(f"[status] available items: {len(chain.get_available())}")

        elif choice == MenuItems.EXIT:
            # cleanup(chain, snap_path)
            break

        else:
            print("invalid option.")


if __name__ == "__main__":
    main()
