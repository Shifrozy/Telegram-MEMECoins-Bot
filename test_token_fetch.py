import asyncio
from src.trading.token_info import TokenInfoService

async def test():
    s = TokenInfoService()
    token = "CjWK9UFuJtKRPmBBgW5U8EFmQh97iLPqJBGUbeFwmY9B"
    print(f"Fetching info for: {token}")
    
    r = await s.get_token_info(token)
    
    if r:
        print(f"Symbol: {r.symbol}")
        print(f"Name: {r.name}")
        print(f"Price: ${r.price_usd}")
    else:
        print("Token info not found!")
    
    await s.close()

asyncio.run(test())
