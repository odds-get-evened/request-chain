import json
import socket
import threading
import time
from typing import Set, Callable, Dict, Any
from dataclasses import dataclass, asdict
from enum import StrEnum
from queue import Queue, Empty


class MessageType(StrEnum):
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


class P2PNetwork:
    def __init__(self, host: str = "0.0.0.0", port: int = 6000):
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"
        self.peers: Set[Peer] = set()
        self.peers_lock = threading.Lock()
        self.server_socket = None
        self.running = False

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
                print(f"✅ Incoming connection from {addr}")

                # Create peer and start handlers
                peer = Peer(addr[0], addr[1], client_sock)
                with self.peers_lock:
                    self.peers.add(peer)

                threading.Thread(target=self._handle_peer, args=(peer,), daemon=True).start()
                threading.Thread(target=self._send_handler, args=(peer,), daemon=True).start()

            except Exception as e:
                if self.running:
                    print(f"❌ Accept error: {e}")

    def _handle_peer(self, peer: Peer):
        """Handle messages from a peer"""
        buffer = ""
        try:
            while self.running and peer.connected:
                data = peer.socket.recv(4096).decode('utf-8')
                if not data:
                    break

                buffer += data
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
                data = msg.to_json() + '\n'
                peer.socket.sendall(data.encode('utf-8'))
            except Empty:
                continue
            except Exception as e:
                print(f"❌ Send error to {peer.address}: {e}")
                break

    def _route_message(self, msg: Message, peer: Peer):
        """Route message to appropriate handler"""
        peer.record_message_received()

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

            # Announce ourselves
            msg = Message(MessageType.PEER_ANNOUNCE, {}, self.address)
            peer.send(msg)

            # Start handlers
            threading.Thread(target=self._handle_peer, args=(peer,), daemon=True).start()
            threading.Thread(target=self._send_handler, args=(peer,), daemon=True).start()

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