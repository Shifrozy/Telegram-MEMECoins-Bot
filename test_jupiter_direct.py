import asyncio
import httpx

async def test_jupiter_order():
    api_key = "1cb59ae8-138e-4040-a5e3-55f300e476b3"
    wallet = "BceQAa4UhC48yVDbJJ46q7Z8R6YiJ8UxNQDXjfmGw23J"
    
    SOL = "So11111111111111111111111111111111111111112"
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    async with httpx.AsyncClient(timeout=30) as client:
        url = "https://api.jup.ag/ultra/v1/order"
        params = {
            "inputMint": SOL,
            "outputMint": USDC,
            "amount": "10000000",  # 0.01 SOL
            "taker": wallet,
            "slippageBps": "50",
        }
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
        }
        
        print(f"Testing SOL -> USDC swap")
        
        resp = await client.get(url, params=params, headers=headers)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"Success! Out amount: {data.get('outAmount')}")
        else:
            print(f"Error: {resp.text[:500]}")

asyncio.run(test_jupiter_order())
