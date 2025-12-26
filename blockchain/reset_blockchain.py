#!/usr/bin/env python3
"""
Reset blockchain data to start fresh with new credit system.

This script deletes the old blockchain file so you can start with
a clean genesis block that includes the new credit system.

Run this if you get errors loading old blockchain data.
"""

from pathlib import Path


def reset_blockchain():
    snap_path = Path.home().joinpath('.databox', 'material', 'blx.pkl')

    if snap_path.exists():
        print(f"Found old blockchain at: {snap_path}")
        confirm = input("Delete and start fresh? (yes/no): ")

        if confirm.lower() in ('yes', 'y'):
            snap_path.unlink()
            print("✅ Blockchain reset! You can now start the peer with a fresh genesis block.")
        else:
            print("❌ Cancelled. No changes made.")
    else:
        print("ℹ️ No blockchain data found. Nothing to reset.")


if __name__ == "__main__":
    reset_blockchain()