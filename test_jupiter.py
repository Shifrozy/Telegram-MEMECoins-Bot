import asyncio
from src.trading.jupiter import JupiterClient

async def test():
    api_key = "1cb59ae8-138e-4040-a5e3-55f300e476b3"
    client = JupiterClient(api_key=api_key)
    
    # Test with a simple order request
    SOL = "So11111111111111111111111111111111111111112"
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    try:
        # Try to get an order (0.01 SOL to USDC)
        quote = await client.get_order(
            input_mint=SOL,
            output_mint=USDC,
            amount=10000000,  # 0.01 SOL in lamports
            taker="11111111111111111111111111111111",  # Dummy address
            slippage_bps=50,
        )
        print(f"Quote received! Out amount: {quote.out_amount}")
    except Exception as e:
        print(f"Error: {e}")
    
    await client.close()

asyncio.run(test())
