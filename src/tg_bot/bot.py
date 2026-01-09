"""
Main Telegram bot implementation.
Simplified and enhanced with auto-trading features.
"""

import asyncio
from typing import Optional

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler as TelegramCommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.blockchain.client import SolanaClient
from src.blockchain.wallet import WalletManager
from src.trading.executor import TradeExecutor
from src.tracking.wallet_tracker import WalletTracker
from src.tracking.copy_trader import CopyTrader
from src.tracking.pnl_tracker import PnLTracker
from src.tg_bot.commands import CommandHandler
from src.tg_bot.notifications import NotificationService
from src.tg_bot.callbacks import CallbackHandler
from src.tg_bot.keyboards import build_main_menu

logger = get_logger(__name__)


class TelegramBot:
    """
    Main Telegram bot for the Solana Trading Bot.
    
    Combines:
    - Command handling for user interaction
    - Notification service for alerts
    - Integration with all bot subsystems
    """
    
    def __init__(
        self,
        settings: Settings,
        solana: SolanaClient,
        wallet: WalletManager,
        executor: TradeExecutor,
        tracker: Optional[WalletTracker] = None,
        copy_trader: Optional[CopyTrader] = None,
        pnl_tracker: Optional[PnLTracker] = None,
    ):
        """
        Initialize the Telegram bot.
        
        Args:
            settings: Application settings
            solana: Solana client
            wallet: Wallet manager
            executor: Trade executor
            tracker: Optional wallet tracker
            copy_trader: Optional copy trader
            pnl_tracker: Optional PnL tracker
        """
        self.settings = settings
        self.solana = solana
        self.wallet = wallet
        self.executor = executor
        self.tracker = tracker
        self.copy_trader = copy_trader
        self.pnl_tracker = pnl_tracker
        
        # Will be initialized on start
        self._app: Optional[Application] = None
        self._bot: Optional[Bot] = None
        self.notifications: Optional[NotificationService] = None
        self._cmd_handler: Optional[CommandHandler] = None
        self._callback_handler: Optional[CallbackHandler] = None
    
    async def start(self) -> None:
        """Start the Telegram bot."""
        token = self.settings.telegram_bot_token.get_secret_value()
        
        # Build the application
        self._app = (
            Application.builder()
            .token(token)
            .build()
        )
        
        self._bot = self._app.bot
        
        # Initialize notification service
        self.notifications = NotificationService(
            bot=self._bot,
            chat_id=self.settings.telegram_admin_id,
            settings=self.settings,
        )
        
        # Initialize command handler
        self._cmd_handler = CommandHandler(
            settings=self.settings,
            solana=self.solana,
            wallet=self.wallet,
            executor=self.executor,
            tracker=self.tracker,
            copy_trader=self.copy_trader,
            pnl_tracker=self.pnl_tracker,
        )
        
        # Initialize callback handler for inline buttons
        self._callback_handler = CallbackHandler(
            settings=self.settings,
            solana=self.solana,
            wallet=self.wallet,
            executor=self.executor,
            tracker=self.tracker,
            copy_trader=self.copy_trader,
            pnl_tracker=self.pnl_tracker,
        )
        
        # Register commands
        self._register_handlers()
        
        # Register callbacks with other services
        self._register_callbacks()
        
        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        
        logger.info("telegram_bot_started")
        
        # Send startup message
        sol_balance = await self.solana.get_balance(self.wallet.address)
        await self.notifications.send_startup_message(
            wallet_address=self.wallet.address,
            sol_balance=sol_balance,
        )
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self.notifications:
            await self.notifications.send_shutdown_message()
        
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        
        logger.info("telegram_bot_stopped")
    
    def _register_handlers(self) -> None:
        """Register all command handlers."""
        if not self._app or not self._cmd_handler:
            return
        
        # Core commands
        self._app.add_handler(
            TelegramCommandHandler("start", self._cmd_handler.cmd_start)
        )
        self._app.add_handler(
            TelegramCommandHandler("help", self._cmd_handler.cmd_help)
        )
        self._app.add_handler(
            TelegramCommandHandler("balance", self._cmd_handler.cmd_balance)
        )
        self._app.add_handler(
            TelegramCommandHandler("status", self._cmd_handler.cmd_status)
        )
        
        # Trading commands
        self._app.add_handler(
            TelegramCommandHandler("buy", self._cmd_handler.cmd_buy)
        )
        self._app.add_handler(
            TelegramCommandHandler("sell", self._cmd_handler.cmd_sell)
        )
        
        # Tracking commands
        self._app.add_handler(
            TelegramCommandHandler("wallets", self._cmd_handler.cmd_wallets)
        )
        self._app.add_handler(
            TelegramCommandHandler("track", self._cmd_handler.cmd_track)
        )
        self._app.add_handler(
            TelegramCommandHandler("untrack", self._cmd_handler.cmd_untrack)
        )
        self._app.add_handler(
            TelegramCommandHandler("activity", self._cmd_handler.cmd_activity)
        )
        
        # Copy trading
        self._app.add_handler(
            TelegramCommandHandler("copy", self._cmd_handler.cmd_copy)
        )
        
        # Reports
        self._app.add_handler(
            TelegramCommandHandler("pnl", self._cmd_handler.cmd_pnl)
        )
        self._app.add_handler(
            TelegramCommandHandler("stats", self._cmd_handler.cmd_stats)
        )
        self._app.add_handler(
            TelegramCommandHandler("token", self._cmd_handler.cmd_token)
        )
        
        # Settings
        self._app.add_handler(
            TelegramCommandHandler("settings", self._cmd_handler.cmd_settings)
        )
        self._app.add_handler(
            TelegramCommandHandler("slippage", self._cmd_handler.cmd_slippage)
        )
        
        # New Trading Settings Commands
        self._app.add_handler(
            TelegramCommandHandler("tp", self._cmd_handler.cmd_tp)
        )
        self._app.add_handler(
            TelegramCommandHandler("sl", self._cmd_handler.cmd_sl)
        )
        self._app.add_handler(
            TelegramCommandHandler("amount", self._cmd_handler.cmd_amount)
        )
        self._app.add_handler(
            TelegramCommandHandler("positions", self._cmd_handler.cmd_positions)
        )
        
        # Interactive menu command
        self._app.add_handler(
            TelegramCommandHandler("menu", self._show_menu)
        )
        
        # Callback query handler for inline buttons
        if self._callback_handler:
            self._app.add_handler(
                CallbackQueryHandler(self._callback_handler.handle_callback)
            )
        
        # Message handler for text input (wallet addresses, token URLs, etc.)
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_text_message
            )
        )
        
        # Error handler
        self._app.add_error_handler(self._error_handler)
        
        logger.debug("telegram_handlers_registered")
    
    def _register_callbacks(self) -> None:
        """Register callbacks with other services."""
        # Trade executor callbacks
        self.executor.on_trade_completed(self._on_trade_completed)
        
        # Wallet tracker callbacks
        if self.tracker:
            self.tracker.on_swap(self._on_wallet_swap)
        
        # Copy trader callbacks
        if self.copy_trader:
            self.copy_trader.on_copy_executed(self._on_copy_executed)
    
    async def _on_trade_completed(self, result) -> None:
        """Handle trade completion."""
        if self.notifications:
            await self.notifications.notify_trade_executed(result)
    
    async def _on_wallet_swap(self, activity) -> None:
        """Handle detected wallet swap."""
        if self.notifications:
            await self.notifications.notify_wallet_activity(activity)
        
        # Update PnL tracker
        if self.pnl_tracker and activity.swap_info:
            self.pnl_tracker.process_swap(activity.swap_info)
    
    async def _on_copy_executed(self, result) -> None:
        """Handle copy trade execution."""
        if self.notifications:
            await self.notifications.notify_trade_executed(result)
    
    async def _error_handler(
        self,
        update: object,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle errors in command processing."""
        logger.error(
            "telegram_error",
            error=str(context.error),
            update=str(update),
        )
        
        if self.notifications:
            await self.notifications.notify_error(
                error_type="Command Error",
                message=str(context.error),
            )
    
    async def _show_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Show interactive menu with inline buttons."""
        if update.effective_user.id != self.settings.telegram_admin_id:
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        message = """
🤖 **Solana Trading Bot**

Welcome! Select an option below:

💰 **Balance** - Check wallet balance
📊 **Portfolio** - View your holdings
🟢🔴 **Buy/Sell** - Execute trades
👛 **Wallets** - Manage tracked wallets
📋 **Activity** - Recent swap activity
📑 **Copy Trade** - Auto-copy settings
📈 **PnL** - Profit & Loss report
⚙️ **Settings** - Bot configuration
🔄 **Status** - System health
"""
        
        await update.message.reply_text(
            message.strip(),
            reply_markup=build_main_menu(),
            parse_mode="Markdown",
        )
    
    async def send_message(self, text: str) -> None:
        """Send a message to the admin."""
        if self.notifications:
            await self.notifications.send_message(text)
    
    async def _handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle text messages (wallet addresses, token URLs, etc.)."""
        # Only process messages from admin
        if update.effective_user.id != self.settings.telegram_admin_id:
            return
        
        # Let callback handler process the message
        if self._callback_handler:
            handled = await self._callback_handler.process_text_message(update, context)
            if handled:
                return
        
        # If not handled, could send a hint message
        # (but let's not be too noisy - only show hint if it looks like they tried to paste something)


async def create_telegram_bot(
    settings: Settings,
    solana: SolanaClient,
    wallet: WalletManager,
    executor: TradeExecutor,
    tracker: Optional[WalletTracker] = None,
    copy_trader: Optional[CopyTrader] = None,
    pnl_tracker: Optional[PnLTracker] = None,
) -> TelegramBot:
    """
    Create and configure the Telegram bot.
    
    Args:
        settings: Application settings
        solana: Solana client
        wallet: Wallet manager
        executor: Trade executor
        tracker: Optional wallet tracker
        copy_trader: Optional copy trader
        pnl_tracker: Optional PnL tracker
        
    Returns:
        Configured TelegramBot
    """
    return TelegramBot(
        settings=settings,
        solana=solana,
        wallet=wallet,
        executor=executor,
        tracker=tracker,
        copy_trader=copy_trader,
        pnl_tracker=pnl_tracker,
    )
