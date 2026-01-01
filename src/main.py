"""
Solana Trading Bot - Main Application Entry Point

A production-ready trading bot with:
- Telegram interface for commands and alerts
- Jupiter DEX integration for trading
- Copy trading from tracked wallets
- Smart wallet monitoring and PnL tracking
"""

import asyncio
import signal
import sys
from typing import Optional

from src.config.settings import get_settings, Settings
from src.config.logging_config import setup_logging, get_logger
from src.blockchain.client import SolanaClient
from src.blockchain.wallet import WalletManager
from src.trading.jupiter import JupiterClient
from src.trading.executor import TradeExecutor
from src.tracking.wallet_tracker import WalletTracker
from src.tracking.copy_trader import CopyTrader
from src.tracking.pnl_tracker import PnLTracker
from src.tg_bot.bot import TelegramBot


class SolanaTradingBot:
    """
    Main application class that orchestrates all components.
    
    Initializes and manages:
    - Solana RPC client
    - Wallet manager
    - Jupiter trading client
    - Trade executor
    - Wallet tracker
    - Copy trader
    - PnL tracker
    - Telegram bot
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize the trading bot.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger("main")
        
        # Components (initialized in start)
        self.solana: Optional[SolanaClient] = None
        self.wallet: Optional[WalletManager] = None
        self.jupiter: Optional[JupiterClient] = None
        self.executor: Optional[TradeExecutor] = None
        self.tracker: Optional[WalletTracker] = None
        self.copy_trader: Optional[CopyTrader] = None
        self.pnl_tracker: Optional[PnLTracker] = None
        self.telegram: Optional[TelegramBot] = None
        
        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def start(self) -> None:
        """Initialize and start all components."""
        self.logger.info("bot_starting", network=self.settings.network)
        
        try:
            # Initialize Solana client
            self.solana = SolanaClient(
                rpc_url=self.settings.get_rpc_url(),
                ws_url=self.settings.get_ws_url(),
                commitment=self.settings.advanced.commitment,
                timeout=self.settings.advanced.rpc_timeout,
                max_retries=self.settings.advanced.rpc_retries,
            )
            await self.solana.connect()
            
            # Verify RPC health
            if not await self.solana.is_healthy():
                raise RuntimeError("Solana RPC is not healthy")
            
            self.logger.info("solana_connected")
            
            # Initialize wallet
            self.wallet = WalletManager(
                self.settings.solana_private_key.get_secret_value()
            )
            
            # Get and log balance
            balance = await self.solana.get_balance(self.wallet.address)
            self.logger.info(
                "wallet_loaded",
                address=self.wallet.address,
                balance_sol=balance,
            )
            
            # Initialize Jupiter client
            self.jupiter = JupiterClient(
                api_key=self.settings.jupiter_api_key.get_secret_value(),
                timeout=self.settings.advanced.rpc_timeout,
                max_retries=self.settings.advanced.rpc_retries,
            )
            
            self.logger.info("jupiter_initialized")
            
            # Initialize trade executor
            self.executor = TradeExecutor(
                settings=self.settings,
                jupiter=self.jupiter,
                wallet=self.wallet,
            )
            
            self.logger.info("executor_initialized")
            
            # Initialize PnL tracker
            self.pnl_tracker = PnLTracker()
            
            # Initialize wallet tracker (always, for tracking + copy trading)
            self.tracker = WalletTracker(
                settings=self.settings,
                solana_client=self.solana,
                poll_interval=5.0,
            )
            await self.tracker.start()
            
            self.logger.info("wallet_tracker_started")
            
            # Initialize copy trader (always, can be enabled/disabled at runtime)
            self.copy_trader = CopyTrader(
                settings=self.settings,
                wallet_tracker=self.tracker,
                trade_executor=self.executor,
            )
            
            # Only start copy trading if enabled in config
            if self.settings.copy_trading.enabled:
                await self.copy_trader.start()
                self.logger.info("copy_trader_started")
            
            # Initialize and start Telegram bot
            self.telegram = TelegramBot(
                settings=self.settings,
                solana=self.solana,
                wallet=self.wallet,
                executor=self.executor,
                tracker=self.tracker,
                copy_trader=self.copy_trader,
                pnl_tracker=self.pnl_tracker,
            )
            await self.telegram.start()
            
            self.logger.info("telegram_bot_started")
            
            self._running = True
            self.logger.info("bot_started_successfully")
            
        except Exception as e:
            self.logger.error("bot_start_failed", error=str(e))
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Gracefully stop all components."""
        self.logger.info("bot_stopping")
        
        self._running = False
        
        # Stop components in reverse order
        if self.telegram:
            try:
                await self.telegram.stop()
            except Exception as e:
                self.logger.error("telegram_stop_error", error=str(e))
        
        if self.copy_trader:
            try:
                await self.copy_trader.stop()
            except Exception as e:
                self.logger.error("copy_trader_stop_error", error=str(e))
        
        if self.tracker:
            try:
                await self.tracker.stop()
            except Exception as e:
                self.logger.error("tracker_stop_error", error=str(e))
        
        if self.jupiter:
            try:
                await self.jupiter.close()
            except Exception as e:
                self.logger.error("jupiter_close_error", error=str(e))
        
        if self.solana:
            try:
                await self.solana.disconnect()
            except Exception as e:
                self.logger.error("solana_disconnect_error", error=str(e))
        
        self._shutdown_event.set()
        self.logger.info("bot_stopped")
    
    async def run_forever(self) -> None:
        """Run the bot until shutdown is signaled."""
        await self._shutdown_event.wait()
    
    def signal_handler(self, sig) -> None:
        """Handle shutdown signals."""
        self.logger.info("shutdown_signal_received", signal=sig)
        asyncio.create_task(self.stop())


async def main() -> None:
    """Main entry point."""
    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Failed to load settings: {e}")
        print("\nMake sure you have:")
        print("1. Copied .env.example to .env and filled in your values")
        print("2. Copied config/config.example.yaml to config/config.yaml")
        sys.exit(1)
    
    # Setup logging
    setup_logging(debug=settings.debug)
    logger = get_logger("main")
    
    # Create bot instance
    bot = SolanaTradingBot(settings)
    
    # Setup signal handlers (Unix)
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: bot.signal_handler(s),
            )
    
    try:
        # Start the bot
        await bot.start()
        
        # Run until shutdown
        logger.info("bot_running", message="Press Ctrl+C to stop")
        
        if sys.platform == "win32":
            # Windows: wait for keyboard interrupt
            try:
                while bot._running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("keyboard_interrupt")
        else:
            await bot.run_forever()
        
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception as e:
        logger.error("bot_error", error=str(e))
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
