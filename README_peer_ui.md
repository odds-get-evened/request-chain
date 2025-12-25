# Blockchain Peer - GUI Version

Tkinter-based UI for the blockchain peer with menubar, modal dialogs, and automatic background monitoring.

## Quick Start

```bash
# Start first node
python peer_gui.py 6000

# Start second node (different terminal)
python peer_gui.py 6001

# Start third node
python peer_gui.py 6002
```

## UI Layout

```
┌─────────────────────────────────────────────────────────┐
│ File  Network                                           │
├─────────────────────────────────────────────────────────┤
│  Actions          │  Status: Chain | Peers | Integrity  │
│                   ├────────────────────────────────────┤
│  Item ID: [____]  │  [Overview] [Peers] [Blockchain]   │
│  [Request|Release]│         [Activity Log]              │
│                   │                                     │
│  Multi-Request:   │  Tab Content                        │
│  [___________]    │                                     │
│  [Request Multiple│                                     │
└─────────────────────────────────────────────────────────┘
```

## Menubar

### File Menu
- **Exit** - Close application with confirmation

### Network Menu
- **Connect to Peer... (Ctrl+N)** - Open connection dialog
- **Sync Chain (Ctrl+S)** - Manually trigger consensus

## Keyboard Shortcuts

| Shortcut | Action                    |
|----------|---------------------------|
| Ctrl+N   | Connect to Peer dialog    |
| Ctrl+S   | Sync chain from peers     |
| Ctrl+Q   | Exit application          |

## Connect to Peer Dialog

Press **Ctrl+N** or **Network → Connect to Peer...** to open modal dialog:

```
┌──────────────────────────────────┐
│ Connect to Peer              [X] │
├──────────────────────────────────┤
│ Enter peer connection details:   │
│                                  │
│ Host:  [localhost___________]    │
│ Port:  [6001________________]    │
│                                  │
│      [Connect]    [Cancel]       │
└──────────────────────────────────┘
```

**Dialog Features:**
- Pre-filled with common values
- Text auto-selected for quick editing
- Enter key to connect
- Escape key to cancel
- Validates port number
- Centers on screen
- Modal (blocks main window)

## Tabs

### 1. Overview Tab
**Reserved & Available Items**
- Two-column view
- Shows all reserved items on left
- Shows all available items on right
- Auto-refreshes every 5 seconds

### 2. Peers Tab
**Connected Peer Statistics**

| Peer   | Address          | Status    | Blocks | Txs | Messages | Connected |
|--------|------------------|-----------|--------|-----|----------|-----------|
| Peer 1 | localhost:6001   | Connected | 3      | 5   | 12↓ 8↑   | 2h 15m    |
| Peer 2 | 192.168.1.5:6002 | Connected | 1      | 2   | 4↓ 3↑    | 45m       |

**Statistics:**
- **Blocks Recv**: Blocks received from this peer
- **Txs Recv**: Transactions received from this peer
- **Messages**: Received↓ / Sent↑ message count
- **Connected**: How long peer has been connected

### 3. Blockchain Tab
**Full Ledger View**

```
▼ Block #3
  ├─ Hash: 00a1b2c3d4e5f6...
  ├─ Timestamp: 2024-12-25 14:30:22
  ├─ Transactions: 2
  ├─ Nonce: 12847
  │
  ├─▼ REQUEST: laptop-001
  │   └─ Requester: 02f8a9b1c2...
  │
  └─▼ RELEASE: mouse-002
      └─ Requester: 03d7e2f4a1...
```

**Features:**
- Blocks shown in reverse order (newest first)
- Expandable transactions
- Shows hash, timestamp, nonce
- Transaction details: type, item ID, requester

### 4. Activity Log Tab
Real-time event stream with timestamps

## Features

### User Actions
- **Request Item**: Enter ID, click Request
- **Release Item**: Enter ID, click Release
- **Multi-Request**: Comma-separated IDs (e.g., "laptop,mouse,desk")
- **Connect to Peer**: Enter host/port, click Connect

### Automatic Background Tasks

**Peer Statistics (real-time)**
- Tracks blocks/transactions from each peer
- Measures connection uptime
- Counts messages sent/received

**Chain Sync (auto every 30s)**
- Requests chains from all peers
- Adopts longest valid chain automatically
- Reports in activity log

**Status Monitor (auto every 5s)**
- Updates all tabs
- Refreshes peer statistics
- Rebuilds blockchain tree
- Updates item lists

**Integrity Check (auto every 10s)**
- Validates chain continuously
- Auto-repairs if corruption detected
- Reports status changes only

## Examples

### Example 1: Connect to Peer
```
1. Press Ctrl+N (or Network → Connect to Peer...)
2. Dialog opens with "localhost:6001" pre-filled
3. Edit host/port if needed
4. Press Enter (or click Connect)
→ Dialog closes
→ Activity log: "🔗 Connecting to localhost:6001..."
→ Peers tab updates when connected
```

### Example 2: Monitor Peer Activity
```
1. Connect to peers
2. Switch to "Peers" tab
3. Watch statistics update in real-time:
   - Blocks received increment
   - Message counts update
   - Uptime increases
```

### Example 2: View Blockchain History
```
1. Switch to "Blockchain" tab
2. Click ▼ next to any block to expand
3. See all transactions in that block
4. View transaction details (requester, time, type)
```

### Example 3: Track Network Activity
```
Terminal 1: python peer_gui.py 6000
Terminal 2: python peer_gui.py 6001

Node 1:
- "Peers" tab shows Peer 1 (localhost:6001)
- Messages: 0↓ 0↑

Node 1 requests item:
- "Blockchain" tab shows new block
- "Peers" tab: Messages: 1↓ 1↑ (block broadcast)

Node 2:
- "Activity Log" shows "📦 Received block #2"
- "Blockchain" tab updates with new block
- "Peers" tab shows messages from Node 1
```

### Example 4: Network Consensus
```
Node A adds 3 blocks offline
Node B adds 1 block

Node B:
1. Press Ctrl+N to connect to Node A
2. Press Ctrl+S to manually sync (or wait for auto-sync)

→ "Activity Log": "📡 Received chain (length 4) vs ours (2)"
→ "Activity Log": "✅ Adopted longer chain (4 blocks)"
→ "Blockchain" tab refreshes with all 4 blocks
→ "Overview" tab shows new item allocations
```

### Example 5: Exit Application
```
Option 1: Press Ctrl+Q
Option 2: File → Exit
Option 3: Click window [X]

All methods show confirmation dialog:
→ "Are you sure you want to exit?"
→ Click OK to exit
→ Chain saved automatically
→ P2P network stops cleanly
```

## Activity Log Messages
```
Node A adds 3 blocks offline
Node B adds 1 block

Node B connects to Node A:
→ "Activity Log": "📡 Received chain (length 4) vs ours (2)"
→ "Activity Log": "✅ Adopted longer chain (4 blocks)"
→ "Blockchain" tab refreshes with all 4 blocks
→ "Overview" tab shows new item allocations
```

## Activity Log Messages

**Network Events:**
- 🌐 Peer started
- 🔗 Connecting to peer
- 📦 Received block
- 📡 Received chain (consensus)

**Chain Operations:**
- ✅ Requested/Released item
- ✅ Adopted longer chain

**Integrity:**
- 😁 Chain integrity: OK
- ⚠️ Corruption detected
- ✅ Repair completed

**Errors:**
- ❌ Failed to process block
- ❌ Peer chain failed validation

## Background Process Details

### Status Updater (5s interval)
```python
- Updates chain length
- Updates peer count
- Updates integrity status
- Refreshes all tabs:
  * Overview: item lists
  * Peers: statistics
  * Blockchain: ledger
```

### Peer Statistics Tracker (real-time)
```python
- Records every message
- Tracks block/transaction receipt
- Measures uptime
- Updates on every network event
```

### Integrity Monitor (10s interval)
```python
- Runs chain.integrity_check()
- Only logs status CHANGES
- Auto-repairs if needed
```

### Auto Sync (30s interval)
```python
- Requests chains from all peers
- Triggers consensus mechanism
- Updates blockchain tab if chain replaced
```

## UI Thread Safety

All background threads use message queue:
```python
message_queue.put(('log', "message"))     # Log entry
message_queue.put(('status', None))        # Update all tabs

# Processed every 100ms in main UI thread
```

## Advantages Over Console

✅ **Professional menubar**: Standard desktop app interface
✅ **Keyboard shortcuts**: Power user efficiency
✅ **Modal dialogs**: Focused, error-preventing workflow
✅ **Tabbed interface**: Organized data views
✅ **Peer statistics**: Real-time metrics
✅ **Blockchain explorer**: Visual ledger
✅ **Expandable transactions**: Hierarchical view
✅ **Multi-window**: Run multiple nodes side-by-side
✅ **Visual feedback**: See items, peers, blocks
✅ **No manual refresh**: Everything auto-updates
✅ **Exit confirmation**: Prevents accidental data loss

## Tips

1. **Use keyboard shortcuts** for faster workflow:
   - Ctrl+N: Quick peer connection
   - Ctrl+S: Force chain sync
   - Ctrl+Q: Quick exit

2. **Modal dialog benefits**:
   - Pre-filled with sensible defaults
   - Text selected for quick editing
   - Enter/Escape shortcuts
   - Prevents accidental main window clicks

3. **Use tabs effectively**:
   - Overview: Quick item check
   - Peers: Monitor network health
   - Blockchain: Audit full history
   - Activity Log: Troubleshoot issues

4. **Watch peer statistics** to identify:
   - Active vs. idle peers
   - Network partition issues
   - Message flood problems

5. **Blockchain tab** shows consensus:
   - Block order changes indicate chain replacement
   - Missing blocks indicate sync needed

6. **Manual sync** when needed:
   - Press Ctrl+S after reconnecting
   - Use when peer count changes
   - Force sync if blocks seem delayed

7. **Window management**:
   - Run multiple nodes in separate windows
   - Side-by-side comparison of peer states
   - Exit confirmation prevents accidental closure

## Startup Options

```bash
# Default port 6000
python peer_gui.py

# Custom port
python peer_gui.py 7000

# Multiple nodes
python peer_gui.py 6000 &
python peer_gui.py 6001 &
python peer_gui.py 6002 &
```