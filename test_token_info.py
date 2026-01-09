import asyncio
from src.trading.token_info import TokenInfoService

async def test():
    svc = TokenInfoService()
    # Test with a pump.fun token
    token = await svc.get_token_info("7Z93mgwKcbpLnsHxVe1ggMUJvAe7E3o1HNL1g1vBpump")
    if token:
        print(f"Symbol: {token.symbol}")
        print(f"Name: {token.name}")
        print(f"Price: ${token.price_usd}")
    else:
        print("Token not found!")
    await svc.close()

asyncio.run(test())
