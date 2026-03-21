import base64
import json
import socket
import threading
import time
from typing import Set, Callable, Dict, Any
from dataclasses import dataclass, asdict
from enum import StrEnum
from queue import Queue, Empty

from blockchain.security import CryptKeeper


class MessageType(StrEnum):
    HANDSHAKE = "handshake"       # Key-exchange frame (always plaintext)
    ENCRYPTED = "encrypted"       # Wrapper for AES-GCM encrypted payload
    PEER_ANNOUNCE = "peer_announce"
    PEER_LIST = "peer_list"
    REQUEST_CHAIN = "request_chain"
    CHAIN_RESPONSE = "chain_response"
    NEW_BLOCK = "new_block"
    NEW_TRANSACTION = "new_transaction"
    PING = "ping"
    PONG = "pong"


@dataclass
class Message:
    type: MessageType
    payload: Dict[Any, Any]
    sender: str = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(data: str) -> 'Message':
        d = json.loads(data)
        return Message(
            type=MessageType(d['type']),
            payload=d['payload'],
            sender=d.get('sender')
        )


class Peer:
    def __init__(self, host: str, port: int, sock: socket.socket = None):
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"
        self.socket = sock
        self.connected = sock is not None
        self.send_queue = Queue()
        self.lock = threading.Lock()

        # Per-peer ECDH state (VULN-2)
        self.peer_public_key = None          # Populated after HANDSHAKE
        self.handshake_done = threading.Event()  # Signalled when key exchange completes

        # Statistics
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.blocks_received = 0
        self.transactions_received = 0
        self.messages_sent = 0
        self.messages_received = 0

    def __hash__(self):
        return hash(self.address)

    def __eq__(self, other):
        return isinstance(other, Peer) and self.address == other.address

    def send(self, message: Message):
        """Queue message for sending"""
        self.send_queue.put(message)
        self.messages_sent += 1
        self.last_seen = time.time()

    def record_message_received(self):
        """Record that a message was received"""
        self.messages_received += 1
        self.last_seen = time.time()

    def close(self):
        """Close peer connection"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self.connected = False


MAX_PEERS = 64  # Hard cap on simultaneous connections
_HANDSHAKE_TIMEOUT = 30  # Seconds to wait for peer's HANDSHAKE before dropping message


class P2PNetwork:
    def __init__(self, host: str = "0.0.0.0", port: int = 6000):
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"
        self.peers: Set[Peer] = set()
        self.peers_lock = threading.Lock()
        self.server_socket = None
        self.running = False

        # Per-node ECDH identity used for all peer sessions (VULN-2)
        self.crypt_keeper = CryptKeeper()

        # Callbacks for handling messages
        self.on_new_block: Callable = None
        self.on_new_transaction: Callable = None
        self.on_chain_request: Callable = None
        self.on_chain_response: Callable = None

    def start(self):
        """Start the P2P server"""
        if self.running:
            return

        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)

        # Start accepting connections
        threading.Thread(target=self._accept_connections, daemon=True).start()
        print(f"🌐 P2P server running on {self.host}:{self.port}")

    def _accept_connections(self):
        """Accept incoming peer connections"""
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()

                # Enforce connection cap to prevent resource-exhaustion DoS
                with self.peers_lock:
                    if len(self.peers) >= MAX_PEERS:
                        client_sock.close()
                        print(f"⚠️  Rejected connection from {addr}: peer limit ({MAX_PEERS}) reached")
                        continue

                print(f"✅ Incoming connection from {addr}")

                # Create peer and start handlers
                peer = Peer(addr[0], addr[1], client_sock)
                with self.peers_lock:
                    self.peers.add(peer)

                # Initiate key exchange: server sends its public key first (VULN-2)
                self._queue_handshake(peer)

                threading.Thread(target=self._handle_peer, args=(peer,), daemon=True).start()
                threading.Thread(target=self._send_handler, args=(peer,), daemon=True).start()

            except Exception as e:
                if self.running:
                    print(f"❌ Accept error: {e}")

    # Maximum buffered bytes per peer before the connection is dropped
    _MAX_BUFFER = 4 * 1024 * 1024  # 4 MB

    def _handle_peer(self, peer: Peer):
        """Handle messages from a peer"""
        buffer = ""
        try:
            while self.running and peer.connected:
                data = peer.socket.recv(4096).decode('utf-8', errors='replace')
                if not data:
                    break

                buffer += data

                # Drop peers that send oversized messages (DoS protection)
                if len(buffer) > self._MAX_BUFFER:
                    print(f"⚠️  Dropping peer {peer.address}: message buffer exceeded {self._MAX_BUFFER} bytes")
                    break

                # Process complete messages (newline-delimited)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            msg = Message.from_json(line)
                            self._route_message(msg, peer)
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"❌ Error handling peer {peer.address}: {e}")
        finally:
            self._disconnect_peer(peer)

    def _send_handler(self, peer: Peer):
        """Handle outgoing messages to a peer"""
        while self.running and peer.connected:
            try:
                msg = peer.send_queue.get(timeout=1)

                if msg.type == MessageType.HANDSHAKE:
                    # Handshake frames are always sent as plaintext (VULN-2)
                    data = msg.to_json() + '\n'
                    peer.socket.sendall(data.encode('utf-8'))
                    continue

                # All other messages must be encrypted (VULN-2).
                # Wait until the peer has sent us their public key.
                if not peer.handshake_done.wait(timeout=_HANDSHAKE_TIMEOUT):
                    print(f"⚠️  Handshake timeout with {peer.address}, dropping queued message")
                    continue

                nonce, ciphertext = self.crypt_keeper.encrypt(
                    msg.to_json().encode('utf-8'), peer.peer_public_key
                )
                encrypted_msg = Message(MessageType.ENCRYPTED, {
                    'nonce': base64.b64encode(nonce).decode(),
                    'data': base64.b64encode(ciphertext).decode()
                }, self.address)
                data = encrypted_msg.to_json() + '\n'
                peer.socket.sendall(data.encode('utf-8'))

            except Empty:
                continue
            except Exception as e:
                print(f"❌ Send error to {peer.address}: {e}")
                break

    def _route_message(self, msg: Message, peer: Peer):
        """Route message to appropriate handler"""
        peer.record_message_received()

        # --- Key-exchange frame (always plaintext) ---
        if msg.type == MessageType.HANDSHAKE:
            try:
                peer_pub_pem = base64.b64decode(msg.payload['pubkey'])
                peer.peer_public_key = self.crypt_keeper.load_peer_public_key(peer_pub_pem)
                peer.handshake_done.set()
            except Exception as e:
                print(f"❌ Handshake failed with {peer.address}: {e}")
                self._disconnect_peer(peer)
            return

        # --- Encrypted wrapper: decrypt then dispatch inner message ---
        if msg.type == MessageType.ENCRYPTED:
            if peer.peer_public_key is None:
                print(f"⚠️  Encrypted message from {peer.address} before handshake; dropping")
                return
            try:
                nonce = base64.b64decode(msg.payload['nonce'])
                ciphertext = base64.b64decode(msg.payload['data'])
                plaintext = self.crypt_keeper.decrypt(nonce, ciphertext, peer.peer_public_key)
                inner_msg = Message.from_json(plaintext.decode('utf-8'))
                # Dispatch the decrypted inner message directly (HANDSHAKE/ENCRYPTED nesting
                # is not valid, so those types are silently ignored here)
                if inner_msg.type not in (MessageType.HANDSHAKE, MessageType.ENCRYPTED):
                    self._dispatch_message(inner_msg, peer)
            except Exception as e:
                print(f"❌ Decryption failed from {peer.address}: {e}")
            return

        # --- Plaintext non-handshake messages ---
        # Accept them only before the handshake is complete (legacy / pre-handshake window).
        # After a successful handshake every application message must be encrypted.
        if peer.handshake_done.is_set():
            print(f"⚠️  Plaintext application message from {peer.address} after handshake; dropping")
            return

        self._dispatch_message(msg, peer)

    def _dispatch_message(self, msg: Message, peer: Peer):
        """Dispatch an already-authenticated (decrypted) application message."""
        if msg.type == MessageType.PEER_ANNOUNCE:
            # Send back our peer list
            with self.peers_lock:
                peer_list = [p.address for p in self.peers if p != peer]
            response = Message(MessageType.PEER_LIST, {"peers": peer_list}, self.address)
            peer.send(response)

        elif msg.type == MessageType.REQUEST_CHAIN:
            # Callback to get chain data
            if self.on_chain_request:
                chain_data = self.on_chain_request()
                response = Message(MessageType.CHAIN_RESPONSE, chain_data, self.address)
                peer.send(response)

        elif msg.type == MessageType.CHAIN_RESPONSE:
            # Callback to handle chain response
            if self.on_chain_response:
                self.on_chain_response(msg.payload)

        elif msg.type == MessageType.NEW_BLOCK:
            peer.blocks_received += 1
            # Callback to handle new block
            if self.on_new_block:
                self.on_new_block(msg.payload)

        elif msg.type == MessageType.NEW_TRANSACTION:
            peer.transactions_received += 1
            # Callback to handle new transaction
            if self.on_new_transaction:
                self.on_new_transaction(msg.payload)

        elif msg.type == MessageType.PING:
            response = Message(MessageType.PONG, {}, self.address)
            peer.send(response)

    def _queue_handshake(self, peer: Peer):
        """Queue our ECDH public key for sending to the peer (VULN-2)."""
        pubkey_pem = self.crypt_keeper.get_serialized_public_key()
        handshake_msg = Message(MessageType.HANDSHAKE, {
            "pubkey": base64.b64encode(pubkey_pem).decode()
        }, self.address)
        peer.send(handshake_msg)

    def connect_to_peer(self, host: str, port: int):
        """Connect to a peer node"""
        threading.Thread(target=self._connect_peer, args=(host, port), daemon=True).start()

    def _connect_peer(self, host: str, port: int):
        """Connect to peer (threaded)"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))

            peer = Peer(host, port, sock)
            with self.peers_lock:
                self.peers.add(peer)

            # Start handlers first so the send queue is drained immediately
            threading.Thread(target=self._handle_peer, args=(peer,), daemon=True).start()
            threading.Thread(target=self._send_handler, args=(peer,), daemon=True).start()

            # Initiate key exchange, then announce ourselves (VULN-2)
            self._queue_handshake(peer)
            msg = Message(MessageType.PEER_ANNOUNCE, {}, self.address)
            peer.send(msg)

            print(f"🔗 Connected to peer: {host}:{port}")

        except Exception as e:
            print(f"❌ Failed to connect to {host}:{port}: {e}")

    def _disconnect_peer(self, peer: Peer):
        """Remove disconnected peer"""
        with self.peers_lock:
            self.peers.discard(peer)
        peer.close()
        print(f"❌ Peer disconnected: {peer.address}")

    def broadcast(self, msg: Message):
        """Broadcast message to all peers"""
        msg.sender = self.address
        with self.peers_lock:
            for peer in list(self.peers):
                if peer.connected:
                    peer.send(msg)

    def request_chain_from_peers(self):
        """Request full chain from all peers"""
        msg = Message(MessageType.REQUEST_CHAIN, {}, self.address)
        self.broadcast(msg)

    def announce_new_block(self, block_data: dict):
        """Broadcast new block to network"""
        msg = Message(MessageType.NEW_BLOCK, block_data, self.address)
        self.broadcast(msg)

    def announce_new_transaction(self, tx_data: dict):
        """Broadcast new transaction to network"""
        msg = Message(MessageType.NEW_TRANSACTION, tx_data, self.address)
        self.broadcast(msg)

    def stop(self):
        """Stop the P2P server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        with self.peers_lock:
            for peer in list(self.peers):
                peer.close()
