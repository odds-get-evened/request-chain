# Flask web UI for the lightweight blockchain with live streaming (SSE)
# Adds a /stream endpoint that pushes updates whenever chain/pool/state changes.
# Run: python app.py
from flask import Flask, jsonify, request, render_template, send_from_directory, Response, stream_with_context
from pathlib import Path
import json
import time
from datetime import datetime
import threading
import queue

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import blockchain  # local module from blockchain.py

# application paths and globals
APP_DIR = Path(__file__).parent
CHAIN_PATH = Path.home().joinpath('.databox', 'material', 'blx.pkl')

app = Flask(__name__, static_folder=str(APP_DIR / "static"), template_folder=str(APP_DIR / "templates"))

# Load or create blockchain instance
chain = blockchain.Blockchain.init(CHAIN_PATH, difficulty=2)

# In-memory transaction pool (transactions waiting to be mined)
tx_pool: list[blockchain.Transaction] = []

# Subscribers for Server-Sent Events (SSE). Each subscriber is a queue.Queue.
_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()


def register_subscriber() -> queue.Queue:
    """Create and register a new subscriber queue, thread-safe."""
    q = queue.Queue(maxsize=32)
    with _subscribers_lock:
        _subscribers.append(q)
    return q


def unregister_subscriber(q: queue.Queue):
    """Remove subscriber queue, thread-safe."""
    with _subscribers_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def notify_subscribers(event: str, payload: dict):
    """
    Put an update into every subscriber queue. Non-blocking: if a queue is full we drop the message for that subscriber.
    The payload will be JSON-serialized by the SSE generator.
    """
    data = {"event": event, "payload": payload}
    with _subscribers_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(data)
            except queue.Full:
                # slow consumer, drop this update for that subscriber
                continue


def _build_broadcast_payload() -> dict:
    """
    Aggregate chain, summary and pool into a simple dict used by the UI for live updates.
    Uses to_full_dict() for blocks to include signatures and easier client display.
    """
    blocks = [b.to_full_dict() for b in chain.chain]
    # summary: small metrics for charts
    txs_per_block = [len(b["transactions"]) for b in blocks]
    block_indexes = [b["index"] for b in blocks]
    block_time_labels = [datetime.utcfromtimestamp(float(b["timestamp"])).isoformat() + "Z" for b in blocks]
    allocated = list(chain.allocation())
    available = list(chain.get_available())
    summary = {
        "chain_length": len(blocks),
        "difficulty": chain.difficulty,
        "allocated_count": len(allocated),
        "available_count": len(available),
        "txs_per_block": txs_per_block,
        "block_indexes": block_indexes,
        "block_time_labels": block_time_labels
    }
    stats = {
        "allocated": allocated,
        "available": available,
        "integrity_ok": chain.integrity_check(),
        "bad_block_index": chain.find_bad_block()
    }
    pool = [tx.to_full_dict() for tx in tx_pool]
    return {"summary": summary, "chain": blocks, "stats": stats, "pool": pool}


@app.route("/")
def index():
    """Serve the visual UI page."""
    return render_template("index.html")


# Static files route (CSS/JS)
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(str(APP_DIR / "static"), filename)


@app.route("/api/generate_key", methods=["POST"])
def api_generate_key():
    """Generate EC keypair (P-256) and return PEM + compressed pubkey hex."""
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    pubhex = blockchain.serialize_pubkey(priv.public_key())
    return jsonify({"privkey_pem": pem, "pubkey_hex": pubhex})


@app.route("/api/create_tx", methods=["POST"])
def api_create_tx():
    """
    Create and sign a transaction using provided private key PEM.
    Body JSON: { "privkey_pem": "...", "uid": "item1", "type": 1 }
    Notify subscribers after adding to pool.
    """
    data = request.get_json() or {}
    pem = data.get("privkey_pem")
    uid = data.get("uid")
    tx_type = int(data.get("type", blockchain.TxTypes.REQUEST))

    if not pem or not uid:
        return jsonify({"error": "privkey_pem and uid are required"}), 400

    try:
        priv = serialization.load_pem_private_key(pem.encode(), password=None)
    except Exception as e:
        return jsonify({"error": f"invalid private key: {e}"}), 400

    pub = priv.public_key()
    tx = blockchain.Transaction(pub, uid, tx_type)
    tx.sign(priv)

    # append to pool and notify subscribers for live updates
    tx_pool.append(tx)
    notify_subscribers("pool_updated", _build_broadcast_payload())

    return jsonify({"tx": tx.to_full_dict()})


@app.route("/api/pool", methods=["GET"])
def api_pool():
    """Return the current transaction pool (full dicts including signatures)."""
    return jsonify({"tx_pool": [tx.to_full_dict() for tx in tx_pool]})


@app.route("/api/clear_pool", methods=["POST"])
def api_clear_pool():
    tx_pool.clear()
    notify_subscribers("pool_cleared", _build_broadcast_payload())
    return jsonify({"ok": True})


@app.route("/api/add_block", methods=["POST"])
def api_add_block():
    """
    Mine & add a block containing transactions in tx_pool (or provided txs).
    Notify subscribers after successful append.
    """
    data = request.get_json() or {}

    incoming = data.get("txs")
    if incoming:
        txs = []
        try:
            for d in incoming:
                pub_hex = d["requester"]
                uid = d["uid"]
                tx_type = int(d["type"])
                ts = float(d.get("timestamp", time.time()))
                sig = d.get("signature")
                pub = blockchain.deserialize_pubkey(pub_hex)
                tx = blockchain.Transaction(pub, uid, tx_type, ts=ts, sig=sig)
                txs.append(tx)
        except Exception as e:
            return jsonify({"error": f"bad tx format: {e}"}), 400
    else:
        if not tx_pool:
            return jsonify({"error": "no transactions in pool"}), 400
        txs = tx_pool.copy()

    # try to add block
    try:
        chain.add_block(txs)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # Clear pool on successful mining and persist chain, then notify subscribers
    tx_pool.clear()
    chain.snapshot(CHAIN_PATH)
    notify_subscribers("block_added", _build_broadcast_payload())
    return jsonify({"ok": True, "chain_length": len(chain.chain)})


@app.route("/api/chain", methods=["GET"])
def api_chain():
    """Return the entire chain: blocks include transactions with signatures."""
    return jsonify({"chain": [b.to_full_dict() for b in chain.chain], "difficulty": chain.difficulty, "length": len(chain.chain)})


@app.route("/api/summary", methods=["GET"])
def api_summary():
    """Return summarized metrics for charts used by the UI."""
    payload = _build_broadcast_payload()
    return jsonify(payload["summary"])


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Return allocation and available sets and integrity info (used by UI)."""
    allocated = list(chain.allocation())
    available = list(chain.get_available())
    integrity = chain.integrity_check()
    bad_idx = chain.find_bad_block()
    return jsonify({"allocated": allocated, "available": available, "integrity_ok": integrity, "bad_block_index": bad_idx})


@app.route("/api/repair", methods=["POST"])
def api_repair():
    """Attempt to repair the chain and persist if repaired, then notify subscribers."""
    repaired = chain.repair()
    if repaired:
        chain.snapshot(CHAIN_PATH)
    notify_subscribers("repaired", _build_broadcast_payload())
    return jsonify({"repaired": repaired})


@app.route("/api/save", methods=["POST"])
def api_save():
    chain.snapshot(CHAIN_PATH)
    notify_subscribers("saved", _build_broadcast_payload())
    return jsonify({"saved": True})


@app.route("/api/load", methods=["POST"])
def api_load():
    """Reload chain from disk (if present) and notify subscribers."""
    global chain
    try:
        chain = blockchain.Blockchain.init(CHAIN_PATH)
        notify_subscribers("loaded", _build_broadcast_payload())
        return jsonify({"loaded": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/corrupt_block", methods=["POST"])
def api_corrupt_block():
    """
    Intentionally corrupt a block (for demos).
    Body: { "index": 1, "field": "nonce", "value": 9999 }
    Notify subscribers so UI will show integrity failure.
    """
    data = request.get_json() or {}
    idx = int(data.get("index", -1))
    if idx <= 0 or idx >= len(chain.chain):
        return jsonify({"error": "invalid index; cannot corrupt genesis or out-of-range"}), 400

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

    # intentionally avoid recomputing hash so integrity breaks
    chain.snapshot(CHAIN_PATH)
    notify_subscribers("corrupted", _build_broadcast_payload())
    return jsonify({"ok": True, "message": "block corrupted"})


@app.route("/stream")
def stream():
    """
    SSE endpoint: clients connect here to receive 'update' events containing the latest
    summary, chain, stats and pool data. Each client gets its own queue.
    """
    q = register_subscriber()

    def event_stream(q_local: queue.Queue):
        try:
            # Immediately send initial state so clients don't wait for changes
            initial = _build_broadcast_payload()
            yield f"event: update\ndata: {json.dumps(initial)}\n\n"
            # Keep streaming updates from the queue
            while True:
                try:
                    item = q_local.get(timeout=15)  # wait for next update or heartbeat
                    # SSE event named 'update'
                    yield f"event: update\ndata: {json.dumps(item['payload'])}\n\n"
                except queue.Empty:
                    # send a heartbeat comment to keep connection alive
                    yield ": heartbeat\n\n"
        finally:
            # Ensure we unregister when client disconnects
            unregister_subscriber(q_local)

    # Use stream_with_context to keep request context while streaming
    return Response(stream_with_context(event_stream(q)), mimetype="text/event-stream")


if __name__ == "__main__":
    # Run the Flask dev server (sufficient for demo). For production, use a WSGI server that supports long-lived responses.
    app.run(debug=True, threaded=True, host="127.0.0.1", port=5000)