import json
import pickle
import time
from enum import IntEnum, StrEnum
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature


class TxTypes(IntEnum):
    COINBASE = 0  # Mining reward - creates new credits
    REQUEST = 1  # Reserve item - costs credits
    RELEASE = 2  # Release item - refund credits
    TRANSFER = 3  # Send credits to another user
    BUYOUT_OFFER = 4  # Offer to buy out current holder


class TxKeys(StrEnum):
    SIG = "signature"
    REQUESTER = "requester"
    UID = "uid"
    TYPE = "type"
    TIMESTAMP = "timestamp"


class BlockKeys(StrEnum):
    HASH = "hash"
    INDEX = "index"
    PREV_HASH = "prev_hash"
    TXS = "transactions"
    NONCE = "nonce"
    TIMESTAMP = "timestamp"


BIT_OP = "0"

# Economic constants
MINING_REWARD = 50.0  # Base credits earned per mined block
ITEM_REQUEST_COST = 10.0  # Initial credits cost to request an item
GENESIS_CREDITS = 100.0  # Starting credits for genesis block

# Demand-based value system
BASE_DEMAND_PERCENTAGE = 0.05  # 5% base increase per failed attempt
DEMAND_INCREMENT = 0.0001  # +0.01% per demand count (0.0001 as decimal)

# Escrow distribution on release
HOLDER_ESCROW_PERCENTAGE = 0.6667  # 66.67% to holder
MINER_ESCROW_PERCENTAGE = 0.3333  # 33.33% to miner (service fee)


def serialize_pubkey(pubkey: ec.EllipticCurvePublicKey) -> str:
    # sec1 compressed format
    return pubkey.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.CompressedPoint
    ).hex()


def deserialize_pubkey(hex_s: str) -> ec.EllipticCurvePublicKey:
    return ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(),
        bytes.fromhex(hex_s)
    )


def calculate_demand_percentage(demand_count: int) -> float:
    """
    Calculate the percentage increase for an item based on demand count.
    Starts at 5%, increases by 0.01% per demand signal.

    :param demand_count: Number of failed request attempts
    :return: Percentage as decimal (e.g., 0.0501 for 5.01%)
    """
    return BASE_DEMAND_PERCENTAGE + (demand_count * DEMAND_INCREMENT)


def calculate_penalty_amount(current_value: float, demand_count: int) -> float:
    """
    Calculate penalty for failed request attempt.

    :param current_value: Current value of the item
    :param demand_count: Current demand count (for calculating percentage)
    :return: Penalty amount in credits
    """
    percentage = calculate_demand_percentage(demand_count)
    return current_value * percentage


def calculate_new_item_value(current_value: float, demand_count: int) -> float:
    """
    Calculate new item value after failed request attempt.

    :param current_value: Current value of the item
    :param demand_count: Current demand count (for calculating percentage)
    :return: New item value in credits
    """
    percentage = calculate_demand_percentage(demand_count)
    return current_value * (1 + percentage)


class Transaction:
    def __init__(self, pub_key: ec.EllipticCurvePublicKey, uid, tx_type=TxTypes.REQUEST, ts=None, sig=None, amount=0.0,
                 recipient=None, accepted_offer=None):
        self.requester = serialize_pubkey(pub_key)
        self.uid = uid
        self.tx_type = tx_type
        self.timestamp = ts or time.time()
        self.signature = sig
        self.amount = amount  # Credits amount (for COINBASE, TRANSFER, BUYOUT_OFFER, or calculated refund)
        self.recipient = recipient  # For TRANSFER transactions (serialized pubkey)
        self.accepted_offer = accepted_offer  # For RELEASE transactions accepting a buyout (offer tx hash)

    def to_signable_dict(self):
        """Return dict with only immutable fields for signing (excludes amount set after signing)"""
        return {
            TxKeys.REQUESTER: self.requester,
            TxKeys.UID: self.uid,
            TxKeys.TYPE: self.tx_type,
            TxKeys.TIMESTAMP: self.timestamp
        }

    def to_dict(self):
        d = {
            TxKeys.REQUESTER: self.requester,
            TxKeys.UID: self.uid,
            TxKeys.TYPE: self.tx_type,
            TxKeys.TIMESTAMP: self.timestamp
        }
        # Handle backward compatibility
        amount = getattr(self, 'amount', 0.0)
        recipient = getattr(self, 'recipient', None)
        accepted_offer = getattr(self, 'accepted_offer', None)

        if amount != 0.0:
            d['amount'] = amount
        if recipient:
            d['recipient'] = recipient
        if accepted_offer:
            d['accepted_offer'] = accepted_offer
        return d

    def to_full_dict(self):
        """
        Extended representation including signature for UI/inspection.
        This is not used by compute_hash() to preserve original behavior.
        """
        d = self.to_dict()
        d[TxKeys.SIG] = self.signature
        return d

    def sign(self, priv_key: ec.EllipticCurvePrivateKey):
        # Sign only immutable fields (amount is set later in add_to_mempool)
        d = json.dumps(self.to_signable_dict(), sort_keys=True).encode()

        sig = priv_key.sign(d, ec.ECDSA(hashes.SHA256()))
        self.signature = sig.hex()

    def verify(self):
        # COINBASE transactions and system-generated transfers don't need signature verification
        if self.tx_type == TxTypes.COINBASE:
            return True

        # System-generated transactions (BUYOUT_PAYMENT, ESCROW_DISTRIBUTION, etc.)
        if self.signature in ["COINBASE", "BUYOUT_PAYMENT", "ESCROW_DISTRIBUTION", "GENESIS"]:
            return True

        # Verify only immutable fields (amount is set after signing)
        pubk = deserialize_pubkey(self.requester)
        d = json.dumps(self.to_signable_dict(), sort_keys=True).encode()
        try:
            pubk.verify(bytes.fromhex(self.signature), d, ec.ECDSA(hashes.SHA256()))

            return True
        except InvalidSignature:
            return False

    def __str__(self):
        return json.dumps(self.to_dict(), sort_keys=True)


class Block:
    def __init__(self, idx: int, prev_hash, txs, nonce=0, ts=None):
        self.hash = None
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

    def to_full_dict(self) -> dict:
        """
        Extended representation including signatures in transactions for UI display.
        """
        return {
            BlockKeys.INDEX: self.index,
            BlockKeys.PREV_HASH: self.prev_hash,
            BlockKeys.TXS: [tx.to_full_dict() for tx in self.transactions],
            BlockKeys.NONCE: self.nonce,
            BlockKeys.TIMESTAMP: self.timestamp,
            BlockKeys.HASH: self.hash
        }

    def compute_hash(self) -> str:
        blk = self.to_dict()
        return sha256(json.dumps(blk, sort_keys=True).encode()).hexdigest()

    def hash_ok(self) -> bool:
        return self.hash == self.compute_hash()

    def signatures_ok(self):
        for tx in self.transactions:
            if not tx.verify():
                return False

        return True

    def __str__(self):
        return json.dumps(self.to_dict(), sort_keys=True)


class Blockchain:
    def __init__(self, difficulty: int = 2):
        self.chain: list[Block] = []
        self.difficulty: int = difficulty
        self.mempool: list[Transaction] = []  # Pending transactions
        self.item_request_times: dict[str, float] = {}  # Track when items were requested
        self.item_demand_counters: dict[str, int] = {}  # Track failed request attempts per item
        self.item_values: dict[str, float] = {}  # Current value of each reserved item
        self.item_escrow: dict[str, float] = {}  # Accumulated penalty fees per item (in escrow)
        self.active_buyout_offers: dict[str, list[Transaction]] = {}  # Buyout offers per item (legacy, may remove)
        self.genesis()
        self._migrate_old_transactions()

    def _migrate_old_transactions(self):
        """Add missing attributes to old transactions for backward compatibility"""
        for block in self.chain:
            for tx in block.transactions:
                if not hasattr(tx, 'amount'):
                    tx.amount = 0.0
                if not hasattr(tx, 'recipient'):
                    tx.recipient = None
                if not hasattr(tx, 'accepted_offer'):
                    tx.accepted_offer = None

        # Rebuild item tracking from chain
        self._rebuild_item_tracking()

    def _rebuild_item_tracking(self):
        """Rebuild item tracking from blockchain history"""
        self.item_request_times.clear()
        self.item_demand_counters.clear()
        self.item_values.clear()
        self.item_escrow.clear()

        for block in self.chain:
            for tx in block.transactions:
                if tx.tx_type == TxTypes.REQUEST:
                    # Check if this is a regular request, buyout, or penalty
                    if tx.amount == ITEM_REQUEST_COST:
                        # Regular request - item was available
                        self.item_request_times[tx.uid] = tx.timestamp
                        self.item_values[tx.uid] = ITEM_REQUEST_COST  # Start at base value
                        self.item_demand_counters[tx.uid] = 0
                    elif tx.amount > ITEM_REQUEST_COST:
                        # Buyout - paid current value
                        self.item_request_times[tx.uid] = tx.timestamp
                        self.item_values[tx.uid] = ITEM_REQUEST_COST  # Reset to base
                        self.item_demand_counters[tx.uid] = 0
                        # Escrow would have been distributed, so clear it
                        self.item_escrow.pop(tx.uid, None)
                    else:
                        # Penalty - failed attempt
                        # Increase value and add to escrow
                        if tx.uid in self.item_values:
                            demand = self.item_demand_counters.get(tx.uid, 0)
                            self.item_escrow[tx.uid] = self.item_escrow.get(tx.uid, 0.0) + tx.amount
                            self.item_values[tx.uid] = calculate_new_item_value(self.item_values[tx.uid], demand)
                            self.item_demand_counters[tx.uid] = demand + 1

                elif tx.tx_type == TxTypes.RELEASE:
                    # Remove from tracking when released
                    self.item_request_times.pop(tx.uid, None)
                    self.item_values.pop(tx.uid, None)
                    self.item_demand_counters.pop(tx.uid, None)
                    # Escrow distributed on release
                    self.item_escrow.pop(tx.uid, None)

    def genesis(self):
        # only create this block if chain is empty
        if len(self.chain) <= 0:
            # Create genesis transaction - initial credits for the network
            # Using a dummy key for genesis (credits available to first miner)
            genesis_key = ec.generate_private_key(ec.SECP256R1()).public_key()
            genesis_tx = Transaction(
                genesis_key,
                uid="GENESIS",
                tx_type=TxTypes.COINBASE,
                amount=GENESIS_CREDITS
            )
            # Genesis transactions don't need signatures
            genesis_tx.signature = "GENESIS"

            b = Block(0, BIT_OP * 64, [genesis_tx], nonce=0)
            b.hash = b.compute_hash()
            self.chain.append(b)

    @property
    def last_hash(self):
        return self.chain[-1].hash

    def get_balance(self, pub_key_hex: str) -> float:
        """
        Calculate balance for a given public key by walking the chain.

        :param pub_key_hex: Serialized public key (hex string)
        :return: Current balance in credits
        """
        balance = 0.0

        for block in self.chain:
            for tx in block.transactions:
                # Earned credits (COINBASE or RELEASE)
                if tx.requester == pub_key_hex:
                    if tx.tx_type == TxTypes.COINBASE:
                        balance += tx.amount
                    elif tx.tx_type == TxTypes.RELEASE:
                        balance += tx.amount
                    elif tx.tx_type == TxTypes.REQUEST:
                        # REQUEST can be: regular (10), penalty (<10), or buyout (>10)
                        balance -= tx.amount
                    elif tx.tx_type == TxTypes.TRANSFER:
                        balance -= tx.amount

                # Received transfer
                if tx.tx_type == TxTypes.TRANSFER and tx.recipient == pub_key_hex:
                    balance += tx.amount

        return balance

    def get_pending_balance(self, pub_key_hex: str) -> float:
        """
        Calculate pending balance including mempool transactions.
        This shows what the balance WILL BE after mempool transactions are mined.

        :param pub_key_hex: Serialized public key (hex string)
        :return: Pending balance in credits
        """
        balance = self.get_balance(pub_key_hex)

        # Apply pending mempool transactions
        for tx in self.mempool:
            if tx.requester == pub_key_hex:
                if tx.tx_type == TxTypes.REQUEST:
                    balance -= tx.amount  # Variable: regular/penalty/buyout
                elif tx.tx_type == TxTypes.RELEASE:
                    balance += tx.amount
                elif tx.tx_type == TxTypes.TRANSFER:
                    balance -= tx.amount
                elif tx.tx_type == TxTypes.BUYOUT_OFFER:
                    balance -= tx.amount

            if tx.tx_type == TxTypes.TRANSFER and tx.recipient == pub_key_hex:
                balance += tx.amount

        return balance

    def allocation(self):
        allocated = set()

        for blk in self.chain:
            for tx in blk.transactions:
                if tx.tx_type == TxTypes.REQUEST:
                    # Only regular requests (10) and buyouts (>10) add to allocation
                    # Penalties (<10) don't change allocation
                    if tx.amount >= ITEM_REQUEST_COST:
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

    def add_to_mempool(self, tx: Transaction) -> bool:
        """
        Add transaction to mempool after validation.
        Handles: regular requests, buyouts, penalties, releases.
        Returns True if added, False if invalid.
        """
        # COINBASE transactions can only be created during mining
        if tx.tx_type == TxTypes.COINBASE:
            return False

        # Verify signature
        if not tx.verify():
            return False

        # Check for duplicate in mempool (except BUYOUT_OFFER which allows multiples)
        for existing_tx in self.mempool:
            if existing_tx.uid == tx.uid and existing_tx.tx_type == tx.tx_type:
                if tx.tx_type != TxTypes.BUYOUT_OFFER:
                    return False

        # Calculate provisional balance
        requester_balance = self.get_balance(tx.requester)
        for mem_tx in self.mempool:
            if mem_tx.requester == tx.requester:
                requester_balance -= mem_tx.amount if mem_tx.tx_type in [TxTypes.REQUEST, TxTypes.TRANSFER,
                                                                         TxTypes.BUYOUT_OFFER] else 0
                requester_balance += mem_tx.amount if mem_tx.tx_type == TxTypes.RELEASE else 0
            if mem_tx.tx_type == TxTypes.TRANSFER and mem_tx.recipient == tx.requester:
                requester_balance += mem_tx.amount

        # Get current allocation
        cur = self.allocation()
        for mem_tx in self.mempool:
            if mem_tx.tx_type == TxTypes.REQUEST and mem_tx.amount >= ITEM_REQUEST_COST:
                cur.add(mem_tx.uid)  # Regular request or buyout
            elif mem_tx.tx_type == TxTypes.RELEASE:
                cur.discard(mem_tx.uid)

        # Handle REQUEST transactions (3 types: regular, buyout, penalty)
        if tx.tx_type == TxTypes.REQUEST:
            if tx.uid not in cur:
                # REGULAR REQUEST: Item available
                if requester_balance < ITEM_REQUEST_COST:
                    return False
                tx.amount = ITEM_REQUEST_COST
            else:
                # Item is reserved - check buyout vs penalty
                current_value = self.item_values.get(tx.uid, ITEM_REQUEST_COST)
                demand_count = self.item_demand_counters.get(tx.uid, 0)

                if requester_balance >= current_value:
                    # BUYOUT: Can afford current value - automatic takeover
                    tx.amount = current_value
                else:
                    # PENALTY: Can't afford - pay penalty
                    penalty = calculate_penalty_amount(current_value, demand_count)
                    if requester_balance < penalty:
                        return False  # Can't even afford penalty
                    tx.amount = penalty
                    # Penalty transaction will be mined and update escrow/demand/value

        # Handle RELEASE transactions
        elif tx.tx_type == TxTypes.RELEASE:
            if tx.uid not in cur:
                return False
            # Amount = current value (holder gets this back on release)
            tx.amount = self.item_values.get(tx.uid, ITEM_REQUEST_COST)

        # Handle TRANSFER transactions
        elif tx.tx_type == TxTypes.TRANSFER:
            if requester_balance < tx.amount:
                return False

        # Handle BUYOUT_OFFER (legacy, may deprecate)
        elif tx.tx_type == TxTypes.BUYOUT_OFFER:
            if tx.uid not in cur or requester_balance < tx.amount:
                return False
            if tx.uid not in self.active_buyout_offers:
                self.active_buyout_offers[tx.uid] = []
            self.active_buyout_offers[tx.uid].append(tx)

        self.mempool.append(tx)
        return True

    def _find_buyout_offer(self, item_id: str, offer_hash: str) -> Transaction | None:
        """Find a buyout offer in mempool by item and offer hash"""
        for tx in self.mempool:
            if tx.tx_type == TxTypes.BUYOUT_OFFER and tx.uid == item_id:
                # Simple hash: just use timestamp as identifier for now
                if str(tx.timestamp) == offer_hash:
                    return tx
        return None

    def mine_block(self, miner_pubkey: ec.EllipticCurvePublicKey, max_txs: int = None) -> Block | None:
        """
        Mine a block from mempool transactions.
        Handles: regular requests, penalties, buyouts, releases with escrow distribution.

        :param miner_pubkey: Public key of the miner (receives mining reward + escrow fees)
        :param max_txs: Maximum transactions to include (None = all)
        :return: Mined block or None if mempool is empty
        """
        # Take transactions from mempool (exclude legacy buyout offers)
        txs_to_mine = [tx for tx in self.mempool if tx.tx_type != TxTypes.BUYOUT_OFFER]
        if max_txs:
            txs_to_mine = txs_to_mine[:max_txs]

        # Validate transactions and build block
        cur = self.allocation()
        valid_txs = []
        balances = {}
        escrow_fees_for_miner = 0.0  # Accumulated escrow fees for this block

        # Track who currently holds each item (for buyouts and penalties)
        item_holders = {}  # {item_id: holder_pubkey}
        for item_id in cur:
            # Find who requested this item by looking at chain
            for block in reversed(self.chain):
                for tx in block.transactions:
                    if tx.tx_type == TxTypes.REQUEST and tx.uid == item_id and tx.amount >= ITEM_REQUEST_COST:
                        item_holders[item_id] = tx.requester
                        break
                if item_id in item_holders:
                    break

        for tx in txs_to_mine:
            requester = tx.requester

            # Get current balance
            if requester not in balances:
                balances[requester] = self.get_balance(requester)

            # Handle REQUEST transactions (3 types: regular, penalty, buyout)
            if tx.tx_type == TxTypes.REQUEST:
                if tx.uid not in cur:
                    # REGULAR REQUEST: Item available
                    if balances[requester] >= ITEM_REQUEST_COST and tx.amount == ITEM_REQUEST_COST:
                        valid_txs.append(tx)
                        cur.add(tx.uid)
                        balances[requester] -= ITEM_REQUEST_COST
                        item_holders[tx.uid] = requester
                else:
                    # Item reserved - check if penalty or buyout
                    current_value = self.item_values.get(tx.uid, ITEM_REQUEST_COST)

                    if tx.amount >= current_value:
                        # BUYOUT: Automatic takeover
                        if balances[requester] >= tx.amount:
                            holder = item_holders.get(tx.uid)
                            if holder:
                                # Create transfer: buyer → holder
                                transfer = Transaction(
                                    deserialize_pubkey(requester),
                                    uid=f"BUYOUT_{tx.uid}_{tx.timestamp}",
                                    tx_type=TxTypes.TRANSFER,
                                    amount=tx.amount,
                                    recipient=holder
                                )
                                transfer.signature = "BUYOUT_PAYMENT"
                                valid_txs.append(transfer)

                                # Update balances
                                balances[requester] -= tx.amount
                                if holder not in balances:
                                    balances[holder] = self.get_balance(holder)
                                balances[holder] += tx.amount

                                # Distribute escrow
                                escrow_amount = self.item_escrow.get(tx.uid, 0.0)
                                if escrow_amount > 0:
                                    holder_share = escrow_amount * HOLDER_ESCROW_PERCENTAGE
                                    miner_share = escrow_amount * MINER_ESCROW_PERCENTAGE

                                    # Create transfer: escrow → holder
                                    escrow_transfer = Transaction(
                                        miner_pubkey,
                                        uid=f"ESCROW_TO_HOLDER_{tx.uid}_{tx.timestamp}",
                                        tx_type=TxTypes.TRANSFER,
                                        amount=holder_share,
                                        recipient=holder
                                    )
                                    escrow_transfer.signature = "ESCROW_DISTRIBUTION"
                                    valid_txs.append(escrow_transfer)
                                    balances[holder] += holder_share

                                    # Miner gets their share
                                    escrow_fees_for_miner += miner_share

                            # Buyer gets the item (add their request)
                            valid_txs.append(tx)
                            cur.add(tx.uid)  # Actually already in cur, but resetting holder
                            item_holders[tx.uid] = requester
                    else:
                        # PENALTY: Can't afford, pay penalty
                        if balances[requester] >= tx.amount:
                            valid_txs.append(tx)
                            balances[requester] -= tx.amount
                            # Penalty goes to escrow (not to holder yet)
                            # Update will happen in tracking after block is added

            # Handle RELEASE transactions
            elif tx.tx_type == TxTypes.RELEASE:
                if tx.uid in cur:
                    valid_txs.append(tx)
                    cur.remove(tx.uid)

                    # Holder gets current value back
                    balances[requester] += tx.amount

                    # Distribute escrow
                    escrow_amount = self.item_escrow.get(tx.uid, 0.0)
                    if escrow_amount > 0:
                        holder_share = escrow_amount * HOLDER_ESCROW_PERCENTAGE
                        miner_share = escrow_amount * MINER_ESCROW_PERCENTAGE

                        # Holder gets their share (added to release amount)
                        balances[requester] += holder_share

                        # Miner gets their share
                        escrow_fees_for_miner += miner_share

            # Handle TRANSFER transactions
            elif tx.tx_type == TxTypes.TRANSFER:
                if balances[requester] >= tx.amount:
                    valid_txs.append(tx)
                    balances[requester] -= tx.amount
                    if tx.recipient not in balances:
                        balances[tx.recipient] = self.get_balance(tx.recipient)
                    balances[tx.recipient] += tx.amount

        # Create coinbase transaction (mining reward + escrow fees)
        miner_key_hex = serialize_pubkey(miner_pubkey)
        total_mining_reward = MINING_REWARD + escrow_fees_for_miner
        coinbase = Transaction(
            miner_pubkey,
            uid=f"COINBASE_BLOCK_{len(self.chain)}",
            tx_type=TxTypes.COINBASE,
            amount=total_mining_reward
        )
        coinbase.signature = "COINBASE"

        # Coinbase is always first transaction
        all_txs = [coinbase] + valid_txs

        # Mine block
        blk = Block(len(self.chain), self.last_hash, all_txs)
        blk.hash = self.proof_of_work(blk)
        self.chain.append(blk)

        # Update tracking for each transaction
        for tx in valid_txs:
            if tx.tx_type == TxTypes.REQUEST:
                if tx.amount == ITEM_REQUEST_COST:
                    # Regular request
                    self.item_request_times[tx.uid] = tx.timestamp
                    self.item_values[tx.uid] = ITEM_REQUEST_COST
                    self.item_demand_counters[tx.uid] = 0
                    self.item_escrow[tx.uid] = 0.0
                elif tx.amount > ITEM_REQUEST_COST:
                    # Buyout
                    self.item_request_times[tx.uid] = tx.timestamp
                    self.item_values[tx.uid] = ITEM_REQUEST_COST  # Reset to base
                    self.item_demand_counters[tx.uid] = 0
                    self.item_escrow[tx.uid] = 0.0  # Escrow was distributed
                else:
                    # Penalty
                    demand_count = self.item_demand_counters.get(tx.uid, 0)
                    current_value = self.item_values.get(tx.uid, ITEM_REQUEST_COST)

                    # Add penalty to escrow
                    self.item_escrow[tx.uid] = self.item_escrow.get(tx.uid, 0.0) + tx.amount

                    # Increase item value
                    self.item_values[tx.uid] = calculate_new_item_value(current_value, demand_count)

                    # Increment demand counter
                    self.item_demand_counters[tx.uid] = demand_count + 1

            elif tx.tx_type == TxTypes.RELEASE:
                # Clear all tracking
                self.item_request_times.pop(tx.uid, None)
                self.item_values.pop(tx.uid, None)
                self.item_demand_counters.pop(tx.uid, None)
                self.item_escrow.pop(tx.uid, None)

        # Remove mined transactions from mempool
        for tx in txs_to_mine:
            if tx in self.mempool:
                self.mempool.remove(tx)

        return blk
        """
        Mine a block from mempool transactions.

        :param miner_pubkey: Public key of the miner (receives mining reward)
        :param max_txs: Maximum transactions to include (None = all)
        :return: Mined block or None if mempool is empty
        """
        # Take transactions from mempool (exclude buyout offers for now)
        txs_to_mine = [tx for tx in self.mempool if tx.tx_type != TxTypes.BUYOUT_OFFER]
        if max_txs:
            txs_to_mine = txs_to_mine[:max_txs]

        # Validate transactions are still valid together
        cur = self.allocation()
        valid_txs = []

        # Track balances for validation
        balances = {}

        # Track buyout payments that need to be made
        buyout_payments = []  # (from_pubkey, to_pubkey, amount)

        for tx in txs_to_mine:
            requester = tx.requester

            # Get current balance
            if requester not in balances:
                balances[requester] = self.get_balance(requester)

            # Calculate release refund if needed
            if tx.tx_type == TxTypes.RELEASE:
                demand_count = self.item_demand_counters.get(tx.uid, 0)
                accepted_buyout_amount = 0.0

                # Check if accepting a buyout offer
                if tx.accepted_offer:
                    offer = self._find_buyout_offer(tx.uid, tx.accepted_offer)
                    if offer:
                        # Validate offerer has funds
                        offerer_balance = balances.get(offer.requester, self.get_balance(offer.requester))
                        if offerer_balance >= offer.amount + ITEM_REQUEST_COST:
                            accepted_buyout_amount = offer.amount
                            # Track payment: offerer pays holder
                            buyout_payments.append((offer.requester, requester, offer.amount))
                            # Offerer will also auto-request the item
                            balances[offer.requester] = offerer_balance - offer.amount - ITEM_REQUEST_COST

                tx.amount = calculate_release_refund(demand_count, accepted_buyout_amount)

            # Validate item transactions
            if tx.tx_type == TxTypes.REQUEST:
                if tx.uid not in cur and balances[requester] >= ITEM_REQUEST_COST:
                    valid_txs.append(tx)
                    cur.add(tx.uid)
                    balances[requester] -= ITEM_REQUEST_COST
            elif tx.tx_type == TxTypes.RELEASE:
                if tx.uid in cur:
                    valid_txs.append(tx)
                    cur.remove(tx.uid)
                    balances[requester] += tx.amount

                    # If buyout was accepted, auto-request for the buyer
                    if tx.accepted_offer:
                        offer = self._find_buyout_offer(tx.uid, tx.accepted_offer)
                        if offer and tx.uid not in cur:
                            # Create auto-request for buyer
                            auto_request = Transaction(
                                deserialize_pubkey(offer.requester),
                                tx.uid,
                                TxTypes.REQUEST,
                                ts=time.time()
                            )
                            auto_request.signature = offer.signature  # Use same signature
                            valid_txs.append(auto_request)
                            cur.add(tx.uid)
            elif tx.tx_type == TxTypes.TRANSFER:
                if balances[requester] >= tx.amount:
                    valid_txs.append(tx)
                    balances[requester] -= tx.amount
                    # Credit recipient
                    if tx.recipient not in balances:
                        balances[tx.recipient] = self.get_balance(tx.recipient)
                    balances[tx.recipient] += tx.amount

        # Add buyout payments as TRANSFER transactions
        for from_key, to_key, amount in buyout_payments:
            transfer = Transaction(
                deserialize_pubkey(from_key),
                uid=f"BUYOUT_PAYMENT_{time.time()}",
                tx_type=TxTypes.TRANSFER,
                amount=amount,
                recipient=to_key
            )
            transfer.signature = "BUYOUT_PAYMENT"  # System-generated
            valid_txs.append(transfer)

        # Create coinbase transaction (mining reward)
        miner_key_hex = serialize_pubkey(miner_pubkey)
        coinbase = Transaction(
            miner_pubkey,
            uid=f"COINBASE_BLOCK_{len(self.chain)}",
            tx_type=TxTypes.COINBASE,
            amount=MINING_REWARD
        )
        coinbase.signature = "COINBASE"  # Coinbase doesn't need real signature

        # Coinbase is always first transaction
        all_txs = [coinbase] + valid_txs

        # Mine block
        blk = Block(len(self.chain), self.last_hash, all_txs)
        blk.hash = self.proof_of_work(blk)
        self.chain.append(blk)

        # Update tracking
        for tx in valid_txs:
            if tx.tx_type == TxTypes.REQUEST:
                self.item_request_times[tx.uid] = tx.timestamp
                # Reset demand counter when item is successfully requested
                self.item_demand_counters[tx.uid] = 0
            elif tx.tx_type == TxTypes.RELEASE:
                self.item_request_times.pop(tx.uid, None)
                # Reset demand counter after release (refund was calculated)
                self.item_demand_counters[tx.uid] = 0

                # Clear buyout offers for this item
                if tx.uid in self.active_buyout_offers:
                    # Remove accepted offer and all others for this item from mempool
                    offers_to_remove = self.active_buyout_offers[tx.uid]
                    for offer in offers_to_remove:
                        if offer in self.mempool:
                            self.mempool.remove(offer)
                    del self.active_buyout_offers[tx.uid]

        # Remove mined transactions from mempool (not coinbase or system-generated)
        for tx in txs_to_mine:
            if tx in self.mempool:
                self.mempool.remove(tx)

        return blk

    def remove_from_mempool(self, tx: Transaction):
        """Remove transaction from mempool"""
        if tx in self.mempool:
            self.mempool.remove(tx)

    def clear_mempool_transactions(self, txs: list[Transaction]):
        """Remove multiple transactions from mempool (e.g., after receiving a block)"""
        for tx in txs:
            # Match by uid and type
            self.mempool = [
                mem_tx for mem_tx in self.mempool
                if not (mem_tx.uid == tx.uid and mem_tx.tx_type == tx.tx_type)
            ]

    def add_block(self, txs: list[Transaction]):
        # verify transaction signatures first (skip coinbase and system-generated)
        for tx in txs:
            if tx.tx_type not in [TxTypes.COINBASE] and tx.signature not in ["COINBASE", "BUYOUT_PAYMENT",
                                                                             "ESCROW_DISTRIBUTION"] and not tx.verify():
                raise ValueError(f"invalid signature for transaction {tx.uid}.")

        # Track balances for validation
        balances = {}

        # validate
        cur = self.allocation()
        for tx in txs:
            # Skip coinbase validation (it creates new credits)
            if tx.tx_type == TxTypes.COINBASE:
                continue

            requester = tx.requester

            # Get current balance
            if requester not in balances:
                balances[requester] = self.get_balance(requester)

            # Validate REQUEST (regular/penalty/buyout - all use tx.amount)
            if tx.tx_type == TxTypes.REQUEST:
                if balances[requester] < tx.amount:
                    raise ValueError(
                        f"insufficient credits for {tx.uid}. Need {tx.amount:.2f}, have {balances[requester]:.2f}.")

                # Regular request or buyout (amount >= ITEM_REQUEST_COST) adds to cur
                if tx.amount >= ITEM_REQUEST_COST:
                    # Item must not be in cur for regular request, but can be for buyout
                    # We trust the mining logic handled this correctly
                    if tx.uid in cur and tx.amount == ITEM_REQUEST_COST:
                        # This is a regular request but item already reserved - error
                        raise ValueError(f"item {tx.uid} is already reserved (cannot regular request).")
                    cur.add(tx.uid)
                # Penalty requests (amount < ITEM_REQUEST_COST) don't change cur

                balances[requester] -= tx.amount

            elif tx.tx_type == TxTypes.RELEASE:
                if tx.uid not in cur:
                    raise ValueError(f"item {tx.uid} is ready for request.")
                cur.remove(tx.uid)
                # Use the amount from the transaction (includes current value + escrow share)
                balances[requester] += tx.amount

            elif tx.tx_type == TxTypes.TRANSFER:
                # System-generated transfers (BUYOUT_PAYMENT, ESCROW_DISTRIBUTION) are trusted
                if tx.signature not in ["BUYOUT_PAYMENT", "ESCROW_DISTRIBUTION"]:
                    if balances[requester] < tx.amount:
                        raise ValueError(
                            f"insufficient credits for transfer. Need {tx.amount}, have {balances[requester]:.1f}.")
                balances[requester] -= tx.amount
                # Credit recipient
                if tx.recipient not in balances:
                    balances[tx.recipient] = self.get_balance(tx.recipient)
                balances[tx.recipient] += tx.amount

        # mine & append
        blk = Block(len(self.chain), self.last_hash, txs)
        blk.hash = self.proof_of_work(blk)
        self.chain.append(blk)

        # Update tracking (rebuild from chain to stay consistent)
        self._rebuild_item_tracking()

    def snapshot(self, p: Path):
        with open(p, 'wb') as fh:
            pickle.dump(self, fh, pickle.HIGHEST_PROTOCOL)

    def integrity_check(self) -> bool:
        """
        walks the chain and ensures:
            - each block's stored hash matches the computed_hash()
            - prev_hash links correctly
            - all transactions signatures verify.
        :return: success/failure
        """
        for i, blk in enumerate(self.chain):
            # 1. check block hash
            if not blk.hash_ok():
                # print(f"there is problem computing hash for block [{i}]")
                return False
            # 2. check block linkage to previous block (skipping genesis block)
            if not self.linkage_ok(i, blk):
                # print(f"there is broken link in block [{i}]")
                return False
            # 3. check each transaction signature
            if not blk.signatures_ok():
                # print(f"there is a transaction with an invalid signature in block [{i}]")
                return False

        # print("no corruption in blockchain")
        return True

    def linkage_ok(self, cur_idx: int, cur_blk: Block):
        if cur_idx > 0:  # ignore genesis block
            prev = self.chain[cur_idx - 1]
            if cur_blk.prev_hash != prev.hash:
                return False

        return True

    def find_bad_block(self) -> int | None:
        """
        returns the index of the first block whose
        hash/linkage/signatures don't check out.
        :return:
        """
        for i, blk in enumerate(self.chain):
            # found a hash mismatch
            if not blk.hash_ok():
                return i

            # found a bad linkage
            if not self.linkage_ok(i, blk):
                return i

            # found a bad transaction signature
            if not blk.signatures_ok():
                return i

        return None

    def repair(self) -> bool:
        """
        if corruption is found, truncate the tail back
        to the last good block and re-save.

        :return: True if repair was needed, otherwise False
        """
        bad_idx = self.find_bad_block()
        if not bad_idx:  # chain is in good standing
            return False

        # drop the bad block and everything after it.
        self.chain = self.chain[:bad_idx]
        # re-compute the hashes just in case
        for blk in self.chain:
            blk.hash = blk.compute_hash()

        return True

    def replace_chain(self, new_chain: list[dict]) -> bool:
        """
        Replace our chain with a longer valid chain (consensus mechanism).
        Only accepts chains that are:
        1. Longer than current chain
        2. Pass full integrity check

        :param new_chain: List of block dicts from peer
        :return: True if chain was replaced
        """
        if len(new_chain) <= len(self.chain):
            return False

        # Reconstruct blockchain from dicts
        temp_blockchain = Blockchain(difficulty=self.difficulty)
        temp_blockchain.chain = []

        try:
            for blk_dict in new_chain:
                # Reconstruct transactions
                txs = []
                for tx_dict in blk_dict.get('transactions', []):
                    pub = deserialize_pubkey(tx_dict['requester'])
                    tx = Transaction(
                        pub,
                        tx_dict['uid'],
                        tx_dict['type'],
                        tx_dict.get('timestamp'),
                        tx_dict.get('signature'),
                        tx_dict.get('amount', 0.0),
                        tx_dict.get('recipient'),
                        tx_dict.get('accepted_offer')
                    )
                    txs.append(tx)

                # Reconstruct block
                blk = Block(
                    blk_dict['index'],
                    blk_dict['prev_hash'],
                    txs,
                    blk_dict.get('nonce', 0),
                    blk_dict.get('timestamp')
                )
                blk.hash = blk_dict.get('hash')
                temp_blockchain.chain.append(blk)

            # Validate the new chain
            if temp_blockchain.integrity_check():
                self.chain = temp_blockchain.chain
                self.difficulty = temp_blockchain.difficulty
                return True

        except Exception as e:
            print(f"Failed to validate peer chain: {e}")

        return False

    def __str__(self):
        return "\n".join([json.dumps(b.to_dict(), sort_keys=True) for b in self.chain])

    @staticmethod
    def init(p: Path, difficulty: int = 2):
        # load pickle file if it exists
        if p.exists():
            with open(p, 'rb') as fh:
                try:
                    chain = pickle.load(fh)
                except Exception as e:
                    raise FileExistsError(f"{str(p)} does not exist. {str(e)}")
        else:
            # establish a new chain
            chain = Blockchain(difficulty=difficulty)

        return chain