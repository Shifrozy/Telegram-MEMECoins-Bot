"""Quick script to validate a Solana private key from .env file."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def validate_key():
    """Validate the private key in .env file."""
    try:
        import base58
        from solders.keypair import Keypair
        from dotenv import load_dotenv
        
        # Load .env file
        load_dotenv()
        
        private_key = os.getenv("SOLANA_PRIVATE_KEY", "").strip()
        
        if not private_key:
            print("[ERROR] No SOLANA_PRIVATE_KEY found in .env file")
            return False
        
        # Mask the key for display
        masked_key = private_key[:8] + "..." + private_key[-4:]
        print(f"[KEY] Checking: {masked_key}")
        
        # Try to decode and create keypair
        try:
            key_bytes = base58.b58decode(private_key)
            
            if len(key_bytes) == 64:
                # Full keypair (private + public)
                keypair = Keypair.from_bytes(key_bytes)
                print("[OK] Valid 64-byte keypair")
            elif len(key_bytes) == 32:
                # Seed only
                keypair = Keypair.from_seed(key_bytes)
                print("[OK] Valid 32-byte seed")
            else:
                print(f"[ERROR] Invalid key length: {len(key_bytes)} bytes")
                print("        Expected: 64 bytes (full keypair) or 32 bytes (seed)")
                return False
            
            # Get the wallet address
            wallet_address = str(keypair.pubkey())
            
            print()
            print("=" * 60)
            print("[SUCCESS] KEY IS VALID!")
            print("=" * 60)
            print()
            print(f"Wallet Address: {wallet_address}")
            print()
            print("View on Solscan:")
            print(f"  https://solscan.io/account/{wallet_address}")
            print()
            print("Next Steps:")
            print("  1. Make sure this wallet has SOL for trading + fees")
            print("  2. Get your Telegram bot token from @BotFather")
            print("  3. Get your Telegram ID from @userinfobot")
            print("  4. Run: python run.py")
            print()
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Invalid private key format: {e}")
            print()
            print("Valid formats:")
            print("  - Base58 encoded 64-byte keypair")
            print("  - Base58 encoded 32-byte seed")
            return False
            
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print("Run: pip install base58 solders python-dotenv")
        return False


if __name__ == "__main__":
    validate_key()
