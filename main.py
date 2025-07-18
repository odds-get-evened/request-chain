import pickle
import threading
import time
from enum import IntEnum
from pathlib import Path
from queue import Queue, Empty

from ecdsa import SigningKey, NIST256p

from blockchain import Blockchain, Transaction, TxTypes


class MenuItems(IntEnum):
    REQUEST = 1
    RELEASE = 2
    RESERVED = 3
    AVAILABLE = 4
    MULTI_REQUEST = 5
    TEST = 6
    EXIT = 7


status_q = Queue()


def blockchain_monitor(chain: Blockchain, interval: float = 10.0):
    """
    periodically verify & repair the chain; enqueue status
    :param chain:
    :param interval:
    :return:
    """
    while True:
        if chain.integrity_check():
            status_q.put("[monitor] chain is A-OK 😁")
        else:
            status_q.put("[monitor] ⚠️ CHAIN CORRUPTED ⚠️ repairing...")

            if chain.repair():
                status_q.put("[monitor] ✅ repaired ")
            else:
                status_q.put("[monitor] ❌ repair failed")

        time.sleep(interval)


def get_user_input(prompt: str) -> str:
    # drain any pending monitor messages first
    try:
        while True:
            print(status_q.get_nowait())
    except Empty:
        pass

    return input(prompt)


def main():
    priv_key = SigningKey.generate(curve=NIST256p)
    pub_key = priv_key.get_verifying_key()

    snap_path = Path.home().joinpath('.databox', 'material', 'blx.pkl')
    snap_path.parent.mkdir(parents=True, exist_ok=True)

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

    # start background monitoring
    threading.Thread(target=blockchain_monitor, args=(chain, 5.0), daemon=True).start()

    menu = """
    1. request (single)
    2. release (single)
    3. list reserved items
    4. list available items
    5. request (multiple)
    6. testing...
    7. exit
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

        elif choice == MenuItems.EXIT:
            chain.snapshot(snap_path)
            print("bye, bye")
            break

        else:
            print("invalid option.")


if __name__ == "__main__":
    main()
