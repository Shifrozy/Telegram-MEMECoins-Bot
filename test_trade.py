import asyncio
from src.config.settings import Settings
from src.blockchain.wallet import WalletManager
from src.trading.jupiter import JupiterClient
from src.trading.executor import TradeExecutor

async def test_full_trade():
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
    
    # Try to buy a small amount
    TOKEN = "7Z93mgwKcbpLnsHxVe1ggMUJvAe7E3o1HNL1g1vBpump"
    
    print(f"\nTrying to buy {TOKEN[:8]}... with 0.01 SOL")
    
    try:
        result = await executor.buy_token(
            token_mint=TOKEN,
            amount_sol=0.01,
        )
        
        print(f"\nResult:")
        print(f"  Status: {result.status}")
        print(f"  Signature: {result.signature}")
        print(f"  Input: {result.input_amount}")
        print(f"  Output: {result.output_amount}")
        if result.error:
            print(f"  Error: {result.error}")
            
    except Exception as e:
        print(f"Error: {e}")
    
    await jupiter.close()

asyncio.run(test_full_trade())
