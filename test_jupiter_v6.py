import asyncio
from src.config.settings import Settings
from src.blockchain.wallet import WalletManager
from src.trading.jupiter_v6 import JupiterV6Client

async def test_jupiter_v6():
    settings = Settings()
    
    # Initialize wallet
    wallet = WalletManager(settings.solana_private_key.get_secret_value())
    print(f"Wallet: {wallet.address}")
    
    # Initialize Jupiter V6 client
    client = JupiterV6Client(
        keypair=wallet.keypair,
        timeout=30,
    )
    
    # Test with pump.fun token
    TOKEN = "7Z93mgwKcbpLnsHxVe1ggMUJvAe7E3o1HNL1g1vBpump"
    
    print(f"\n=== Testing Jupiter V6 Quote ===")
    print(f"Token: {TOKEN[:16]}...")
    
    # First just get a quote
    SOL = "So11111111111111111111111111111111111111112"
    quote = await client.get_quote(
        input_mint=SOL,
        output_mint=TOKEN,
        amount=10000000,  # 0.01 SOL
        slippage_bps=100,
    )
    
    if quote:
        print(f"Quote SUCCESS!")
        print(f"  In Amount: {quote.get('inAmount')} lamports")
        print(f"  Out Amount: {quote.get('outAmount')} tokens")
        print(f"  Price Impact: {quote.get('priceImpactPct')}%")
        
        # Now try actual swap with small amount
        print(f"\n=== Testing Actual Swap (0.005 SOL) ===")
        result = await client.buy_token(
            token_mint=TOKEN,
            amount_sol=0.005,
            slippage_bps=200,  # 2% slippage for memecoins
        )
        
        print(f"\nSwap Result:")
        print(f"  Success: {result.success}")
        print(f"  Signature: {result.signature}")
        if result.error:
            print(f"  Error: {result.error}")
        if result.signature:
            print(f"  Solscan: {result.solscan_url}")
    else:
        print("Quote FAILED!")
    
    await client.close()

asyncio.run(test_jupiter_v6())
