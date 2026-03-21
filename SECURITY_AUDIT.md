# Security Audit Report: Request-Chain Blockchain

**Date:** 2026-03-21
**Scope:** Defensive security audit of the Request-Chain P2P blockchain codebase
**Files Reviewed:** `blockchain/blockchain.py`, `blockchain/network.py`, `blockchain/security.py`, `electron_backend.py`

---

## Executive Summary

This audit identified **14 security vulnerabilities** across the codebase, including 2 critical issues, 4 high-severity issues, 4 medium-severity issues, and 4 low-severity issues. The most severe findings are: a logic flaw allowing any user to release items they don't own (theft of credits), and the complete absence of network encryption despite encryption code existing in the codebase.

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High     | 4 |
| Medium   | 4 |
| Low      | 4 |
| **Total** | **14** |

---

## Vulnerabilities

---

### VULN-1 — Critical: RELEASE Transactions Do Not Verify Item Ownership

**Files:** `blockchain/blockchain.py`
**Locations:** `add_to_mempool()` (lines 514–519), `mine_block()` (lines 654–658), `add_block()` (lines 940–943)

#### Description

When a RELEASE transaction is validated, the code checks only that the item exists in the reserved set (`cur`). It does **not** verify that the requester is the actual holder of the item. Any user with a valid keypair can release any item in the system.

#### Vulnerable Code (`add_to_mempool`, lines 514–519)

```python
elif tx.tx_type == TxTypes.RELEASE:
    if tx.uid not in cur:
        return False
    # Missing: if cur.get(tx.uid) != tx.requester: return False
    tx.amount = self.item_values.get(tx.uid, ITEM_REQUEST_COST)
```

The same holder check is absent in `mine_block()` (line 654) and `add_block()` (line 940).

#### Attack Scenario

1. Alice pays 10 credits to reserve item `widget-A`.
2. Attacker Eve generates her own ECDSA keypair and signs a valid RELEASE transaction for `widget-A`.
3. The transaction passes signature verification (Eve's key signed it correctly).
4. The mempool accepts it — no holder check is performed.
5. The block is mined: Alice's item is released and the credit value is credited to Eve.
6. Eve has stolen Alice's reservation value without ever legitimately holding the item.

#### Recommended Fix

In all three validation paths, add a check that `cur[tx.uid] == tx.requester`:

```python
elif tx.tx_type == TxTypes.RELEASE:
    if tx.uid not in cur:
        return False
    if cur.get(tx.uid) != tx.requester:   # ADD THIS
        return False
    tx.amount = self.item_values.get(tx.uid, ITEM_REQUEST_COST)
```

Apply equivalently in `mine_block()` and `add_block()`.

---

### VULN-2 — Critical: P2P Network Transmits All Data In Plaintext (Encryption Code Is Unused)

**Files:** `blockchain/network.py`, `blockchain/security.py`
**Location:** `_handle_peer()` (lines 151–179), `_send_handler()` (lines 181–192)

#### Description

`security.py` implements a complete ECDH key exchange + AES-256-GCM encryption system (`CryptKeeper`). However, this class is **never imported or referenced** by `P2PNetwork`. All messages — including blocks, transactions, peer lists, and signatures — are sent as raw newline-delimited JSON over unencrypted TCP sockets.

#### Vulnerable Code (`network.py`, lines 186–188)

```python
def _send_handler(self, peer: Peer):
    ...
    data = msg.to_json() + '\n'
    peer.socket.sendall(data.encode('utf-8'))   # Plaintext — no encryption
```

#### Attack Scenarios

**Passive eavesdropping:** Any attacker on the same network segment can read all transaction data, linking public keys to item access patterns and building a complete picture of network activity.

**Active injection (no message authentication):** Because messages carry no HMAC or authenticated encryption, an attacker with MITM position can:
- Inject fabricated `NEW_BLOCK` or `NEW_TRANSACTION` messages
- Modify a `CHAIN_RESPONSE` payload before it reaches the target node
- Replay old transactions or chain states

**Note:** CHAIN_RESPONSE forgery is partly mitigated by signature/hash validation in `replace_chain()`, but `NEW_TRANSACTION` and `NEW_BLOCK` payloads have no equivalent protection at the transport layer.

#### Recommended Fix

Integrate `CryptKeeper` into `P2PNetwork`. During the connection handshake, both sides exchange PEM public keys. All subsequent `sendall()` / `recv()` calls use `encrypt()` / `decrypt()` from `CryptKeeper`. This provides both confidentiality and authentication (AES-GCM is authenticated encryption).

---

### VULN-3 — High: TRANSFER Amount and Recipient Are Not Included in the Signed Payload

**File:** `blockchain/blockchain.py`
**Location:** `Transaction.to_signable_dict()` (lines 138–145)

#### Description

Signatures only cover `{requester, uid, type, timestamp}`. For TRANSFER transactions, the `amount` and `recipient` fields — the two most security-critical values — are **excluded from signing**. A man-in-the-middle or malicious node can modify either field after the signature is created, and signature verification will still pass.

#### Vulnerable Code (lines 138–145)

```python
def to_signable_dict(self):
    return {
        TxKeys.REQUESTER: self.requester,
        TxKeys.UID:        self.uid,
        TxKeys.TYPE:       self.tx_type,
        TxKeys.TIMESTAMP:  self.timestamp
        # 'amount' and 'recipient' are NOT included
    }
```

#### Attack Scenario

1. Alice signs a TRANSFER of 100 credits to Bob's pubkey.
2. The signed transaction propagates through the P2P network.
3. A malicious relay node modifies `recipient` to its own pubkey (or `amount` to a higher value within Alice's balance).
4. The receiving node calls `tx.verify()` — which checks only the signable dict. Verification succeeds.
5. The modified transaction is mined: funds go to the attacker, not Bob.

#### Recommended Fix

Include `amount` and `recipient` in `to_signable_dict()` unconditionally (using `None` / `0.0` defaults for transaction types that don't use them):

```python
def to_signable_dict(self):
    return {
        TxKeys.REQUESTER:  self.requester,
        TxKeys.UID:        self.uid,
        TxKeys.TYPE:       self.tx_type,
        TxKeys.TIMESTAMP:  self.timestamp,
        'amount':          getattr(self, 'amount', 0.0),
        'recipient':       getattr(self, 'recipient', None),
    }
```

Note: This is a breaking protocol change. All existing signatures would be invalidated.

---

### VULN-4 — High: `dict.add()` Crash Bug in Mempool Validation

**File:** `blockchain/blockchain.py`
**Location:** `add_to_mempool()` (lines 484–489)

#### Description

`allocation()` returns `dict[str, str]` (uid → holder pubkey). The mempool validation code then calls `.add()` and `.discard()` on this dict — methods that only exist on `set`. This raises an `AttributeError` whenever a REQUEST transaction is already pending in the mempool.

#### Vulnerable Code (lines 484–489)

```python
cur = self.allocation()           # Returns dict, NOT a set
for mem_tx in self.mempool:
    if mem_tx.tx_type == TxTypes.REQUEST and mem_tx.amount >= ITEM_REQUEST_COST:
        cur.add(mem_tx.uid)       # AttributeError: 'dict' object has no attribute 'add'
    elif mem_tx.tx_type == TxTypes.RELEASE:
        cur.discard(mem_tx.uid)   # AttributeError: 'dict' object has no attribute 'discard'
```

#### Attack Scenario

1. Attacker submits a valid REQUEST transaction. It enters the mempool.
2. Any subsequent call to `add_to_mempool()` by any user — even legitimate ones — will hit the `cur.add()` line and raise an `AttributeError`.
3. No further transactions can be added to the mempool until the node is restarted.
4. This is a denial-of-service: one transaction permanently breaks new transaction acceptance.

#### Recommended Fix

Convert the allocation dict to a set of reserved UIDs:

```python
cur = set(self.allocation().keys())
```

The rest of the code using `cur` as a set (`.add()`, `.discard()`, `in cur`) will then work correctly.

---

### VULN-5 — High: Proof-of-Work Difficulty=2 Enables Trivial 51% Attacks

**File:** `blockchain/blockchain.py`
**Location:** `Blockchain.__init__()` (line 264), `proof_of_work()` (lines 432–440)

#### Description

The default PoW difficulty is 2, meaning a valid block hash must start with `"00"`. With SHA-256 in hex, this is a 1-in-256 probability — achievable in under a millisecond on modern hardware. A single attacker machine can mine blocks many orders of magnitude faster than the expected honest network, making chain takeover near-effortless.

#### Attack Scenarios

**51% attack / double spend:**
1. Attacker requests item `widget-A` on the public chain; transaction is confirmed.
2. Attacker mines a private fork from one block before the REQUEST, excluding the REQUEST transaction, at overwhelming speed.
3. When the private fork is longer than the public chain, attacker broadcasts it.
4. All honest nodes adopt the longer chain (consensus rule). The REQUEST transaction is orphaned.
5. Attacker now has the item AND retains the credits.

**History rewrite:**
Due to trivial mining speed, an attacker can rewrite the last N blocks in seconds, reversing any recent transaction.

#### Recommended Fix

- Increase difficulty to at least 5 (1-in-1,048,576 chance) for test deployments; higher for production.
- Implement **dynamic difficulty adjustment**: recalculate difficulty every N blocks so that average block time stays within a target window (e.g., 10–60 seconds).

---

### VULN-6 — High: `repair()` Silently Ignores Genesis Block Corruption

**File:** `blockchain/blockchain.py`
**Location:** `repair()` (lines 1042–1058)

#### Description

`repair()` calls `find_bad_block()` which returns `None` when the chain is clean, or an integer index for the first bad block. The bug is using `if not bad_idx:` to check for the clean case — this also evaluates to `True` when `bad_idx == 0` (the genesis block is corrupt), so genesis corruption is never repaired.

#### Vulnerable Code (lines 1049–1051)

```python
bad_idx = self.find_bad_block()
if not bad_idx:   # BUG: 'not 0' is True — genesis corruption treated as "no corruption"
    return False
```

#### Impact

A node that loads a tampered genesis block will silently accept it as valid. Since all subsequent blocks reference the genesis hash, a completely fabricated chain history could be loaded from disk without triggering any repair.

#### Recommended Fix

Use an explicit `None` check:

```python
if bad_idx is None:
    return False
```

---

### VULN-7 — Medium: Unbounded Mempool Enables Memory Exhaustion

**File:** `blockchain/blockchain.py`
**Location:** `add_to_mempool()` (lines 442–535)

#### Description

The mempool is an unbounded Python list. There is no maximum size limit. An attacker can flood the mempool with valid penalty transactions (each deducting a tiny penalty amount) for highly-demanded items, consuming memory without limit.

#### Attack Scenario

1. Attacker repeatedly submits REQUEST transactions for a highly-valued item they cannot buy out.
2. Each transaction results in a small penalty (valid, passes all checks) and is added to the mempool.
3. Memory usage grows until the node runs out of RAM and crashes (OOM kill), causing denial of service.

#### Recommended Fix

Define a maximum mempool size and reject new transactions when the limit is reached:

```python
MAX_MEMPOOL_SIZE = 10_000  # Configurable constant

def add_to_mempool(self, tx: Transaction) -> bool:
    if len(self.mempool) >= MAX_MEMPOOL_SIZE:
        return False
    ...
```

---

### VULN-8 — Medium: No Rate Limiting on P2P Message Handling or Flask API

**Files:** `blockchain/network.py` (lines 151–179), `electron_backend.py`

#### Description

There is no per-peer rate limiting on incoming P2P messages. A malicious peer can flood a node with `REQUEST_CHAIN`, `NEW_TRANSACTION`, or `NEW_BLOCK` messages at maximum TCP throughput, consuming CPU and bandwidth. The Flask API similarly has no rate limiting on transaction submission or mining endpoints.

#### Attack Scenarios

**P2P flooding:** A peer floods `REQUEST_CHAIN` messages. Each triggers `on_chain_request`, serializing and transmitting the full chain. CPU and bandwidth are saturated.

**API flooding:** Automated POST requests to `/mine` or `/request` endpoints can lock up the mining thread or fill the mempool.

#### Recommended Fix

- **P2P:** Track `messages_per_second` per `Peer` object (already has `messages_received` counter). Disconnect peers exceeding a threshold (e.g., 100 messages/second).
- **API:** Add `Flask-Limiter` with per-IP rate limits on mutation endpoints.

---

### VULN-9 — Medium: Floating-Point Precision Causes Permanent Credit Loss in Escrow

**File:** `blockchain/blockchain.py`
**Location:** Constants (lines 49–50), `mine_block()` (lines 621–639, 663–672)

#### Description

The escrow distribution constants `HOLDER_ESCROW_PERCENTAGE = 0.6667` and `MINER_ESCROW_PERCENTAGE = 0.3333` sum to `0.9999`, not `1.0`. On every escrow distribution, 0.01% of the escrow pool is permanently lost. Combined with floating-point representation errors, credits are not conserved across operations.

#### Example

For an escrow pool of 100 credits:
- Holder receives: `100 × 0.6667 = 66.67`
- Miner receives: `100 × 0.3333 = 33.33`
- Total distributed: `99.99` — 0.01 credits vanish permanently

Over thousands of transactions, this accumulates into a meaningful discrepancy between total credits issued and credits reachable by any user.

#### Recommended Fix

Calculate one share as the remainder to guarantee conservation:

```python
holder_share = escrow_amount * HOLDER_ESCROW_PERCENTAGE
miner_share = escrow_amount - holder_share   # Exact remainder, no rounding loss
```

For full correctness, use `decimal.Decimal` for all financial arithmetic.

---

### VULN-10 — Medium: Dead Code Contains Reference to Undefined Function

**File:** `blockchain/blockchain.py`
**Location:** Lines 743–883

#### Description

`mine_block()` has a `return blk` statement at line 743, followed by approximately 140 lines of dead, unreachable code. This dead block is a vestigial second implementation of `mine_block()` that references `calculate_release_refund()` — a function that does not exist anywhere in the codebase.

If this code were ever made reachable through refactoring (e.g., removing the early return, or a merge conflict), it would raise a `NameError` at runtime and silently corrupt mining behavior by using the wrong logic.

#### Recommended Fix

Delete lines 744–883 (the entire dead code block after the first `return blk`).

---

### VULN-11 — Low: Full Network Topology Disclosed on `PEER_ANNOUNCE`

**File:** `blockchain/network.py`
**Location:** `_route_message()` (lines 198–203)

#### Description

When any node connects and sends `PEER_ANNOUNCE`, the receiving node immediately responds with its complete peer list — every currently connected peer address. An attacker can connect to a single node to enumerate the entire network topology.

#### Attack Scenarios

- **Eclipse attack preparation:** Attacker maps all connections, then saturates the target node's peer slots (MAX_PEERS = 64) with attacker-controlled nodes, isolating it from the honest network.
- **Targeted DoS:** Peer list reveals IP:port of specific high-value nodes (e.g., primary miners) for targeted attacks.

#### Recommended Fix

Return only a random subset of peers (e.g., up to 8), consistent with Bitcoin's approach:

```python
import random
peer_list = random.sample([p.address for p in self.peers if p != peer],
                          min(8, len(self.peers) - 1))
```

---

### VULN-12 — Low: Mempool Deduplication Allows Same-User Spam via Timestamp Variation

**File:** `blockchain/blockchain.py`
**Location:** `add_to_mempool()` (lines 467–471)

#### Description

Duplicate transaction detection checks only `uid` and `tx_type`. A user can submit multiple transactions for the same item with slightly different timestamps, all passing deduplication. Balance checks prevent overspending, but this still allows mempool spam and complicates mining logic.

#### Vulnerable Code (lines 467–471)

```python
for existing_tx in self.mempool:
    if existing_tx.uid == tx.uid and existing_tx.tx_type == tx.tx_type:
        if tx.tx_type != TxTypes.BUYOUT_OFFER:
            return False
# Different timestamp = different transaction = passes this check
```

#### Recommended Fix

Include `requester` in the deduplication check:

```python
if (existing_tx.uid == tx.uid
    and existing_tx.tx_type == tx.tx_type
    and existing_tx.requester == tx.requester):
    return False
```

---

### VULN-13 — Low: Block Timestamps Not Validated Against Wall Clock

**File:** `blockchain/blockchain.py`
**Location:** `integrity_check()` (lines 981–1010)

#### Description

`integrity_check()` only enforces that block timestamps are monotonically non-decreasing. It does not validate timestamps against real wall-clock time. A miner can set a block timestamp arbitrarily far in the future.

#### Attack Scenarios

**Future timestamp griefing:** A miner publishes a block with timestamp `now + 1 year`. Honest nodes adopt it (it's a longer valid chain). Now any new block must also have a timestamp ≥ that future value, effectively preventing other nodes from mining until their system clocks catch up.

**Past timestamp manipulation:** Artificially old timestamps affect item reservation time tracking (`item_request_times`), potentially bypassing time-based logic.

#### Recommended Fix

In `integrity_check()` (and `replace_chain()`), reject any block whose timestamp is more than a reasonable tolerance (e.g., 2 minutes) ahead of local wall clock time:

```python
import time
MAX_FUTURE_SECONDS = 120
if blk.timestamp > time.time() + MAX_FUTURE_SECONDS:
    return False
```

---

### VULN-14 — Low: Genesis Credits Are Permanently Inaccessible

**File:** `blockchain/blockchain.py`
**Location:** `genesis()` (lines 329–346)

#### Description

The genesis block creates 100 credits (`GENESIS_CREDITS`) using a randomly generated throwaway private key that is immediately discarded. These credits are permanently locked — no one can ever spend them — but they appear in the chain and inflate the perceived total credit supply.

#### Vulnerable Code (lines 333–342)

```python
genesis_key = ec.generate_private_key(ec.SECP256R1()).public_key()
genesis_tx = Transaction(
    genesis_key,
    uid="GENESIS",
    tx_type=TxTypes.COINBASE,
    amount=GENESIS_CREDITS      # 100 credits created for a key nobody holds
)
# genesis_key private key is never saved — credits are irrecoverable
```

#### Impact

- `GENESIS_CREDITS = 100` credits exist on-chain but can never be spent.
- Balance accounting (total supply) is permanently off by 100.
- If the network scales, this creates confusing discrepancies in auditing total credit supply.

#### Recommended Fix

Either assign genesis credits to a known key (the node's own key, or a designated bootstrap key), or set `GENESIS_CREDITS = 0` and rely solely on mining rewards for credit creation.

---

## Summary

| ID | Severity | Location | Description |
|----|----------|----------|-------------|
| VULN-1 | **Critical** | `blockchain.py:514, 654, 940` | RELEASE does not verify item ownership |
| VULN-2 | **Critical** | `network.py:151–192` | P2P unencrypted; `CryptKeeper` unused |
| VULN-3 | **High** | `blockchain.py:138–145` | TRANSFER amount/recipient excluded from signature |
| VULN-4 | **High** | `blockchain.py:484–489` | `dict.add()` crash bug in mempool validation |
| VULN-5 | **High** | `blockchain.py:264, 432` | PoW difficulty=2 trivially weak; enables 51% attack |
| VULN-6 | **High** | `blockchain.py:1049–1051` | `repair()` ignores genesis corruption (`not 0` bug) |
| VULN-7 | **Medium** | `blockchain.py:442–535` | No mempool size limit; memory exhaustion |
| VULN-8 | **Medium** | `network.py:151`, `electron_backend.py` | No rate limiting on P2P or API |
| VULN-9 | **Medium** | `blockchain.py:49–50, 621–672` | Float precision loses credits in escrow |
| VULN-10 | **Medium** | `blockchain.py:743–883` | Dead code references undefined `calculate_release_refund` |
| VULN-11 | **Low** | `network.py:198–203` | Full peer list disclosed on connect |
| VULN-12 | **Low** | `blockchain.py:467–471` | Mempool dedup bypassed by timestamp variation |
| VULN-13 | **Low** | `blockchain.py:981–1010` | Future block timestamps not validated |
| VULN-14 | **Low** | `blockchain.py:329–346` | Genesis credits permanently inaccessible |

---

*End of report.*
