"""
===========================================
SOLANA TRADING BOT - COMPLETE SYSTEM CHECK
===========================================

Run this BEFORE deploying to client to verify everything works.
"""
import asyncio
import sys
import os

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("   SOLANA TRADING BOT - COMPLETE SYSTEM CHECK")
print("=" * 60)

# Track test results
results = {
    "passed": 0,
    "failed": 0,
    "warnings": 0,
}

def log_pass(msg):
    print(f"[PASS] {msg}")
    results["passed"] += 1

def log_fail(msg):
    print(f"[FAIL] {msg}")
    results["failed"] += 1

def log_warn(msg):
    print(f"[WARN] {msg}")
    results["warnings"] += 1

def log_info(msg):
    print(f"[INFO] {msg}")


async def main():
    
    # ==========================================
    # 1. CONFIGURATION CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("1. CONFIGURATION CHECK")
    print("=" * 60)
    
    try:
        from src.config.settings import Settings
        settings = Settings()
        log_pass("Settings loaded successfully")
        
        # Check required env vars
        if settings.telegram_bot_token.get_secret_value():
            log_pass(f"Telegram Bot Token: Set")
        else:
            log_fail("Telegram Bot Token: Missing!")
        
        if settings.telegram_admin_id:
            log_pass(f"Telegram Admin ID: {settings.telegram_admin_id}")
        else:
            log_fail("Telegram Admin ID: Missing!")
        
        if settings.solana_private_key.get_secret_value():
            log_pass("Solana Private Key: Set")
        else:
            log_fail("Solana Private Key: Missing!")
        
        if settings.jupiter_api_key.get_secret_value():
            log_pass(f"Jupiter API Key: Set ({settings.jupiter_api_key.get_secret_value()[:8]}...)")
        else:
            log_warn("Jupiter API Key: Not set (will have rate limits)")
        
        log_info(f"Network: {settings.network}")
        log_info(f"RPC URL: {settings.solana_rpc_url[:40]}...")
        log_info(f"Dry Run Mode: {settings.dry_run}")
        
        if settings.dry_run:
            log_warn("DRY_RUN is TRUE - trades will be SIMULATED!")
        
    except Exception as e:
        log_fail(f"Settings error: {e}")
        return
    
    # ==========================================
    # 2. WALLET CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("2. WALLET CHECK")
    print("=" * 60)
    
    try:
        from src.blockchain.wallet import WalletManager
        wallet = WalletManager(settings.solana_private_key.get_secret_value())
        log_pass(f"Wallet initialized: {wallet.address}")
        
        # Check balance
        try:
            from solana.rpc.async_api import AsyncClient
            async with AsyncClient(settings.solana_rpc_url) as client:
                resp = await client.get_balance(wallet.keypair.pubkey())
                if resp.value is not None:
                    balance_sol = resp.value / 1_000_000_000
                    log_pass(f"Wallet Balance: {balance_sol:.4f} SOL")
                    
                    if balance_sol < 0.01:
                        log_warn("Balance very low! Need SOL for trading.")
                    elif balance_sol < 0.1:
                        log_warn("Balance low. Recommend at least 0.1 SOL.")
                else:
                    log_warn("Could not fetch balance")
        except Exception as e:
            log_warn(f"Balance check failed: {str(e)[:50]}")
        
    except Exception as e:
        log_fail(f"Wallet error: {e}")
        return
    
    # ==========================================
    # 3. JUPITER API CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("3. JUPITER API CHECK")
    print("=" * 60)
    
    try:
        from src.trading.jupiter import JupiterClient
        jupiter = JupiterClient(
            api_key=settings.jupiter_api_key.get_secret_value(),
            timeout=15,
        )
        
        # Test Ultra API with SOL to USDC
        SOL = "So11111111111111111111111111111111111111112"
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        try:
            quote = await jupiter.get_order(
                input_mint=SOL,
                output_mint=USDC,
                amount=10000000,  # 0.01 SOL
                taker=wallet.address,
                slippage_bps=50,
            )
            log_pass(f"Jupiter Ultra API: Working (Quote: {quote.out_amount} USDC)")
        except Exception as e:
            log_warn(f"Jupiter Ultra API: {str(e)[:50]}")
        
        await jupiter.close()
        
    except Exception as e:
        log_fail(f"Jupiter client error: {e}")
    
    # ==========================================
    # 4. JUPITER V6 API CHECK (Raydium support)
    # ==========================================
    print("\n" + "=" * 60)
    print("4. JUPITER V6 API CHECK (Raydium/wider token support)")
    print("=" * 60)
    
    try:
        from src.trading.jupiter_v6 import JupiterV6Client
        jupiter_v6 = JupiterV6Client(
            keypair=wallet.keypair,
            rpc_url=settings.solana_rpc_url,
            timeout=15,
        )
        
        quote = await jupiter_v6.get_quote(
            input_mint=SOL,
            output_mint=USDC,
            amount=10000000,
            slippage_bps=50,
        )
        
        if quote:
            log_pass(f"Jupiter V6 API: Working (Out: {quote.get('outAmount')})")
        else:
            log_warn("Jupiter V6 API: No quote returned")
        
        await jupiter_v6.close()
        
    except Exception as e:
        log_warn(f"Jupiter V6 error: {str(e)[:50]}")
    
    # ==========================================
    # 5. PUMPPORTAL API CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("5. PUMPPORTAL API CHECK (pump.fun tokens)")
    print("=" * 60)
    
    try:
        from src.trading.pumpportal import PumpPortalClient, is_pump_token
        log_pass("PumpPortal client: Available")
        log_info(f"is_pump_token('abc...pump') = {is_pump_token('abcpump')}")
        log_info(f"is_pump_token('abc...xyz') = {is_pump_token('abcxyz')}")
    except Exception as e:
        log_warn(f"PumpPortal error: {e}")
    
    # ==========================================
    # 6. TOKEN INFO SERVICE CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("6. TOKEN INFO SERVICE CHECK")
    print("=" * 60)
    
    try:
        from src.trading.token_info import TokenInfoService
        token_svc = TokenInfoService()
        
        # Test with BONK (known token)
        BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        info = await token_svc.get_token_info(BONK)
        
        if info:
            log_pass(f"Token Info Service: Working")
            log_info(f"  BONK Price: ${info.price_usd:.8f}")
        else:
            log_warn("Token Info Service: Could not fetch BONK info")
        
        await token_svc.close()
        
    except Exception as e:
        log_warn(f"Token info error: {str(e)[:50]}")
    
    # ==========================================
    # 7. TRADE EXECUTOR CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("7. TRADE EXECUTOR CHECK")
    print("=" * 60)
    
    try:
        from src.trading.executor import TradeExecutor
        from src.trading.jupiter import JupiterClient
        
        jupiter = JupiterClient(
            api_key=settings.jupiter_api_key.get_secret_value(),
            timeout=30,
        )
        
        executor = TradeExecutor(
            settings=settings,
            jupiter=jupiter,
            wallet=wallet,
        )
        
        log_pass("Trade Executor: Initialized")
        log_info(f"  Dry Run Mode: {executor.dry_run}")
        log_info(f"  Has PumpPortal: {executor.pumpportal is not None}")
        log_info(f"  Has Jupiter V6: {executor.jupiter_v6 is not None}")
        
        await jupiter.close()
        
    except Exception as e:
        log_fail(f"Trade executor error: {e}")
    
    # ==========================================
    # 8. TELEGRAM BOT CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("8. TELEGRAM BOT CHECK")
    print("=" * 60)
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            token = settings.telegram_bot_token.get_secret_value()
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    log_pass(f"Telegram Bot: @{bot_info.get('username')}")
                else:
                    log_fail(f"Telegram Bot: Invalid token")
            else:
                log_fail(f"Telegram Bot: API error {resp.status_code}")
                
    except Exception as e:
        log_fail(f"Telegram error: {e}")
    
    # ==========================================
    # 9. USER WALLET MANAGER CHECK
    # ==========================================
    print("\n" + "=" * 60)
    print("9. USER WALLET MANAGER CHECK")
    print("=" * 60)
    
    try:
        from src.tg_bot.user_wallet_manager import UserWalletManager
        uwm = UserWalletManager()
        log_pass("User Wallet Manager: Available")
        log_info(f"  Storage file: {uwm._storage_file}")
        
        # Test wallet generation
        test_wallet = uwm.generate_wallet(999999999)
        if test_wallet:
            log_pass(f"  Wallet generation: Working")
            # Clean up test wallet
            uwm.delete_wallet(999999999)
        
    except Exception as e:
        log_warn(f"User Wallet Manager error: {e}")
    
    # ==========================================
    # FINAL SUMMARY
    # ==========================================
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    
    print(f"\n  PASSED:   {results['passed']}")
    print(f"  FAILED:   {results['failed']}")
    print(f"  WARNINGS: {results['warnings']}")
    
    if results['failed'] == 0:
        print("\n" + "=" * 60)
        print("  [SUCCESS] ALL CRITICAL CHECKS PASSED!")
        print("=" * 60)
        print("\nBot is ready for deployment.")
        
        if settings.dry_run:
            print("\n[IMPORTANT] DRY_RUN=true in .env")
            print("Set DRY_RUN=false for real trading!")
    else:
        print("\n" + "=" * 60)
        print("  [ERROR] SOME CHECKS FAILED!")
        print("=" * 60)
        print("\nFix the failed checks before deploying.")
    
    if results['warnings'] > 0:
        print(f"\n[NOTE] {results['warnings']} warnings - review above for details.")


# Run
asyncio.run(main())
