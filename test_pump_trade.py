import asyncio
from src.config.settings import Settings
from src.blockchain.wallet import WalletManager
from src.trading.jupiter import JupiterClient
from src.trading.executor import TradeExecutor
from src.trading.pumpportal import is_pump_token

async def test_pump_trade():
    settings = Settings()
    
    # Initialize components
    wallet = WalletManager(settings.solana_private_key.get_secret_value())
    print(f"Wallet: {wallet.address}")
    
    jupiter = JupiterClient(
        api_key=settings.jupiter_api_key.get_secret_value(),
        timeout=30,
    )
    
    executor = TradeExecutor(
        settings=settings,
        jupiter=jupiter,
        wallet=wallet,
    )
    
    # Try to buy a pump.fun token
    TOKEN = "7Z93mgwKcbpLnsHxVe1ggMUJvAe7E3o1HNL1g1vBpump"
    
    print(f"\nIs pump token: {is_pump_token(TOKEN)}")
    print(f"Trying to buy {TOKEN[:8]}... with 0.005 SOL")
    
    try:
        result = await executor.buy_token(
            token_mint=TOKEN,
            amount_sol=0.005,
        )
        
        print(f"\nResult:")
        print(f"  Status: {result.status}")
        print(f"  Signature: {result.signature}")
        if result.error:
            print(f"  Error: {result.error}")
        if result.signature:
            print(f"  Solscan: https://solscan.io/tx/{result.signature}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    await jupiter.close()

asyncio.run(test_pump_trade())
