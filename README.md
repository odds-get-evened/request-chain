# request-chain peer - User Manual

## Overview

The Blockchain Peer UI is a decentralized application for managing item reservations on a blockchain network. Each peer can request items, release them back to the pool, mine blocks to earn credits, and participate in a peer-to-peer network.

---

## Getting Started

### Launching the Application

```bash
# normal python script
python peer_ui.py [port]

# or if you choose to run the binaries
peer_ui [port]
```

- **Default port:** 6000
- **Example:** `python peer_ui.py 6001` (starts on port 6001)
- Each peer needs a unique port number

### First Launch

When you first start the application:
- A new blockchain is created (or loaded if one exists)
- Your initial balance is **0 credits**
- You need to **mine blocks** to earn credits before requesting items

---

## Understanding the Interface

### Status Bar (Top Right)

- **Chain Length:** Number of blocks in the blockchain
- **Peers:** Number of connected peers
- **Integrity:** Blockchain validation status (OK/CORRUPT)
- **Reserved:** Items you currently hold
- **Mempool:** Pending transactions waiting to be mined
- **Balance:** Your available credits

### Four Main Tabs

1. **Overview** - View and select items
2. **Peers** - See connected peers
3. **Blockchain** - Browse blocks and transactions
4. **Activity Log** - Recent events and messages

---

## Working with Items

### Overview Tab

The Overview tab shows two lists:

#### **Reserved Items (Left)**
Items you currently hold, showing:
- Item name
- Current value (what you'll get back if you release it)
- Demand count (how many others want it)
- Escrow amount (accumulated from buyout attempts)

**Example:** `item_42  [Value: 15.0, Demand: 3, Escrow: 2.50]`

#### **Available Items (Right)**
Items not currently reserved by anyone

### Requesting Items

**Method 1: Double-click**
1. Go to the **Overview** tab
2. Double-click an item in the **Available Items** list
3. It's added to your batch queue

**Method 2: Manual entry**
1. Type the item name in the text box (left panel)
2. Select **REQUEST** from the dropdown
3. Click **Add to Batch** (or press Enter)

**Cost:** Standard request = **10 credits**

### Releasing Items

**Method 1: Double-click**
1. Go to the **Overview** tab
2. Double-click an item in the **Reserved Items** list
3. It's added to your batch queue

**Method 2: Manual entry**
1. Type the item name in the text box
2. Select **RELEASE** from the dropdown
3. Click **Add to Batch**

**Refund:** You receive the item's current value + your share of escrow (66.67% of accumulated escrow)

---

## Batch Operations

### Managing the Batch Queue

The **Batch Queue** (left panel) shows all pending operations before execution.

**Add items:**
- Double-click from Overview tab
- Enter manually with action selector

**Remove items:**
- Select an item in the queue
- Press **Delete** or **Backspace**
- Or click the **Remove** button

**Clear all:**
- Click **Clear All** to empty the entire queue

### Executing Batch Operations

1. Add one or more items to the batch
2. Click **Execute Batch** button
3. Transactions are broadcast to all connected peers
4. Wait for a miner to include them in a block

**Important:** You must have sufficient credits for all REQUEST operations in the batch.

---

## Mining Blocks

### Manual Mining

1. Wait for transactions to appear in the mempool
2. Click **Mine Block from Mempool**
3. A new block is created and broadcast to peers

**Mining Reward:** 50 credits + any escrow distribution fees

### Auto-Mining

Enable automatic mining to continuously mine blocks when transactions are pending:

1. Check the **⚡ Auto-mine (background)** checkbox
2. Mining runs automatically every few seconds
3. Uncheck to disable

**Recommended for:** Active participants who want to earn consistent rewards

---

## Advanced Features

### Buyouts and Penalties

When you request an item that someone else holds:

**If you have enough credits (≥ current value):**
- You make a **BUYOUT OFFER** 🤝
- Current holder receives the offer amount
- You get the item
- Display: `REQUEST: item_42 🤝 BUYOUT (-15.0 credits)`

**If you don't have enough credits:**
- A **PENALTY** is applied ⚠️
- Penalty amount depends on demand
- Item value increases for current holder
- Your credits go into escrow
- Display: `REQUEST: item_42 ⚠️ PENALTY (-3.5 credits, 35%)`

### Item Value System

- Base value: **10 credits**
- Value increases with demand
- High-demand items show 🔥 indicator (5+ requests)
- Released items return to base value

---

## Networking

### Connecting to Peers

**Menu: Network → Connect to Peer... (Ctrl+N)**

1. Enter peer's **Host** (e.g., `localhost` or IP address)
2. Enter peer's **Port** (e.g., `6001`)
3. Click **Connect**

**Example Setup:**
- Peer 1: `python peer_ui.py 6000`
- Peer 2: `python peer_ui.py 6001`
- From Peer 2, connect to `localhost:6000`

### Syncing the Chain

**Menu: Network → Sync Chain (Ctrl+S)**

Manually request the latest blockchain from connected peers. The app also auto-syncs every 30 seconds.

### Peers Tab

View all connected peers with:
- Address (host:port)
- Connection status
- Blocks/transactions received
- Message statistics
- Uptime

---

## Monitoring

### Blockchain Tab

Browse the entire blockchain:
- Blocks listed newest first
- Click ▶ to expand and view transactions
- Transaction types:
  - ⛏️ **COINBASE** - Mining reward
  - **REQUEST** - Item reservation
  - **RELEASE** - Item returned
  - 💰 **BUYOUT OFFER** - Buyout attempt
  - **TRANSFER** - Credit transfer

### Activity Log Tab

Real-time feed of all events:
- 📤 Broadcast transactions
- 📨 Received transactions
- 📦 New blocks
- ⛏️ Mining activity
- 🔗 Network connections
- ⚠️ Errors and warnings

---

## Tips and Best Practices

### Earning Credits
1. **Mine regularly** - Auto-mining ensures steady income
2. **Release high-demand items** - Earn more from escrow accumulation
3. **Accept buyout offers** - Instant profit when someone offers more than base value

### Managing Items
1. **Check demand before releasing** - High-demand items earn more
2. **Monitor escrow** - Items with escrow accumulation are valuable
3. **Don't hoard unnecessarily** - Release unused items to earn credits

### Network Health
1. **Connect to multiple peers** - Ensures chain consistency
2. **Sync regularly** - Keep your chain up to date
3. **Monitor integrity** - Watch for corruption warnings

### Avoiding Issues
1. **Check balance before batching** - Ensure you can afford all operations
2. **Don't request reserved items without credits** - Penalties add up quickly
3. **Mine before requesting** - Build up credit reserves first

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+N** | Connect to new peer |
| **Ctrl+S** | Sync blockchain |
| **Ctrl+Q** | Exit application |
| **Enter** | Add item to batch (when in text field) |
| **Delete/Backspace** | Remove selected item from batch |

---

## Troubleshooting

### "Insufficient Credits" Error
- **Solution:** Mine blocks to earn credits before requesting items

### Blockchain Integrity Shows "CORRUPT"
- **Auto-repair:** The system attempts automatic repair
- **Manual fix:** Check Activity Log for repair status

### No Peers Connected
- **Check:** Ensure peer addresses and ports are correct
- **Firewall:** Verify network allows connections on your port
- **Restart:** Try restarting both peers

### Transactions Not Confirming
- **Mine a block:** Transactions need to be mined into blocks
- **Enable auto-mining:** Automatic block creation
- **Wait for peers:** Other peers may mine the transactions

---

## Data Persistence

Your blockchain data is automatically saved to:
```
~/.databox/material/blx.pkl
```

The chain is saved:
- After each mined block
- On application exit
- Periodically during operation

---

## Glossary

| Term | Definition |
|------|------------|
| **Mempool** | Pool of pending transactions waiting to be mined |
| **Mining** | Creating new blocks and earning rewards |
| **Coinbase** | Special transaction that pays mining rewards |
| **Escrow** | Credits held when buyout offers fail |
| **Demand** | Number of pending requests for a reserved item |
| **Integrity** | Validation that blockchain hasn't been corrupted |
| **Peer** | Another node in the blockchain network |
| **Nonce** | Number used in mining to find valid blocks |

---

## Quick Start Example

1. **Launch two peers:**
   ```bash
   python peer_ui.py 6000  # Terminal 1
   python peer_ui.py 6001  # Terminal 2
   ```

2. **Connect peers:**
   - In peer 6001: Network → Connect to Peer
   - Host: `localhost`, Port: `6000`

3. **Mine initial credits:**
   - Enable auto-mining on both peers
   - Wait for a few blocks to be mined

4. **Request an item:**
   - Double-click an available item
   - Click "Execute Batch"
   - Mine a block to confirm

5. **Release the item:**
   - Double-click your reserved item
   - Click "Execute Batch"
   - Mine to confirm and receive refund

---

**Need Help?** Check the Activity Log tab for detailed error messages and status updates.