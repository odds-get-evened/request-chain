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

# Blockchain P2P Network with Consensus

Decentralized blockchain with **longest valid chain consensus** to handle network splits and conflicts.

## How Data Persistence Works

### Each Node Saves Its Chain
```python
snap_path = Path.home().joinpath('.databox', 'material', 'blx.pkl')

# Chain saved:
- On exit
- After each block is added
- After consensus adopts new chain
```

### What Happens When Network Goes Down

**Scenario: Total Network Failure**
```
1. All nodes shut down
2. Each node has saved its chain to disk
3. Network comes back online
4. Nodes restart and load saved chains
5. Consensus mechanism resolves any conflicts
```

**Your chain persists!** Even if the entire network goes down, when nodes restart they load their saved state.

## Consensus Mechanism (Longest Valid Chain)

### The Problem
```
Network Split:
   Node A (blocks 0,1,2,3)     Node B (blocks 0,1,2,4)
         ↓                            ↓
   Both add different blocks!
```

### The Solution
When nodes reconnect, **longest valid chain wins**:

```python
def replace_chain(self, new_chain: list[dict]) -> bool:
    # Only replace if:
    # 1. Peer's chain is LONGER
    # 2. Peer's chain passes FULL integrity check
    
    if len(new_chain) <= len(self.chain):
        return False  # Keep ours
    
    # Validate peer's chain
    if temp_blockchain.integrity_check():
        self.chain = temp_blockchain.chain  # Adopt longer chain
        return True
```

### How It Works

**Step 1: Node requests chains**
```
select > 8 (sync chain from network)
```

**Step 2: Peers send their chains**
```
[consensus 📡] received chain (length 5) vs ours (length 3)
```

**Step 3: Consensus decides**
```
[consensus ✅] adopted longer chain (5 blocks)
```

OR

```
[consensus ℹ️] kept current chain (already longest)
```

## Real-World Example

### Scenario: Network Split & Recovery

**Initial State (all synced):**
```
Node A: [genesis, block1, block2]
Node B: [genesis, block1, block2]
Node C: [genesis, block1, block2]
```

**Network splits - A disconnects:**
```
Node A (offline)
Node B & C (connected)
```

**While A is offline, B adds blocks:**
```
Node A: [genesis, block1, block2]            (3 blocks)
Node B: [genesis, block1, block2, block3, block4]   (5 blocks)
Node C: [genesis, block1, block2, block3, block4]   (5 blocks)
```

**Meanwhile, A comes back and adds a block:**
```
Node A: [genesis, block1, block2, block5]    (4 blocks - different!)
```

**A reconnects and syncs:**
```bash
# On Node A:
select > 8  # sync chain
```

**Consensus resolves:**
```
[consensus 📡] received chain (length 5) vs ours (length 4)
[consensus ✅] adopted longer chain (5 blocks)
```

**Final State (all synced again):**
```
Node A: [genesis, block1, block2, block3, block4]
Node B: [genesis, block1, block2, block3, block4]
Node C: [genesis, block1, block2, block3, block4]
```

Node A's block5 is **abandoned** because B & C had a longer chain.

## Network Resilience

### Total Network Failure
```
1. All nodes crash ❌
2. Chains saved to disk ✅
3. Nodes restart 🔄
4. Chains loaded from disk ✅
5. Consensus resolves conflicts ✅
```

### Partial Network Failure
```
1. Some nodes offline ❌
2. Others keep working ✅
3. Offline nodes save state to disk ✅
4. Offline nodes rejoin later 🔄
5. Sync with option 8 ✅
6. Adopt longest chain ✅
```

### Single Node "Goes Rogue"
```
1. Node adds invalid blocks
2. Other nodes reject them
3. When syncing, valid chain wins
```

## Data Safety Guarantees

✅ **Persistent Storage**: Chains save to `~/.databox/material/blx.pkl`
✅ **Crash Recovery**: Load chain on restart
✅ **Split Resolution**: Longest valid chain wins
✅ **Integrity Checks**: Invalid chains rejected
✅ **Automatic Sync**: Request chains anytime

## Testing Consensus

### Test 1: Simple Split
```bash
# Terminal 1
python peer.py 6000
# Add some blocks

# Terminal 2  
python peer.py 6001
# DON'T connect yet - work independently
# Add different blocks

# Now connect and sync
select > 6  # connect to localhost:6000
select > 8  # sync chain
# Longest chain wins!
```

### Test 2: Network Crash
```bash
# Start 3 nodes, add blocks
python peer.py 6000
python peer.py 6001
python peer.py 6002

# Kill all nodes (Ctrl+C)
# Chains saved automatically!

# Restart nodes
python peer.py 6000
python peer.py 6001
python peer.py 6002

# Chains loaded from disk!
```

### Test 3: Competing Chains
```bash
# Node A adds 5 blocks
# Node B adds 3 blocks
# When they connect:
# Node B adopts A's chain (5 > 3)
```

## Important Notes

### Chain Selection Rules
1. **Longer is better** (more blocks = more proof-of-work)
2. **Valid only** (all blocks must pass integrity check)
3. **Automatic** (no manual intervention needed)

### Data Loss Prevention
- Chains auto-save after every block
- Exit handlers ensure final save
- Load from disk on startup
- Consensus recovers from splits

### What Happens to Orphaned Blocks?
When your chain gets replaced by a longer one:
- Your blocks are **discarded**
- Transactions in those blocks are **lost**
- This is by design (consensus mechanism)
- **In production**: Use transaction pools to re-broadcast

## Architecture

```
┌──────────────┐
│  Blockchain  │
├──────────────┤
│ replace_chain│ ← Consensus mechanism
│ integrity_chk│ ← Validates chains
│ snapshot()   │ ← Saves to disk
│ init()       │ ← Loads from disk
└──────────────┘
        ↑
        │
┌──────────────┐
│  P2PNetwork  │
├──────────────┤
│ CHAIN_RESPONSE│ ← Triggers consensus
│ REQUEST_CHAIN│ ← Asks for chains
│ broadcast()  │ ← Announces blocks
└──────────────┘
```

## Best Practices

1. **Always sync after reconnecting**: `select > 8`
2. **Check status regularly**: `select > 9`
3. **Connect to multiple peers** for redundancy
4. **Monitor integrity checks** (auto-runs every 5 seconds)

## Summary

**Q: Does the network save state?**
A: Yes! Each node saves to disk automatically.

**Q: What if the entire network crashes?**
A: Nodes load saved chains on restart. Network recovers.

**Q: What if nodes have different chains?**
A: Consensus picks the longest valid chain.

**Q: Can I lose my blocks?**
A: Yes, if another node has a longer valid chain. This prevents double-spending and maintains consistency.

**Q: How do I trigger consensus?**
A: Option 8: "sync chain from network"