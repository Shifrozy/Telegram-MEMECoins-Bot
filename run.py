#!/usr/bin/env python3
"""
Solana Trading Bot - Runner Script

Use this script to start the bot from the project root.
"""

import sys
import os

# Add src to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Now import and run
from src.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
