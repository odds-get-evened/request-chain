"""
Electron backend: Flask server with full P2P integration.
Merges peer_ui.py logic (P2P callbacks, background threads, batch signing)
with the web UI's REST/SSE API surface.

Run: python electron_backend.py [p2p_port]   (default: 6000)
Flask listens on 127.0.0.1:5000
"""
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')
import json
import time
import threading
import queue
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, Response, stream_with_context, send_from_directory
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# ── Blockchain imports (unchanged package) ────────────────────────────────────
from blockchain.blockchain import (
    Blockchain, Block, Transaction, TxTypes, ITEM_REQUEST_COST, MINING_REWARD,
    serialize_pubkey, deserialize_pubkey, validate_uid,
    calculate_penalty_amount, calculate_demand_percentage,
)
from blockchain.network import P2PNetwork, Message, MessageType

# ── Paths ──────────────────────────────────────────────────────────────────────
CHAIN_PATH = Path.home() / '.databox' / 'material' / 'blx.json'
CHAIN_PATH.parent.mkdir(parents=True, exist_ok=True)

RENDERER_DIR = Path(__file__).parent / 'electron' / 'renderer'

# ── Flask app ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(RENDERER_DIR), static_url_path='')

# ── Node identity (generated once at startup) ─────────────────────────────────
_priv_key = ec.generate_private_key(ec.SECP256R1())
_pub_key = _priv_key.public_key()
_node_pubkey_hex = serialize_pubkey(_pub_key)

# ── Blockchain state ───────────────────────────────────────────────────────────
chain: Blockchain = Blockchain.init(CHAIN_PATH, difficulty=2) or Blockchain(difficulty=2)

# ── P2P network ───────────────────────────────────────────────────────────────
_p2p_port = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
p2p = P2PNetwork(host="0.0.0.0", port=_p2p_port)

# ── Thread safety ─────────────────────────────────────────────────────────────
_chain_lock = threading.Lock()

# ── Activity log (capped deque, typed entries) ────────────────────────────────
_activity_log: deque = deque(maxlen=200)
_activity_lock = threading.Lock()

# ── Balance history for sparkline ─────────────────────────────────────────────
_balance_history: list = []          # list of [timestamp, balance]
_balance_lock = threading.Lock()

# ── Mining state ──────────────────────────────────────────────────────────────
_mine_executor = ThreadPoolExecutor(max_workers=1)
_mining_in_progress = threading.Event()
_auto_mining_enabled = threading.Event()

# ── SSE subscribers ───────────────────────────────────────────────────────────
_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log(log_type: str, message: str):
    entry = {"ts": time.time(), "type": log_type, "message": message}
    with _activity_lock:
        _activity_log.append(entry)
    notify_subscribers("log_entry", {"entry": entry})


def _record_balance():
    bal = chain.get_balance(_node_pubkey_hex)
    ts = time.time()
    with _balance_lock:
        _balance_history.append([ts, bal])
        if len(_balance_history) > 200:
            _balance_history.pop(0)


def _peer_list() -> list:
    with p2p.peers_lock:
        peers = list(p2p.peers)
    result = []
    for peer in peers:
        uptime = time.time() - peer.connected_at
        result.append({
            "address": peer.address,
            "connected": peer.connected,
            "last_seen": peer.last_seen,
            "blocks_received": peer.blocks_received,
            "transactions_received": peer.transactions_received,
            "messages_sent": peer.messages_sent,
            "messages_received": peer.messages_received,
            "uptime_seconds": int(uptime),
        })
    return result


def _items_payload() -> dict:
    allocated = chain.allocation()
    available = list(chain.get_available())
    reserved = []
    for uid, holder in allocated.items():
        reserved.append({
            "uid": uid,
            "holder": holder,
            "holder_short": holder[:12] + "…" if len(holder) > 12 else holder,
            "is_mine": holder == _node_pubkey_hex,
            "value": chain.item_values.get(uid, ITEM_REQUEST_COST),
            "demand": chain.item_demand_counters.get(uid, 0),
            "escrow": chain.item_escrow.get(uid, 0.0),
        })
    avail_list = []
    for uid in available:
        avail_list.append({
            "uid": uid,
            "value": chain.item_values.get(uid, ITEM_REQUEST_COST),
            "demand": chain.item_demand_counters.get(uid, 0),
            "escrow": 0.0,
        })
    return {"reserved": reserved, "available": avail_list}


def _build_broadcast_payload() -> dict:
    blocks = [b.to_full_dict() for b in chain.chain]
    txs_per_block = [len(b["transactions"]) for b in blocks]
    block_indexes = [b["index"] for b in blocks]
    block_time_labels = [
        datetime.fromtimestamp(float(b["timestamp"]), tz=timezone.utc).isoformat()
        for b in blocks
    ]
    allocated = chain.allocation()
    available = list(chain.get_available())

    # Count tx types across entire chain for donut chart
    type_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for b in blocks:
        for tx in b.get("transactions", []):
            t = int(tx.get("type", 0))
            if t in type_counts:
                type_counts[t] += 1

    summary = {
        "chain_length": len(blocks),
        "difficulty": chain.difficulty,
        "allocated_count": len(allocated),
        "available_count": len(available),
        "txs_per_block": txs_per_block,
        "block_indexes": block_indexes,
        "block_time_labels": block_time_labels,
        "tx_type_counts": type_counts,
        "mempool_size": len(chain.mempool),
        "mining_in_progress": _mining_in_progress.is_set(),
        "auto_mining": _auto_mining_enabled.is_set(),
    }
    stats = {
        "allocated": list(allocated.keys()),
        "available": available,
        "integrity_ok": chain.integrity_check(),
        "bad_block_index": chain.find_bad_block(),
    }
    with _activity_lock:
        log_entries = list(_activity_log)[-50:]
    with _balance_lock:
        bal_hist = list(_balance_history)

    return {
        "summary": summary,
        "chain": blocks,
        "stats": stats,
        "pool": [tx.to_full_dict() for tx in chain.mempool],
        "peers": _peer_list(),
        "node": {
            "pubkey_hex": _node_pubkey_hex,
            "pubkey_short": _node_pubkey_hex[:16] + "…",
            "balance": chain.get_balance(_node_pubkey_hex),
            "port": _p2p_port,
        },
        "items": _items_payload(),
        "balance_history": bal_hist,
        "activity_log": log_entries,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SSE
# ─────────────────────────────────────────────────────────────────────────────

def _register_subscriber() -> queue.Queue:
    q = queue.Queue(maxsize=32)
    with _subscribers_lock:
        _subscribers.append(q)
    return q


def _unregister_subscriber(q: queue.Queue):
    with _subscribers_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def notify_subscribers(event: str, payload: dict):
    data = json.dumps({"event": event, "payload": payload})
    with _subscribers_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait({"event": event, "data": data})
            except queue.Full:
                pass


@app.route("/stream")
def stream():
    q = _register_subscriber()

    def event_gen(q_local):
        try:
            initial = _build_broadcast_payload()
            yield f"event: initial_state\ndata: {json.dumps(initial)}\n\n"
            while True:
                try:
                    item = q_local.get(timeout=15)
                    yield f"event: {item['event']}\ndata: {item['data']}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            _unregister_subscriber(q_local)

    return Response(
        stream_with_context(event_gen(q)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# P2P callbacks
# ─────────────────────────────────────────────────────────────────────────────

def _setup_network_callbacks():
    def handle_new_transaction(tx_data: dict):
        try:
            pub = deserialize_pubkey(tx_data['requester'])
            tx = Transaction(
                pub,
                tx_data['uid'],
                tx_data['type'],
                tx_data.get('timestamp'),
                tx_data.get('signature'),
                tx_data.get('amount', 0.0),
                tx_data.get('recipient'),
                tx_data.get('accepted_offer'),
            )
            with _chain_lock:
                added = chain.add_to_mempool(tx)
            if added:
                label = {0: "COINBASE", 1: "REQUEST", 2: "RELEASE", 3: "TRANSFER", 4: "BUYOUT"}.get(
                    int(tx_data['type']), "UNKNOWN")
                _log("tx", f"📨 Received {label}: {tx_data['uid']}")
                notify_subscribers("tx_added", _build_broadcast_payload())
        except Exception as e:
            _log("system", f"❌ Bad transaction from peer: {e}")

    def handle_new_block(block_data: dict):
        try:
            txs = []
            for tx_dict in block_data.get('transactions', []):
                pub = deserialize_pubkey(tx_dict['requester'])
                tx = Transaction(
                    pub,
                    tx_dict['uid'],
                    tx_dict['type'],
                    tx_dict.get('timestamp'),
                    tx_dict.get('signature'),
                    tx_dict.get('amount', 0.0),
                    tx_dict.get('recipient'),
                    tx_dict.get('accepted_offer'),
                )
                txs.append(tx)

            with _chain_lock:
                if len(chain.chain) == block_data['index']:
                    chain.add_block(txs)
                    chain.clear_mempool_transactions(txs)
                    chain.snapshot(CHAIN_PATH)

            _log("block", f"📦 Received block #{block_data['index']} from peer")
            _record_balance()
            notify_subscribers("block_added", _build_broadcast_payload())
        except Exception as e:
            _log("system", f"❌ Bad block from peer: {e}")

    def handle_chain_request():
        with _chain_lock:
            return {
                'chain': [b.to_full_dict() for b in chain.chain],
                'length': len(chain.chain),
            }

    def handle_chain_response(response_data: dict):
        try:
            peer_chain = response_data.get('chain', [])
            peer_length = response_data.get('length', 0)
            _log("network", f"📡 Received chain ({peer_length} blocks) vs ours ({len(chain.chain)})")
            with _chain_lock:
                replaced = chain.replace_chain(peer_chain)
            if replaced:
                chain.snapshot(CHAIN_PATH)
                _log("network", f"✅ Adopted longer chain ({peer_length} blocks)")
                _record_balance()
                notify_subscribers("chain_replaced", _build_broadcast_payload())
            else:
                msg = "❌ Peer chain failed validation" if peer_length > len(chain.chain) else "ℹ️ Kept current chain"
                _log("network", msg)
        except Exception as e:
            _log("system", f"❌ Chain response error: {e}")

    p2p.on_new_transaction = handle_new_transaction
    p2p.on_new_block = handle_new_block
    p2p.on_chain_request = handle_chain_request
    p2p.on_chain_response = handle_chain_response


# ─────────────────────────────────────────────────────────────────────────────
# Background threads
# ─────────────────────────────────────────────────────────────────────────────

def _start_background_tasks():
    def integrity_monitor():
        last_ok = None
        while True:
            with _chain_lock:
                ok = chain.integrity_check()
                if not ok:
                    repaired = chain.repair()
                else:
                    repaired = False
            if last_ok is None or ok != last_ok:
                if ok:
                    _log("system", "😁 Chain integrity: OK")
                else:
                    if repaired:
                        _log("system", "✅ Corruption detected and repaired")
                    else:
                        _log("system", "❌ Corruption detected, repair failed")
                last_ok = ok
                notify_subscribers("integrity_update", _build_broadcast_payload())
            time.sleep(10)

    def status_updater():
        while True:
            _record_balance()
            notify_subscribers("status_update", _build_broadcast_payload())
            time.sleep(5)

    def auto_sync():
        time.sleep(10)
        while True:
            with p2p.peers_lock:
                has_peers = len(p2p.peers) > 0
            if has_peers:
                p2p.request_chain_from_peers()
            time.sleep(30)

    def auto_mine_worker():
        while True:
            if _auto_mining_enabled.is_set() and not _mining_in_progress.is_set():
                with _chain_lock:
                    pool_size = len(chain.mempool)
                if pool_size > 0:
                    _mining_in_progress.set()
                    _mine_executor.submit(_do_mine)
                    time.sleep(5)
                else:
                    time.sleep(2)
            else:
                time.sleep(2)

    threading.Thread(target=integrity_monitor, daemon=True).start()
    threading.Thread(target=status_updater, daemon=True).start()
    threading.Thread(target=auto_sync, daemon=True).start()
    threading.Thread(target=auto_mine_worker, daemon=True).start()


def _do_mine():
    try:
        with _chain_lock:
            block = chain.mine_block(_pub_key)
        if block:
            tx_count = len(block.transactions) - 1
            coinbase_tx = block.transactions[0]
            escrow_fee = coinbase_tx.amount - MINING_REWARD
            if escrow_fee > 0:
                _log("block", f"⛏️ Mined block #{block.index} ({tx_count} txs) — reward: {MINING_REWARD} + {escrow_fee:.2f} escrow = {coinbase_tx.amount:.2f}")
            else:
                _log("block", f"⛏️ Mined block #{block.index} ({tx_count} txs) — reward: {MINING_REWARD} credits")
            p2p.announce_new_block(block.to_full_dict())
            chain.snapshot(CHAIN_PATH)
            _record_balance()
            notify_subscribers("block_added", _build_broadcast_payload())
        else:
            _log("system", "❌ No valid transactions to mine")
    except Exception as e:
        _log("system", f"❌ Mining failed: {e}")
    finally:
        _mining_in_progress.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Routes — static renderer
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(RENDERER_DIR), "index.html")


# ─────────────────────────────────────────────────────────────────────────────
# Routes — node info
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/ping")
def api_ping():
    return jsonify({"ok": True})


@app.route("/api/node")
def api_node():
    return jsonify({
        "pubkey_hex": _node_pubkey_hex,
        "pubkey_short": _node_pubkey_hex[:16] + "…",
        "balance": chain.get_balance(_node_pubkey_hex),
        "port": _p2p_port,
        "mempool_size": len(chain.mempool),
        "mining_in_progress": _mining_in_progress.is_set(),
        "auto_mining": _auto_mining_enabled.is_set(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Routes — chain
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/chain")
def api_chain():
    with _chain_lock:
        blocks = [b.to_full_dict() for b in chain.chain]
    return jsonify({"chain": blocks, "difficulty": chain.difficulty, "length": len(blocks)})


@app.route("/api/summary")
def api_summary():
    payload = _build_broadcast_payload()
    return jsonify(payload["summary"])


@app.route("/api/stats")
def api_stats():
    with _chain_lock:
        allocated = list(chain.allocation().keys())
        available = list(chain.get_available())
        ok = chain.integrity_check()
        bad = chain.find_bad_block()
    return jsonify({"allocated": allocated, "available": available, "integrity_ok": ok, "bad_block_index": bad})


@app.route("/api/repair", methods=["POST"])
def api_repair():
    with _chain_lock:
        repaired = chain.repair()
        if repaired:
            chain.snapshot(CHAIN_PATH)
    notify_subscribers("integrity_update", _build_broadcast_payload())
    return jsonify({"repaired": repaired})


@app.route("/api/save", methods=["POST"])
def api_save():
    chain.snapshot(CHAIN_PATH)
    return jsonify({"saved": True})


@app.route("/api/load", methods=["POST"])
def api_load():
    global chain
    try:
        with _chain_lock:
            chain = Blockchain.init(CHAIN_PATH)
        notify_subscribers("chain_replaced", _build_broadcast_payload())
        return jsonify({"loaded": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/corrupt_block", methods=["POST"])
def api_corrupt_block():
    data = request.get_json() or {}
    idx = int(data.get("index", -1))
    if idx <= 0 or idx >= len(chain.chain):
        return jsonify({"error": "invalid index"}), 400
    blk = chain.chain[idx]
    field = data.get("field", "nonce")
    value = data.get("value")
    if field == "nonce":
        blk.nonce = int(value)
    elif field == "prev_hash":
        blk.prev_hash = str(value)
    elif field == "timestamp":
        blk.timestamp = float(value)
    else:
        return jsonify({"error": "unsupported field"}), 400
    chain.snapshot(CHAIN_PATH)
    notify_subscribers("integrity_update", _build_broadcast_payload())
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# Routes — items
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/items")
def api_items():
    return jsonify(_items_payload())


@app.route("/api/items/<uid>/history")
def api_item_history(uid: str):
    history = []
    with _chain_lock:
        for block in chain.chain:
            for tx in block.transactions:
                if tx.uid == uid:
                    history.append({
                        "block_index": block.index,
                        "block_ts": block.timestamp,
                        "type": int(tx.tx_type),
                        "requester": tx.requester,
                        "requester_short": tx.requester[:12] + "…" if len(tx.requester) > 12 else tx.requester,
                        "is_mine": tx.requester == _node_pubkey_hex,
                        "amount": tx.amount,
                        "timestamp": tx.timestamp,
                    })
    return jsonify({"uid": uid, "history": history})


# ─────────────────────────────────────────────────────────────────────────────
# Routes — peers
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/peers")
def api_peers():
    return jsonify({"peers": _peer_list()})


@app.route("/api/peers/connect", methods=["POST"])
def api_peers_connect():
    data = request.get_json() or {}
    host = data.get("host", "").strip()
    port_str = data.get("port")
    if not host or not port_str:
        return jsonify({"error": "host and port required"}), 400
    try:
        port = int(port_str)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid port"}), 400
    p2p.connect_to_peer(host, port)
    _log("network", f"🔗 Connecting to {host}:{port}…")
    notify_subscribers("peer_connected", _build_broadcast_payload())
    return jsonify({"ok": True})


@app.route("/api/peers/sync", methods=["POST"])
def api_peers_sync():
    with p2p.peers_lock:
        has_peers = len(p2p.peers) > 0
    if not has_peers:
        return jsonify({"error": "no peers connected"}), 400
    p2p.request_chain_from_peers()
    _log("network", "📡 Manual chain sync requested")
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# Routes — mempool
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/pool")
def api_pool():
    return jsonify({"pool": [tx.to_full_dict() for tx in chain.mempool]})


@app.route("/api/pool/clear", methods=["POST"])
def api_pool_clear():
    with _chain_lock:
        chain.mempool.clear()
    notify_subscribers("pool_cleared", _build_broadcast_payload())
    return jsonify({"ok": True})


@app.route("/api/mempool/mine", methods=["POST"])
def api_mine():
    if _mining_in_progress.is_set():
        return jsonify({"error": "mining already in progress"}), 409
    if not chain.mempool:
        return jsonify({"error": "mempool is empty"}), 400
    _mining_in_progress.set()
    _mine_executor.submit(_do_mine)
    return jsonify({"status": "mining"})


@app.route("/api/mempool/auto_mine", methods=["POST"])
def api_auto_mine():
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", False))
    if enabled:
        _auto_mining_enabled.set()
        _log("system", "⚡ Auto-mining enabled")
    else:
        _auto_mining_enabled.clear()
        _log("system", "⚡ Auto-mining disabled")
    notify_subscribers("status_update", _build_broadcast_payload())
    return jsonify({"auto_mining": enabled})


# ─────────────────────────────────────────────────────────────────────────────
# Routes — batch
# ─────────────────────────────────────────────────────────────────────────────

def _compute_batch_preview(items: list) -> list:
    """Compute cost/refund for each batch item without mutating state."""
    allocation = chain.allocation()
    my_balance = chain.get_balance(_node_pubkey_hex)
    preview = []
    running_balance = my_balance

    for item in items:
        action = item.get("action", "REQUEST").upper()
        uid = item.get("uid", "")
        entry = {"action": action, "uid": uid}

        if action == "RELEASE":
            current_value = chain.item_values.get(uid, ITEM_REQUEST_COST)
            escrow_amount = chain.item_escrow.get(uid, 0.0)
            holder_share = escrow_amount * 0.6667
            total_refund = current_value + holder_share
            entry["cost_type"] = "refund"
            entry["amount"] = total_refund
            entry["detail"] = f"+{total_refund:.2f} credits ({current_value:.1f} value + {holder_share:.2f} escrow)"
            running_balance += total_refund
        else:  # REQUEST
            if uid not in allocation:
                entry["cost_type"] = "regular"
                entry["amount"] = -ITEM_REQUEST_COST
                entry["detail"] = f"-{ITEM_REQUEST_COST} credits"
                running_balance -= ITEM_REQUEST_COST
            else:
                current_value = chain.item_values.get(uid, ITEM_REQUEST_COST)
                demand_count = chain.item_demand_counters.get(uid, 0)
                if running_balance >= current_value:
                    entry["cost_type"] = "buyout"
                    entry["amount"] = -current_value
                    entry["detail"] = f"-{current_value:.2f} credits (buyout)"
                    running_balance -= current_value
                else:
                    penalty = calculate_penalty_amount(current_value, demand_count)
                    pct = calculate_demand_percentage(demand_count)
                    entry["cost_type"] = "penalty"
                    entry["amount"] = -penalty
                    entry["detail"] = f"-{penalty:.2f} credits ({pct * 100:.1f}% penalty)"
                    running_balance -= penalty

        entry["balance_after"] = running_balance
        preview.append(entry)

    return preview


@app.route("/api/batch/preview", methods=["POST"])
def api_batch_preview():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"preview": [], "total_cost": 0, "balance": chain.get_balance(_node_pubkey_hex)})
    preview = _compute_batch_preview(items)
    total = sum(e["amount"] for e in preview)
    return jsonify({
        "preview": preview,
        "total_cost": total,
        "balance": chain.get_balance(_node_pubkey_hex),
        "can_afford": chain.get_balance(_node_pubkey_hex) + total >= 0,
    })


@app.route("/api/batch/execute", methods=["POST"])
def api_batch_execute():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "no items"}), 400

    # Validate balance first
    preview = _compute_batch_preview(items)
    total_cost = sum(e["amount"] for e in preview)
    my_balance = chain.get_balance(_node_pubkey_hex)
    if my_balance + total_cost < 0:
        return jsonify({
            "error": "insufficient credits",
            "balance": my_balance,
            "total_cost": total_cost,
            "shortfall": abs(my_balance + total_cost),
        }), 400

    # Sign and broadcast
    broadcast_count = 0
    failed = []
    for item in items:
        action = item.get("action", "REQUEST").upper()
        uid = item.get("uid", "")
        if not validate_uid(uid):
            failed.append({"uid": uid, "reason": "invalid uid"})
            continue
        tx_type = TxTypes.REQUEST if action == "REQUEST" else TxTypes.RELEASE
        tx = Transaction(_pub_key, uid, tx_type=tx_type)
        tx.sign(_priv_key)
        with _chain_lock:
            added = chain.add_to_mempool(tx)
        if added:
            p2p.announce_new_transaction(tx.to_full_dict())
            broadcast_count += 1
            _log("tx", f"📤 Broadcast {action}: {uid}")
        else:
            failed.append({"uid": uid, "reason": "rejected by mempool"})

    if broadcast_count:
        _log("tx", f"✅ Broadcast {broadcast_count} transaction{'s' if broadcast_count != 1 else ''}")
        notify_subscribers("tx_added", _build_broadcast_payload())

    return jsonify({
        "broadcast": broadcast_count,
        "failed": failed,
        "mempool_size": len(chain.mempool),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────

def _shutdown():
    chain.snapshot(CHAIN_PATH)
    p2p.stop()
    print("Backend shut down cleanly.")


if __name__ == "__main__":
    import atexit
    atexit.register(_shutdown)

    _setup_network_callbacks()
    p2p.start()
    _log("system", f"🚀 Node started on P2P port {_p2p_port}")
    _log("system", f"🔑 Node key: {_node_pubkey_hex[:20]}…")
    _start_background_tasks()

    print(f"Flask backend starting on http://127.0.0.1:5000 (P2P: {_p2p_port})")
    app.run(debug=False, threaded=True, host="127.0.0.1", port=5000)
