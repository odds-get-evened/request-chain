# Blockchain P2P Network

Decentralized blockchain network using TCP sockets for peer-to-peer communication.

## Architecture

```
┌─────────┐      TCP Socket       ┌─────────┐
│ Node A  │◄────────────────────► │ Node B  │
│ :6000   │                       │ :6001   │
└────┬────┘                       └────┬────┘
     │                                 │
     │           ┌─────────┐          │
     └──────────►│ Node C  │◄─────────┘
                 │ :6002   │
                 └─────────┘
```

## Components

**P2PNetwork** - Handles peer connections, message routing, and broadcast
- TCP socket server accepts incoming connections
- Each peer connection runs in separate threads
- Message queue for reliable delivery

**Message Types:**
- `PEER_ANNOUNCE` - Introduce yourself to peer
- `NEW_BLOCK` - Broadcast new block to network
- `NEW_TRANSACTION` - Broadcast transaction
- `REQUEST_CHAIN` - Ask peers for their chain
- `CHAIN_RESPONSE` - Send chain data to peer

## Usage

### Start Multiple Nodes

**Terminal 1 (Node A - Port 6000):**
```bash
python main_p2p.py 6000
```

**Terminal 2 (Node B - Port 6001):**
```bash
python main_p2p.py 6001
```

**Terminal 3 (Node C - Port 6002):**
```bash
python main_p2p.py 6002
```

### Connect Nodes

In Node B, connect to Node A:
```
select > 6
peer host: localhost
peer port: 6000
```

In Node C, connect to Node A:
```
select > 6
peer host: localhost
peer port: 6000
```

Now all nodes are connected!

### Test Network

**Node A - Request item:**
```
select > 1
item ID: laptop-001
```
→ Block broadcasts to B and C automatically

**Node B - Check status:**
```
select > 9
```
→ Shows new block received

**Node C - Release item:**
```
select > 2
item ID: laptop-001
```
→ Block broadcasts to A and B

## Key Features

✅ **Auto-broadcast** - New blocks automatically sent to all peers
✅ **Chain sync** - Request full chain from network
✅ **Thread-safe** - Handles concurrent connections
✅ **Message queues** - Reliable delivery per peer
✅ **Auto-reconnect** - Peers can rejoin network

## Network Messages

### Block Announcement
```python
{
  "type": "new_block",
  "payload": {
    "index": 2,
    "hash": "00abc...",
    "transactions": [...]
  },
  "sender": "192.168.1.10:6000"
}
```

### Chain Request
```python
{
  "type": "request_chain",
  "payload": {},
  "sender": "192.168.1.11:6001"
}
```

## Implementation Details

### Connection Handling
- Server socket listens on specified port
- Accept thread handles incoming connections
- Each peer gets dedicated send/receive threads
- Newline-delimited JSON messages

### Message Flow
```
User action → Blockchain update → Broadcast to peers → Peer validation → Update chain
```

### Thread Safety
- `peers_lock` protects peer set
- Per-peer message queues prevent blocking
- Thread-safe callbacks for blockchain updates

## Example Workflow

1. Start 3 nodes on different ports
2. Connect them in a network
3. Node A creates transaction
4. Transaction auto-broadcasts to B and C
5. All nodes have synchronized chain

## Next Steps

- Add consensus mechanism (longest chain wins)
- Implement transaction pool sync
- Add peer discovery protocol
- Implement NAT traversal for internet connectivity