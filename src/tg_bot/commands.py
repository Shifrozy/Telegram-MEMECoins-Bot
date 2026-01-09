"""
Telegram command handlers for the trading bot.
Clean, simplified command structure with auto-trading features.
"""

from typing import Optional, Dict, Any
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.blockchain.client import SolanaClient
from src.blockchain.wallet import WalletManager
from src.trading.executor import TradeExecutor
from src.trading.models import TradeOrder, TradeSource
from src.tracking.wallet_tracker import WalletTracker
from src.tracking.copy_trader import CopyTrader
from src.tracking.pnl_tracker import PnLTracker
from src.tracking.wallet_analyzer import WalletAnalyzer
from src.trading.token_info import TokenInfoService
from src.trading.position_manager import PositionManager, Position
from src.trading.user_settings import UserSettingsManager
from src.tg_bot.keyboards import (
    build_main_menu,
    build_wallet_setup_menu,
    build_main_trading_menu,
    build_back_button,
    build_settings_menu,
    build_positions_menu,
    build_token_action_menu,
    build_buy_menu,
    build_buy_confirm_menu,
)
from src.tg_bot.wallet_connection import WalletConnectionManager, TokenExtractor

logger = get_logger(__name__)


class CommandHandler:
    """
    Handles Telegram bot commands.
    
    Core Commands:
    - /start - Main menu
    - /buy <token> - Buy token
    - /sell <token> - Sell token
    - /balance - Wallet balance
    - /positions - Open positions with TP/SL
    - /settings - Trading settings (TP, SL, Amount)
    - /copy - Copy trading
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
        self.settings = settings
        self.solana = solana
        self.wallet = wallet
        self.executor = executor
        self.tracker = tracker
        self.copy_trader = copy_trader
        self.pnl_tracker = pnl_tracker
        
        self.admin_id = settings.telegram_admin_id
        
        # Initialize services
        self._wallet_analyzer = WalletAnalyzer(solana)
        self._token_service = TokenInfoService()
        self._user_settings = UserSettingsManager()
        self._position_manager = PositionManager(
            token_service=self._token_service,
            executor=executor,
        )
        self._wallet_connection = WalletConnectionManager()
        
        # Pending actions (user_id -> action data)
        self._pending: Dict[int, Dict[str, Any]] = {}
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        return user_id == self.admin_id
    
    async def _check_admin(self, update: Update) -> bool:
        """Check admin and send error if not."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized. This bot is private.")
            return False
        return True
    
    # ==========================================
    # CORE COMMANDS
    # ==========================================
    
    async def cmd_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /start command - Main menu."""
        if not await self._check_admin(update):
            return
        
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "Trader"
        user_settings = self._user_settings.get_settings(user_id)
        
        # Get balance
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
        except:
            sol_balance = 0.0
        
        # Get open positions count
        open_positions = len(self._position_manager.get_all_positions(open_only=True))
        
        message = f"""
🚀 **Solana Trading Bot**

Welcome, {user_name}! 👋

━━━━━━━━━━━━━━━━━━━━

💰 **Balance:** {sol_balance:.4f} SOL
📊 **Open Positions:** {open_positions}

━━━━━━━━━━━━━━━━━━━━

**Quick Settings:**
• Buy Amount: {user_settings.default_buy_amount_sol} SOL
• Take Profit: {user_settings.take_profit_pct}%
• Stop Loss: {user_settings.stop_loss_pct}%

━━━━━━━━━━━━━━━━━━━━

**🔥 Quick Trade:**
Just paste a token address to start trading!

Select an option below:
"""
        await update.message.reply_text(
            message.strip(),
            reply_markup=build_main_menu(),
            parse_mode="Markdown",
        )
    
    async def cmd_help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /help command."""
        if not await self._check_admin(update):
            return
        
        help_text = """
🤖 **Solana Trading Bot - Help**

**📱 Quick Start:**
Just paste a token address and the bot will ask to buy!

**💹 Trading Commands:**
• `/buy <token>` - Buy token with your default amount
• `/sell <token>` - Sell token
• `/balance` - Check wallet balance

**📊 Position Management:**
• `/positions` - View open positions with TP/SL
• All positions auto-sell on TP or SL hit!

**⚙️ Settings:**
• `/settings` - Change Buy Amount, TP%, SL%
• `/tp <percent>` - Set Take Profit (e.g., /tp 50)
• `/sl <percent>` - Set Stop Loss (e.g., /sl 25)
• `/amount <sol>` - Set buy amount (e.g., /amount 0.5)

**📋 Copy Trading:**
• `/copy` - Manage copy trading
• `/track <address>` - Track a wallet

**🔄 Other:**
• `/status` - Bot status
• `/menu` - Show main menu

💡 **Tip:** Paste any DEX Screener, Pump.fun, or Jupiter link!
"""
        await update.message.reply_text(
            help_text.strip(),
            parse_mode="Markdown",
        )
    
    async def cmd_balance(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /balance command."""
        if not await self._check_admin(update):
            return
        
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
            
            # Get SOL price
            sol_price = await self._token_service.get_sol_price()
            usd_value = sol_balance * sol_price if sol_price else 0
            
            message = f"""
💰 **Wallet Balance**

**Address:** 
`{self.wallet.address[:8]}...{self.wallet.address[-4:]}`

**SOL Balance:** {sol_balance:.4f} SOL
**USD Value:** ~${usd_value:.2f}

🔗 [View on Solscan](https://solscan.io/account/{self.wallet.address})
"""
            await update.message.reply_text(
                message.strip(),
                parse_mode="Markdown",
                reply_markup=build_back_button(),
            )
        except Exception as e:
            logger.error("balance_command_error", error=str(e))
            await update.message.reply_text(f"❌ Error: {e}")
    
    async def cmd_buy(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /buy <token> [amount] command."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        user_id = update.effective_user.id
        user_settings = self._user_settings.get_settings(user_id)
        
        if not args:
            await update.message.reply_text(
                "🟢 **Buy Token**\n\n"
                "Usage: `/buy <token_address> [amount_sol]`\n\n"
                "Example:\n"
                "`/buy EPjFWdd5...`\n"
                "`/buy EPjFWdd5... 0.5`\n\n"
                f"Default amount: **{user_settings.default_buy_amount_sol} SOL**",
                parse_mode="Markdown",
            )
            return
        
        token_address = args[0]
        
        # Get amount (from args or default)
        if len(args) > 1:
            try:
                amount_sol = float(args[1])
            except ValueError:
                await update.message.reply_text("❌ Invalid amount")
                return
        else:
            amount_sol = user_settings.default_buy_amount_sol
        
        # Check if auto confirm is off
        if user_settings.auto_buy_confirm:
            # Show confirmation
            await self._show_buy_confirmation(
                update, token_address, amount_sol, user_settings
            )
        else:
            # Execute immediately
            await self._execute_buy(update, token_address, amount_sol, user_settings)
    
    async def _show_buy_confirmation(
        self,
        update: Update,
        token_address: str,
        amount_sol: float,
        user_settings,
    ) -> None:
        """Show buy confirmation with token info."""
        loading_msg = await update.message.reply_text("🔄 Fetching token info...")
        
        try:
            # Get token info
            token_info = await self._token_service.get_token_info(token_address)
            
            if token_info:
                symbol = token_info.symbol or "???"
                name = token_info.name or "Unknown"
                price = token_info.price_usd or 0
                mcap = token_info.market_cap or 0
                liq = token_info.liquidity_usd or 0
                
                # Calculate TP/SL prices
                tp_price = price * (1 + user_settings.take_profit_pct / 100)
                sl_price = price * (1 - user_settings.stop_loss_pct / 100)
                
                message = f"""
🟢 **Buy Confirmation**

**Token:** {name} ({symbol})
**Address:** `{token_address[:12]}...`

💵 **Price:** ${price:.8f}
📊 **Market Cap:** ${mcap:,.0f}
💧 **Liquidity:** ${liq:,.0f}

━━━━━━━━━━━━━━━━━━━━

**Your Order:**
• Amount: **{amount_sol} SOL**
• Slippage: {user_settings.slippage_bps / 100}%

**Auto TP/SL:**
• 📈 Take Profit: {user_settings.take_profit_pct}% (${tp_price:.8f})
• 📉 Stop Loss: {user_settings.stop_loss_pct}% (${sl_price:.8f})

━━━━━━━━━━━━━━━━━━━━

Confirm to proceed:
"""
                await loading_msg.edit_text(
                    message.strip(),
                    reply_markup=build_buy_confirm_menu(token_address, amount_sol),
                    parse_mode="Markdown",
                )
            else:
                await loading_msg.edit_text(
                    f"⚠️ Token not found or no data.\n\n"
                    f"Address: `{token_address}`\n\n"
                    f"Buy anyway?",
                    reply_markup=build_buy_confirm_menu(token_address, amount_sol),
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error("show_buy_confirmation_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error: {e}")
    
    async def _execute_buy(
        self,
        update: Update,
        token_address: str,
        amount_sol: float,
        user_settings,
    ) -> None:
        """Execute the buy order."""
        loading_msg = await update.message.reply_text(
            f"🔄 **Executing Buy...**\n\n"
            f"Amount: {amount_sol} SOL\n"
            f"Token: `{token_address[:12]}...`",
            parse_mode="Markdown",
        )
        
        try:
            # Get token info for position tracking
            token_info = await self._token_service.get_token_info(token_address)
            
            # Execute trade
            result = await self.executor.buy_token(
                token_mint=token_address,
                amount_sol=amount_sol,
                slippage_bps=user_settings.slippage_bps,
            )
            
            if result.is_success:
                # Add position for TP/SL monitoring
                entry_price = token_info.price_usd if token_info else 0
                token_symbol = token_info.symbol if token_info else token_address[:8]
                
                # Estimate tokens received (rough)
                tokens_received = result.output_amount or 0
                
                if entry_price > 0 and user_settings.auto_tp_sl:
                    position = self._position_manager.add_position(
                        token_address=token_address,
                        token_symbol=token_symbol,
                        entry_price_usd=entry_price,
                        entry_amount_sol=amount_sol,
                        entry_token_amount=tokens_received,
                        take_profit_pct=user_settings.take_profit_pct,
                        stop_loss_pct=user_settings.stop_loss_pct,
                    )
                    
                    await loading_msg.edit_text(
                        f"✅ **Buy Successful!**\n\n"
                        f"**Token:** {token_symbol}\n"
                        f"**Spent:** {amount_sol} SOL\n\n"
                        f"📈 **TP:** {user_settings.take_profit_pct}% (${position.tp_price:.8f})\n"
                        f"📉 **SL:** {user_settings.stop_loss_pct}% (${position.sl_price:.8f})\n\n"
                        f"🔗 [View TX]({result.solscan_url})\n\n"
                        f"_Position #{position.id} created with auto TP/SL_",
                        parse_mode="Markdown",
                        reply_markup=build_back_button(),
                    )
                else:
                    await loading_msg.edit_text(
                        f"✅ **Buy Successful!**\n\n"
                        f"**Spent:** {amount_sol} SOL\n"
                        f"🔗 [View TX]({result.solscan_url})",
                        parse_mode="Markdown",
                        reply_markup=build_back_button(),
                    )
            else:
                await loading_msg.edit_text(
                    f"❌ **Buy Failed**\n\n"
                    f"Error: {result.error}",
                    parse_mode="Markdown",
                    reply_markup=build_back_button(),
                )
        except Exception as e:
            logger.error("execute_buy_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error: {e}")
    
    async def cmd_sell(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /sell <token> [percent] command."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "🔴 **Sell Token**\n\n"
                "Usage: `/sell <token_address> [percent]`\n\n"
                "Example:\n"
                "`/sell EPjFWdd5...` - Sell 100%\n"
                "`/sell EPjFWdd5... 50` - Sell 50%\n",
                parse_mode="Markdown",
            )
            return
        
        token_address = args[0]
        percent = int(args[1]) if len(args) > 1 else 100
        
        # TODO: Get user's token balance and calculate amount
        await update.message.reply_text(
            f"🔄 **Selling {percent}%...**\n\n"
            f"Token: `{token_address[:12]}...`",
            parse_mode="Markdown",
        )
        
        # Close position if exists
        position = self._position_manager.get_position_by_token(token_address)
        if position:
            self._position_manager.close_position(position.id, "manual_sell")
    
    async def cmd_positions(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /positions command - Show open positions."""
        if not await self._check_admin(update):
            return
        
        positions = self._position_manager.get_all_positions(open_only=True)
        
        if not positions:
            await update.message.reply_text(
                "📊 **Open Positions**\n\n"
                "No open positions.\n\n"
                "Buy a token to start tracking!",
                parse_mode="Markdown",
                reply_markup=build_back_button(),
            )
            return
        
        message = "📊 **Open Positions**\n\n"
        
        for pos in positions:
            pnl_emoji = "🟢" if pos.current_pnl_pct >= 0 else "🔴"
            
            message += (
                f"{pnl_emoji} **{pos.token_symbol}**\n"
                f"   Entry: ${pos.entry_price_usd:.8f}\n"
                f"   Current: ${pos.current_price_usd:.8f}\n"
                f"   PnL: {pos.current_pnl_pct:+.1f}%\n"
                f"   TP: {pos.take_profit_pct}% | SL: {pos.stop_loss_pct}%\n\n"
            )
        
        # Add stats
        stats = self._position_manager.get_stats()
        message += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Total: {stats['total_positions']} | "
        message += f"Wins: {stats['tp_wins']} | "
        message += f"Losses: {stats['sl_losses']}"
        
        positions_data = [p.to_dict() for p in positions]
        
        await update.message.reply_text(
            message.strip(),
            parse_mode="Markdown",
            reply_markup=build_positions_menu(positions_data),
        )
    
    async def cmd_settings(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /settings command."""
        if not await self._check_admin(update):
            return
        
        user_id = update.effective_user.id
        settings = self._user_settings.get_settings(user_id)
        message = self._user_settings.format_settings_message(user_id)
        
        await update.message.reply_text(
            message.strip(),
            parse_mode="Markdown",
            reply_markup=build_settings_menu(settings.to_dict()),
        )
    
    async def cmd_tp(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /tp <percent> command - Set Take Profit."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        user_id = update.effective_user.id
        
        if not args:
            settings = self._user_settings.get_settings(user_id)
            await update.message.reply_text(
                f"📈 **Take Profit Settings**\n\n"
                f"Current: **{settings.take_profit_pct}%**\n\n"
                f"Usage: `/tp <percent>`\n"
                f"Example: `/tp 75`",
                parse_mode="Markdown",
            )
            return
        
        try:
            tp_pct = float(args[0])
            if tp_pct <= 0 or tp_pct > 1000:
                await update.message.reply_text("❌ TP must be between 1% and 1000%")
                return
            
            self._user_settings.set_tp(user_id, tp_pct)
            await update.message.reply_text(
                f"✅ Take Profit set to **{tp_pct}%**",
                parse_mode="Markdown",
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid percentage")
    
    async def cmd_sl(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /sl <percent> command - Set Stop Loss."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        user_id = update.effective_user.id
        
        if not args:
            settings = self._user_settings.get_settings(user_id)
            await update.message.reply_text(
                f"📉 **Stop Loss Settings**\n\n"
                f"Current: **{settings.stop_loss_pct}%**\n\n"
                f"Usage: `/sl <percent>`\n"
                f"Example: `/sl 20`",
                parse_mode="Markdown",
            )
            return
        
        try:
            sl_pct = float(args[0])
            if sl_pct <= 0 or sl_pct > 100:
                await update.message.reply_text("❌ SL must be between 1% and 100%")
                return
            
            self._user_settings.set_sl(user_id, sl_pct)
            await update.message.reply_text(
                f"✅ Stop Loss set to **{sl_pct}%**",
                parse_mode="Markdown",
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid percentage")
    
    async def cmd_amount(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /amount <sol> command - Set default buy amount."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        user_id = update.effective_user.id
        
        if not args:
            settings = self._user_settings.get_settings(user_id)
            await update.message.reply_text(
                f"💰 **Default Buy Amount**\n\n"
                f"Current: **{settings.default_buy_amount_sol} SOL**\n\n"
                f"Usage: `/amount <sol>`\n"
                f"Example: `/amount 0.5`",
                parse_mode="Markdown",
            )
            return
        
        try:
            amount = float(args[0])
            if amount <= 0 or amount > 100:
                await update.message.reply_text("❌ Amount must be between 0.01 and 100 SOL")
                return
            
            self._user_settings.set_buy_amount(user_id, amount)
            await update.message.reply_text(
                f"✅ Default buy amount set to **{amount} SOL**",
                parse_mode="Markdown",
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid amount")
    
    async def cmd_status(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /status command."""
        if not await self._check_admin(update):
            return
        
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
            is_healthy = await self.solana.is_healthy()
            exec_stats = self.executor.get_stats()
            pos_stats = self._position_manager.get_stats()
            
            # Copy trading stats
            copy_enabled = "Disabled"
            tracked_wallets = 0
            if self.copy_trader and self.settings.copy_trading.enabled:
                copy_enabled = "Enabled"
            if self.tracker:
                tracked_wallets = len(self.tracker.get_all_wallets())
            
            message = f"""
🔄 **Bot Status**

**System:**
• RPC: {"🟢 Healthy" if is_healthy else "🔴 Unhealthy"}
• Network: {self.settings.network}

**Wallet:**
• Balance: {sol_balance:.4f} SOL
• Address: `{self.wallet.address[:8]}...`

**Trading Stats:**
• Total Trades: {exec_stats['total_trades']}
• Success Rate: {exec_stats['success_rate']:.0f}%

**Positions:**
• Open: {pos_stats['open_positions']}
• TP Wins: {pos_stats['tp_wins']}
• SL Losses: {pos_stats['sl_losses']}

**Copy Trading:** {copy_enabled}
• Tracked Wallets: {tracked_wallets}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
            await update.message.reply_text(
                message.strip(),
                parse_mode="Markdown",
                reply_markup=build_back_button(),
            )
        except Exception as e:
            logger.error("status_error", error=str(e))
            await update.message.reply_text(f"❌ Error: {e}")
    
    # ==========================================
    # COPY TRADING COMMANDS
    # ==========================================
    
    async def cmd_copy(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /copy command."""
        if not await self._check_admin(update):
            return
        
        if not self.copy_trader:
            await update.message.reply_text("Copy trading not configured.")
            return
        
        args = context.args
        subcommand = args[0].lower() if args else "status"
        
        if subcommand == "status":
            stats = self.copy_trader.get_stats()
            enabled = self.settings.copy_trading.enabled
            tracked = len(self.tracker.get_all_wallets()) if self.tracker else 0
            
            message = f"""
📋 **Copy Trading**

**Status:** {"🟢 Enabled" if enabled else "🔴 Disabled"}
**Tracked Wallets:** {tracked}

**Stats:**
• Detected: {stats['total_detected']}
• Copied: {stats['total_copied']}
• Skipped: {stats['total_skipped']}

**Settings:**
• Size: {self.settings.copy_trading.copy_percentage}%
• Delay: {self.settings.copy_trading.copy_delay_seconds}s
"""
            from src.tg_bot.keyboards import build_copy_trade_menu
            await update.message.reply_text(
                message.strip(),
                parse_mode="Markdown",
                reply_markup=build_copy_trade_menu(enabled, tracked),
            )
        
        elif subcommand == "enable":
            self.settings.copy_trading.enabled = True
            await self.copy_trader.start()
            await update.message.reply_text("✅ Copy trading enabled")
        
        elif subcommand == "disable":
            self.settings.copy_trading.enabled = False
            await self.copy_trader.stop()
            await update.message.reply_text("⏹️ Copy trading disabled")
    
    async def cmd_track(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /track <address> [name] command."""
        if not await self._check_admin(update):
            return
        
        if not self.tracker:
            await update.message.reply_text("Wallet tracking not enabled.")
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "Usage: `/track <wallet_address> [name]`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        name = args[1] if len(args) > 1 else "Trader"
        
        if not WalletManager.is_valid_address(address):
            await update.message.reply_text("❌ Invalid wallet address")
            return
        
        self.tracker.add_wallet(address, name)
        await update.message.reply_text(
            f"✅ Now tracking:\n**{name}**\n`{address}`",
            parse_mode="Markdown",
        )
    
    async def cmd_wallets(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /wallets command - Show tracked wallets."""
        if not await self._check_admin(update):
            return
        
        if not self.tracker:
            await update.message.reply_text("Wallet tracking not enabled.")
            return
        
        wallets = self.tracker.get_all_wallets()
        
        if not wallets:
            await update.message.reply_text(
                "No wallets being tracked.\n"
                "Use `/track <address> [name]` to add one.",
                parse_mode="Markdown",
            )
            return
        
        message = "👛 **Tracked Wallets**\n\n"
        
        for w in wallets:
            message += (
                f"**{w['name']}**\n"
                f"`{w['address'][:8]}...{w['address'][-4:]}`\n"
                f"Swaps: {w['total_swaps']} "
                f"(🟢{w['total_buys']} / 🔴{w['total_sells']})\n\n"
            )
        
        await update.message.reply_text(
            message.strip(),
            parse_mode="Markdown",
        )
    
    async def cmd_token(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /token <address> command - Get token info."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "Usage: `/token <token_address>`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        loading_msg = await update.message.reply_text("🔄 Fetching token info...")
        
        try:
            info = await self._token_service.get_token_info(address)
            
            if not info:
                await loading_msg.edit_text(
                    f"❌ Token not found.\n`{address}`",
                    parse_mode="Markdown",
                )
                return
            
            message = self._token_service.format_token_message(info)
            
            await loading_msg.edit_text(
                message,
                parse_mode="Markdown",
                reply_markup=build_token_action_menu(address, info.symbol),
            )
        except Exception as e:
            logger.error("token_command_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error: {e}")
    
    # ==========================================
    # LEGACY COMMANDS (for backwards compatibility)
    # ==========================================
    
    async def cmd_pnl(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /pnl command."""
        if not await self._check_admin(update):
            return
        
        stats = self._position_manager.get_stats()
        
        message = f"""
📈 **PnL Summary**

**Total Positions:** {stats['total_positions']}
**Open:** {stats['open_positions']}
**Closed:** {stats['closed_positions']}

**Wins (TP):** {stats['tp_wins']}
**Losses (SL):** {stats['sl_losses']}
**Win Rate:** {stats['win_rate']:.0f}%
"""
        await update.message.reply_text(
            message.strip(),
            parse_mode="Markdown",
        )
    
    async def cmd_slippage(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /slippage <bps> command."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        user_id = update.effective_user.id
        
        if not args:
            settings = self._user_settings.get_settings(user_id)
            await update.message.reply_text(
                f"📊 **Slippage Settings**\n\n"
                f"Current: **{settings.slippage_bps} bps** ({settings.slippage_bps/100}%)\n\n"
                f"Usage: `/slippage <bps>`\n"
                f"Example: `/slippage 300` for 3%",
                parse_mode="Markdown",
            )
            return
        
        try:
            slippage = int(args[0])
            if slippage < 10 or slippage > 5000:
                await update.message.reply_text("❌ Slippage must be 10-5000 bps")
                return
            
            self._user_settings.update_settings(user_id, slippage_bps=slippage)
            await update.message.reply_text(
                f"✅ Slippage set to **{slippage} bps** ({slippage/100}%)",
                parse_mode="Markdown",
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid slippage")
    
    async def cmd_stats(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /stats <address> - Wallet analysis."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "Usage: `/stats <wallet_address>`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        
        if not WalletManager.is_valid_address(address):
            await update.message.reply_text("❌ Invalid wallet address")
            return
        
        loading_msg = await update.message.reply_text("🔄 Analyzing wallet...")
        
        try:
            stats = await self._wallet_analyzer.analyze_wallet(address, limit=50)
            message = self._wallet_analyzer.format_stats_message(stats)
            
            await loading_msg.edit_text(message, parse_mode="Markdown")
        except Exception as e:
            logger.error("stats_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error: {e}")
    
    async def cmd_untrack(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /untrack <address> command."""
        if not await self._check_admin(update):
            return
        
        if not self.tracker:
            await update.message.reply_text("Wallet tracking not enabled.")
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "Usage: `/untrack <wallet_address>`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        self.tracker.remove_wallet(address)
        await update.message.reply_text(f"✅ Stopped tracking: `{address[:8]}...`", parse_mode="Markdown")
    
    async def cmd_activity(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /activity command."""
        if not await self._check_admin(update):
            return
        
        if not self.tracker:
            await update.message.reply_text("Wallet tracking not enabled.")
            return
        
        args = context.args
        address = args[0] if args else None
        activities = self.tracker.get_recent_activities(address=address, limit=10)
        
        if not activities:
            await update.message.reply_text("No recent activity.")
            return
        
        message = "📋 **Recent Activity**\n\n"
        
        for act in activities:
            time = act.timestamp.strftime("%H:%M:%S")
            if act.swap_info:
                swap = act.swap_info
                direction = "🟢 BUY" if swap.direction.value == "buy" else "🔴 SELL"
                message += f"**{act.wallet_name}** ({time})\n{direction}\n\n"
        
        await update.message.reply_text(message.strip(), parse_mode="Markdown")
    
    # Keep position manager reference for external access
    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager
    
    @property
    def user_settings(self) -> UserSettingsManager:
        return self._user_settings
    
    @property  
    def token_service(self) -> TokenInfoService:
        return self._token_service
