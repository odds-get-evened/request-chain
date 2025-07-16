import json
import pickle
import time
from enum import IntEnum, StrEnum
from hashlib import sha256

from ecdsa import VerifyingKey, SigningKey, NIST256p


class TxTypes(IntEnum):
    REQUEST = 1
    RELEASE = 2


class TxKeys(StrEnum):
    REQUESTER = "requester"
    UID = "uid"
    TYPE = "type"
    TIMESTAMP = "timestamp"


class BlockKeys(StrEnum):
    INDEX = "index"
    PREV_HASH = "prev_hash"
    TXS = "transactions"
    NONCE = "nonce"
    TIMESTAMP = "timestamp"


BIT_OP = "0"


class Transaction:
    def __init__(self, pub_key: VerifyingKey, uid, tx_type=TxTypes.REQUEST, ts=None, sig=None):
        self.requester = pub_key.to_string().hex()
        self.uid = uid
        self.tx_type = tx_type
        self.timestamp = ts or time.time()
        self.signature = sig

    def to_dict(self):
        return {
            TxKeys.REQUESTER: self.requester,
            TxKeys.UID: self.uid,
            TxKeys.TYPE: self.tx_type,
            TxKeys.TIMESTAMP: self.timestamp
        }

    def sign(self, priv_key: SigningKey):
        d = json.dumps(self.to_dict(), sort_keys=True).encode()

        self.signature = priv_key.sign(d).hex()

    def verify(self):
        vk = VerifyingKey.from_string(bytes.fromhex(self.requester), curve=NIST256p)
        d = json.dumps(self.to_dict(), sort_keys=True).encode()

        return vk.verify(bytes.fromhex(self.signature), d)

    def __str__(self):
        return json.dumps(self.to_dict(), sort_keys=True)


class Block:
    def __init__(self, idx, prev_hash, txs, nonce=0, ts=None):
        self.index = idx
        self.prev_hash = prev_hash
        self.transactions: list[Transaction] = txs
        self.nonce = nonce
        self.timestamp = ts or time.time()

    def to_dict(self) -> dict:
        return {
            BlockKeys.INDEX: self.index,
            BlockKeys.PREV_HASH: self.prev_hash,
            BlockKeys.TXS: [tx.to_dict() for tx in self.transactions],
            BlockKeys.NONCE: self.nonce,
            BlockKeys.TIMESTAMP: self.timestamp
        }

    def compute_hash(self) -> str:
        blk = self.to_dict()
        return sha256(json.dumps(blk, sort_keys=True).encode()).hexdigest()

    def __str__(self):
        return json.dumps(self.to_dict(), sort_keys=True)


class Blockchain:
    def __init__(self, difficulty=2):
        self.chain: list[Block] = []
        self.difficulty: int = difficulty
        self.genesis()

    def genesis(self):
        # only create this block if chain is empty
        if len(self.chain) <= 0:
            b = Block(0, BIT_OP * 64, [], nonce=0)
            b.hash = b.compute_hash()
            self.chain.append(b)

    @property
    def last_hash(self):
        return self.chain[-1].hash

    def allocation(self):
        allocated = set()

        for blk in self.chain:
            for tx in blk.transactions:
                if tx.tx_type == TxTypes.REQUEST:
                    allocated.add(tx.uid)
                elif tx.tx_type == TxTypes.RELEASE:
                    allocated.discard(tx.uid)

        return allocated

    def get_available(self):
        seen = set()

        for blk in self.chain:
            for tx in blk.transactions:
                seen.add(tx.uid)

        return seen - self.allocation()

    def proof_of_work(self, block: Block):
        tgt = BIT_OP * self.difficulty

        while True:
            h = block.compute_hash()
            if h.startswith(tgt):
                return h

            block.nonce += 1

    def add_block(self, txs: list[Transaction]):
        # verify transaction signatures first
        for tx in txs:
            if not tx.verify():
                raise ValueError(f"invalid signature for transaction {tx.uid}.")

        # validate
        cur = self.allocation()
        for tx in txs:
            if tx.tx_type == TxTypes.REQUEST and tx.uid in cur:
                raise ValueError(f"item {tx.uid} is not available.")
            if tx.tx_type == TxTypes.RELEASE and tx.uid not in cur:
                raise ValueError(f"item {tx.uid} is ready for request.")

            # provisional update
            if tx.tx_type == TxTypes.REQUEST:
                cur.add(tx.uid)
            else:
                cur.remove(tx.uid)

        # mine & append
        blk = Block(len(self.chain), self.last_hash, txs)
        blk.hash = self.proof_of_work(blk)
        self.chain.append(blk)

    def snapshot(self, p):
        with open(p, 'wb') as fh:
            pickle.dump(self, fh, pickle.HIGHEST_PROTOCOL)

    def __str__(self):
        return "\n".join([json.dumps(b.to_dict(), sort_keys=True) for b in self.chain])
        # return json.dumps([b.to_dict() for b in self.chain], sort_keys=True, indent=4)
