# Request Chain

A lightweight peer-to-peer blockchain implementation with dual interfaces for distributed request management. Built in Python, Request Chain provides both command-line and graphical interfaces for running blockchain nodes.

## Overview

Request Chain demonstrates a working blockchain network where peers can:
- Connect to other nodes in a distributed network
- Submit and validate requests
- Mine blocks using proof-of-work consensus
- Maintain synchronized blockchain state across the network
- View blockchain data through console or GUI

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Peer A    │◄───────►│   Peer B    │◄───────►│   Peer C    │
│  (Console)  │         │    (GUI)    │         │  (Console)  │
└─────────────┘         └─────────────┘         └─────────────┘
       │                       │                       │
       └───────────────────────┴───────────────────────┘
                    Synchronized Blockchain
```

## Features

- **Dual Interface Options**
  - Command-line interface for headless operation
  - GUI application for visual blockchain monitoring
  
- **P2P Networking**
  - Automatic peer discovery and connection
  - Real-time block propagation
  - Network synchronization

- **Blockchain Core**
  - Proof-of-work mining
  - Block validation
  - Chain consensus mechanisms
  - Persistent storage

- **Request Management**
  - Submit requests to the network
  - Track request status
  - View request history

## Installation

### Prerequisites

- Python 3.8+
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone https://github.com/odds-get-evened/request-chain.git
cd request-chain
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install the package (optional):
```bash
python setup.py install
```

## Usage

Request Chain offers two ways to run a blockchain node:

### Console Application

Perfect for servers or headless environments:

```bash
python peer.py --port 5000
```

**Options:**
- `--port`: Port number for the node (default: 5000)
- `--peers`: Comma-separated list of peer addresses to connect to

**Example with peers:**
```bash
python peer.py --port 5001 --peers localhost:5000,localhost:5002
```

See [Console App Guide](README_peer.md) for detailed usage.

### GUI Application

For visual monitoring and interaction:

```bash
python peer_ui.py
```

The GUI provides:
- Real-time blockchain visualization
- Network peer status
- Request submission interface
- Mining controls
- Block explorer

See [GUI App Guide](README_peer_ui.md) for detailed usage.

## Architecture

### Component Structure

```
request-chain/
├── blockchain/          # Core blockchain logic
│   ├── chain.py        # Blockchain data structure
│   ├── block.py        # Block implementation
│   └── consensus.py    # Mining & validation
├── ui/                 # GUI components
│   ├── main_window.py  # Primary interface
│   └── widgets/        # UI widgets
├── peer.py             # Console node
├── peer_ui.py          # GUI node
└── main.py             # Entry point
```

### Block Structure

Each block in the chain contains:

```
┌─────────────────────────────────────┐
│ Block #N                            │
├─────────────────────────────────────┤
│ Index:          N                   │
│ Timestamp:      Unix timestamp      │
│ Previous Hash:  Hash of block N-1   │
│ Data:           Request payload     │
│ Nonce:          Proof-of-work value │
│ Hash:           SHA-256 hash        │
└─────────────────────────────────────┘
```

### Network Flow

1. **Peer Initialization**
   - Node starts and binds to specified port
   - Attempts connection to known peers
   - Exchanges blockchain state

2. **Request Submission**
   - User submits request via console or GUI
   - Request broadcast to all connected peers
   - Added to pending request pool

3. **Mining Process**
   - Miner selects pending requests
   - Calculates proof-of-work
   - Creates new block
   - Broadcasts to network

4. **Block Validation**
   - Peers receive new block
   - Validate hash and previous hash
   - Check proof-of-work difficulty
   - Accept or reject block

5. **Chain Synchronization**
   - Compare chain lengths
   - Adopt longest valid chain
   - Resolve conflicts automatically

## Quick Start Example

### Running a Three-Node Network

**Terminal 1 - First node:**
```bash
python peer.py --port 5000
```

**Terminal 2 - Second node:**
```bash
python peer.py --port 5001 --peers localhost:5000
```

**Terminal 3 - Third node with GUI:**
```bash
python peer_ui.py
# In GUI: Connect to localhost:5000
```

Now you have a working blockchain network! Submit requests from any node and watch them propagate across the network.

## Configuration

Edit configuration in `blockchain/config.py`:

```python
DIFFICULTY = 4              # Mining difficulty (leading zeros)
BLOCK_TIME = 10             # Target seconds between blocks
MAX_REQUESTS_PER_BLOCK = 10 # Request limit per block
```

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Code Style
This project follows PEP 8 guidelines and uses object-oriented design patterns.

## API Overview

### Core Classes

**Blockchain**
```python
class Blockchain:
    def add_block(self, data)
    def validate_chain(self)
    def resolve_conflicts(self, peer_chains)
```

**Peer**
```python
class Peer:
    def connect(self, address)
    def broadcast_block(self, block)
    def sync_chain(self)
```

**Block**
```python
class Block:
    def calculate_hash(self)
    def mine(self, difficulty)
    def is_valid(self)
```

## Troubleshooting

**Peers won't connect**
- Check firewall settings
- Verify port availability
- Ensure correct peer addresses

**Chain not syncing**
- Check network connectivity
- Restart nodes to force resync
- Verify compatible versions

**Mining too slow/fast**
- Adjust DIFFICULTY in config
- Check CPU resources
- Modify BLOCK_TIME target

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

BSD-3-Clause License - see [LICENSE](LICENSE) file for details.

## Resources

- [Console App Documentation](README_peer.md)
- [GUI App Documentation](README_peer_ui.md)
- [Issue Tracker](https://github.com/odds-get-evened/request-chain/issues)

---

**Version:** 0.0.1  
**Last Updated:** December 2024

