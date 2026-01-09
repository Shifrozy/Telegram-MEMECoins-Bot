"""Test httpx DNS resolution"""
import asyncio
import httpx

async def test():
    print("Testing httpx...")
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Test DexScreener
            print("\nTesting DexScreener API...")
            resp = await client.get(
                "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112"
            )
            print(f"DexScreener status: {resp.status_code}")
            
            # Test Jupiter
            print("\nTesting Jupiter API...")
            resp2 = await client.get(
                "https://tokens.jup.ag/token/So11111111111111111111111111111111111111112"
            )
            print(f"Jupiter status: {resp2.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
