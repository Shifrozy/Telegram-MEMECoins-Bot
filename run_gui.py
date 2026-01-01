"""
GUI Dashboard Launcher

Starts the trading bot with GUI dashboard.
"""

import asyncio
import threading
import sys

from src.config.settings import get_settings
from src.config.logging_config import setup_logging, get_logger
from src.blockchain.client import SolanaClient
from src.blockchain.wallet import WalletManager
from src.trading.jupiter import JupiterClient
from src.trading.executor import TradeExecutor
from src.trading.token_info import TokenInfoService
from src.trading.limit_orders import LimitOrderService
from src.tracking.wallet_tracker import WalletTracker
from src.gui.dashboard import TradingDashboard


async def init_services(settings):
    """Initialize all services."""
    logger = get_logger("gui")
    
    # Initialize Solana client
    solana = SolanaClient(
        rpc_url=settings.get_rpc_url(),
        ws_url=settings.get_ws_url(),
        commitment=settings.advanced.commitment,
        timeout=settings.advanced.rpc_timeout,
    )
    await solana.connect()
    logger.info("solana_connected")
    
    # Initialize wallet
    wallet = WalletManager(
        settings.solana_private_key.get_secret_value()
    )
    logger.info("wallet_loaded", address=wallet.address[:8])
    
    # Initialize Jupiter
    jupiter = JupiterClient(
        api_key=settings.jupiter_api_key.get_secret_value(),
    )
    
    # Initialize executor
    executor = TradeExecutor(
        settings=settings,
        jupiter=jupiter,
        wallet=wallet,
    )
    
    # Initialize token service
    token_service = TokenInfoService()
    
    # Initialize limit order service
    limit_service = LimitOrderService(
        token_service=token_service,
        executor=executor,
    )
    
    # Initialize tracker
    tracker = WalletTracker(
        settings=settings,
        solana_client=solana,
    )
    await tracker.start()
    
    # Get initial balance
    balance = await solana.get_balance(wallet.address)
    sol_price = await token_service.get_sol_price()
    
    return {
        "settings": settings,
        "solana": solana,
        "wallet": wallet,
        "executor": executor,
        "tracker": tracker,
        "token_service": token_service,
        "limit_service": limit_service,
        "balance": balance,
        "sol_price": sol_price,
    }


def run_async_services(settings, dashboard):
    """Run async services in background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        services = loop.run_until_complete(init_services(settings))
        
        # Update dashboard with services
        dashboard.solana = services["solana"]
        dashboard.wallet = services["wallet"]
        dashboard.executor = services["executor"]
        dashboard.tracker = services["tracker"]
        dashboard.token_service = services["token_service"]
        dashboard.limit_service = services["limit_service"]
        
        # Update balance
        dashboard.update_balance(services["balance"])
        dashboard.update_sol_price(services["sol_price"])
        
        # Keep loop running for async operations
        loop.run_forever()
        
    except Exception as e:
        print(f"Service error: {e}")
    finally:
        loop.close()


def main():
    """Main entry point."""
    print("=" * 50)
    print("  Solana Trading Bot - GUI Dashboard")
    print("=" * 50)
    print()
    
    # Load settings
    try:
        settings = get_settings()
        setup_logging(debug=settings.debug)
    except Exception as e:
        print(f"Failed to load settings: {e}")
        print("\nMake sure you have:")
        print("1. Copied .env.example to .env and filled in your values")
        print("2. Copied config/config.example.yaml to config/config.yaml")
        sys.exit(1)
    
    print(f"Network: {settings.network}")
    print()
    
    # Create dashboard
    dashboard = TradingDashboard(settings=settings)
    
    # Start async services in background
    service_thread = threading.Thread(
        target=run_async_services,
        args=(settings, dashboard),
        daemon=True,
    )
    service_thread.start()
    
    print("Starting GUI...")
    print()
    
    # Run dashboard (blocking)
    dashboard.mainloop()
    
    print("\nDashboard closed.")


if __name__ == "__main__":
    main()
