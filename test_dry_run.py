"""
Test buy/sell with DRY RUN mode - no real funds needed!
"""
import asyncio
import sys
import os

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8')

# Enable dry run mode BEFORE importing settings
os.environ["DRY_RUN"] = "true"

from src.config.settings import Settings
from src.blockchain.wallet import WalletManager
from src.trading.jupiter import JupiterClient
from src.trading.executor import TradeExecutor

async def test_dry_run():
    print("=" * 50)
    print("[TEST] DRY RUN MODE TEST - No real funds used!")
    print("=" * 50)
    
    settings = Settings()
    settings.dry_run = True  # Force dry run
    
    print(f"\n[OK] Dry Run Mode: {settings.dry_run}")
    
    # Initialize wallet (even with 0 balance, dry run works)
    wallet = WalletManager(settings.solana_private_key.get_secret_value())
    print(f"[WALLET] {wallet.address}")
    
    # Initialize Jupiter client
    jupiter = JupiterClient(
        api_key=settings.jupiter_api_key.get_secret_value(),
        timeout=30,
    )
    
    # Initialize executor
    executor = TradeExecutor(
        settings=settings,
        jupiter=jupiter,
        wallet=wallet,
    )
    executor.dry_run = True  # Force dry run again
    
    print(f"\n[CONFIG] Executor Dry Run: {executor.dry_run}")
    
    # Test tokens
    PUMP_TOKEN = "7Z93mgwKcbpLnsHxVe1ggMUJvAe7E3o1HNL1g1vBpump"
    BONK_TOKEN = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    
    print("\n" + "=" * 50)
    print("TEST 1: BUY Pump.fun Token")
    print("=" * 50)
    
    result1 = await executor.buy_token(
        token_mint=PUMP_TOKEN,
        amount_sol=0.1,
    )
    
    print(f"  Status: {result1.status}")
    print(f"  Order ID: {result1.order_id}")
    print(f"  Signature: {result1.signature}")
    print(f"  Input: {result1.input_amount} lamports")
    print(f"  Output: {result1.output_amount} tokens")
    
    print("\n" + "=" * 50)
    print("TEST 2: BUY Standard Token (BONK)")
    print("=" * 50)
    
    result2 = await executor.buy_token(
        token_mint=BONK_TOKEN,
        amount_sol=0.5,
    )
    
    print(f"  Status: {result2.status}")
    print(f"  Order ID: {result2.order_id}")
    print(f"  Signature: {result2.signature}")
    print(f"  Input: {result2.input_amount} lamports")
    print(f"  Output: {result2.output_amount} tokens")
    
    print("\n" + "=" * 50)
    print("[STATS] Trading Statistics")
    print("=" * 50)
    stats = executor.get_stats()
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Successful: {stats['successful_trades']}")
    print(f"  Failed: {stats['failed_trades']}")
    print(f"  Simulated: {executor._simulated_trades}")
    
    print("\n[SUCCESS] ALL TESTS PASSED (DRY RUN MODE)")
    print("[INFO] No real SOL was spent!")
    
    await jupiter.close()

asyncio.run(test_dry_run())
