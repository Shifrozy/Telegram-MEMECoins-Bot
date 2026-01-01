"""
Telegram command handlers for the trading bot.
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
from src.trading.limit_orders import LimitOrderService, OrderType, OrderStatus

logger = get_logger(__name__)


class CommandHandler:
    """
    Handles Telegram bot commands.
    
    Commands:
    - /start, /help - Show help
    - /balance - Show wallet balance
    - /buy <token> <amount> - Buy token with SOL
    - /sell <token> <amount> - Sell token for SOL
    - /status - Show bot status
    - /wallets - Show tracked wallets
    - /pnl - Show PnL report
    - /settings - Show current settings
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
        Initialize command handler.
        
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
        
        self.admin_id = settings.telegram_admin_id
        
        # Initialize wallet analyzer for historical stats
        self._wallet_analyzer = WalletAnalyzer(solana)
        
        # Initialize token info service
        self._token_service = TokenInfoService()
        
        # Initialize limit order service
        self._limit_service = LimitOrderService(
            token_service=self._token_service,
            executor=executor,
        )
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        return user_id == self.admin_id
    
    async def _check_admin(self, update: Update) -> bool:
        """Check admin and send error if not."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text(
                "⛔ Unauthorized. This bot is private."
            )
            return False
        return True
    
    async def cmd_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /start command."""
        if not await self._check_admin(update):
            return
        
        await self.cmd_help(update, context)
    
    async def cmd_help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /help command."""
        if not await self._check_admin(update):
            return
        
        help_text = """
🤖 **Solana Trading Bot**

**Trading Commands:**
• `/balance` - Show wallet balance
• `/buy <token> <sol_amount>` - Buy token with SOL
• `/sell <token> <amount>` - Sell token for SOL
• `/menu` - Interactive menu with buttons

**Tracking Commands:**
• `/wallets` - List tracked wallets
• `/track <address> [name]` - Add wallet to track
• `/untrack <address>` - Remove tracked wallet
• `/activity [address]` - Show recent activity
• `/stats <address>` - Analyze wallet history 📊

**Copy Trading:**
• `/copy status` - Copy trading status
• `/copy enable` - Enable copy trading
• `/copy disable` - Disable copy trading

**Reports:**
• `/pnl [address]` - Show PnL report
• `/status` - Show bot status

**Settings:**
• `/settings` - View current settings
• `/slippage <bps>` - Set default slippage

Use token mint addresses or search by symbol.
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
            # Get SOL balance
            sol_balance = await self.solana.get_balance(self.wallet.address)
            
            message = f"""
💰 **Wallet Balance**

**Address:** `{self.wallet.address[:8]}...{self.wallet.address[-4:]}`
**SOL:** {sol_balance:.4f}

🔗 [View on Solscan](https://solscan.io/account/{self.wallet.address})
"""
            
            # TODO: Add token balances
            
            await update.message.reply_text(
                message.strip(),
                parse_mode="Markdown",
            )
            
        except Exception as e:
            logger.error("balance_command_error", error=str(e))
            await update.message.reply_text(f"❌ Error: {e}")
    
    async def cmd_buy(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /buy <token> <amount> command."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/buy <token_mint> <sol_amount>`\n"
                "Example: `/buy EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v 0.1`",
                parse_mode="Markdown",
            )
            return
        
        token_mint = args[0]
        
        try:
            sol_amount = float(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Use a number.")
            return
        
        # Validate amount against risk settings
        if sol_amount > self.settings.risk.confirm_above_sol:
            await update.message.reply_text(
                f"⚠️ Trade exceeds {self.settings.risk.confirm_above_sol} SOL.\n"
                f"Reply 'CONFIRM {sol_amount} {token_mint[:8]}' to proceed.",
            )
            return
        
        await update.message.reply_text(
            f"🔄 Executing buy...\n"
            f"Token: `{token_mint[:8]}...`\n"
            f"Amount: {sol_amount} SOL",
            parse_mode="Markdown",
        )
        
        try:
            result = await self.executor.buy_token(
                token_mint=token_mint,
                amount_sol=sol_amount,
            )
            
            if result.is_success:
                await update.message.reply_text(
                    f"✅ **Buy Successful!**\n"
                    f"🔗 [View Transaction]({result.solscan_url})",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    f"❌ **Buy Failed**\n"
                    f"Error: {result.error}",
                    parse_mode="Markdown",
                )
                
        except Exception as e:
            logger.error("buy_command_error", error=str(e))
            await update.message.reply_text(f"❌ Error: {e}")
    
    async def cmd_sell(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /sell <token> <amount> command."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/sell <token_mint> <token_amount>`\n"
                "Example: `/sell EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v 100`",
                parse_mode="Markdown",
            )
            return
        
        token_mint = args[0]
        
        try:
            token_amount = float(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Use a number.")
            return
        
        await update.message.reply_text(
            f"🔄 Executing sell...\n"
            f"Token: `{token_mint[:8]}...`\n"
            f"Amount: {token_amount}",
            parse_mode="Markdown",
        )
        
        try:
            # TODO: Get token decimals dynamically
            result = await self.executor.sell_token(
                token_mint=token_mint,
                amount=token_amount,
                decimals=6,  # Common for many tokens
            )
            
            if result.is_success:
                await update.message.reply_text(
                    f"✅ **Sell Successful!**\n"
                    f"🔗 [View Transaction]({result.solscan_url})",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    f"❌ **Sell Failed**\n"
                    f"Error: {result.error}",
                    parse_mode="Markdown",
                )
                
        except Exception as e:
            logger.error("sell_command_error", error=str(e))
            await update.message.reply_text(f"❌ Error: {e}")
    
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
            
            # Get execution stats
            exec_stats = self.executor.get_stats()
            
            # Get copy trading stats
            copy_stats = {}
            copy_enabled = "Disabled"
            if self.copy_trader:
                copy_stats = self.copy_trader.get_stats()
                if self.settings.copy_trading.enabled:
                    copy_enabled = "Enabled"
            
            # Get tracker stats
            tracked_wallets = 0
            if self.tracker:
                tracked_wallets = len(self.tracker.get_all_wallets())
            
            message = f"""
📊 **Bot Status**

**Wallet:**
• Address: `{self.wallet.address[:8]}...{self.wallet.address[-4:]}`
• Balance: {sol_balance:.4f} SOL
• Network: {self.settings.network}

**RPC Status:** {"🟢 Healthy" if is_healthy else "🔴 Unhealthy"}

**Trading Stats:**
• Total Trades: {exec_stats['total_trades']}
• Successful: {exec_stats['successful_trades']}
• Failed: {exec_stats['failed_trades']}
• Success Rate: {exec_stats['success_rate']:.1f}%

**Copy Trading:** {copy_enabled}
• Detected: {copy_stats.get('total_detected', 0)}
• Copied: {copy_stats.get('total_copied', 0)}
• Skipped: {copy_stats.get('total_skipped', 0)}

**Tracking:**
• Monitored Wallets: {tracked_wallets}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            await update.message.reply_text(
                message.strip(),
                parse_mode="Markdown",
            )
            
        except Exception as e:
            logger.error("status_command_error", error=str(e))
            await update.message.reply_text(f"❌ Error: {e}")
    
    async def cmd_wallets(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /wallets command."""
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
        
        if len(args) < 1:
            await update.message.reply_text(
                "Usage: `/track <wallet_address> [name]`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        name = args[1] if len(args) > 1 else "Unknown"
        
        # Validate address
        if not WalletManager.is_valid_address(address):
            await update.message.reply_text("❌ Invalid wallet address.")
            return
        
        self.tracker.add_wallet(address, name)
        
        await update.message.reply_text(
            f"✅ Now tracking wallet:\n"
            f"**{name}**\n"
            f"`{address}`",
            parse_mode="Markdown",
        )
    
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
        
        if len(args) < 1:
            await update.message.reply_text(
                "Usage: `/untrack <wallet_address>`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        self.tracker.remove_wallet(address)
        
        await update.message.reply_text(
            f"✅ Stopped tracking: `{address[:8]}...`",
            parse_mode="Markdown",
        )
    
    async def cmd_activity(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /activity [address] command."""
        if not await self._check_admin(update):
            return
        
        if not self.tracker:
            await update.message.reply_text("Wallet tracking not enabled.")
            return
        
        args = context.args
        address = args[0] if args else None
        
        # Get recent activities
        activities = self.tracker.get_recent_activities(address=address, limit=10)
        
        if not activities:
            if address:
                await update.message.reply_text(
                    f"No recent activity for wallet `{address[:8]}...`\n\n"
                    "Make sure the wallet is being tracked with `/track`",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    "No recent activity detected.\n\n"
                    "Add wallets to track with `/track <address> [name]`",
                    parse_mode="Markdown",
                )
            return
        
        message = "📜 **Recent Activity**\n\n"
        
        for activity in activities:
            timestamp = activity.timestamp.strftime("%H:%M:%S")
            
            if activity.swap_info:
                swap = activity.swap_info
                direction = "🟢 BUY" if swap.direction.value == "buy" else "🔴 SELL"
                
                message += (
                    f"**{activity.wallet_name}** ({timestamp})\n"
                    f"{direction} | In: {swap.input_amount:.4f} → Out: {swap.output_amount:.4f}\n"
                    f"[TX](https://solscan.io/tx/{activity.signature})\n\n"
                )
            else:
                message += (
                    f"**{activity.wallet_name}** ({timestamp})\n"
                    f"Type: {activity.activity_type}\n"
                    f"[TX](https://solscan.io/tx/{activity.signature})\n\n"
                )
        
        await update.message.reply_text(
            message.strip(),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    
    async def cmd_copy(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /copy [status|enable|disable] command."""
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
            
            message = f"""
📋 **Copy Trading Status**

**Status:** {"🟢 Enabled" if enabled else "🔴 Disabled"}
**Tracked Wallets:** {len(self.settings.copy_trading.tracked_wallets)}

**Statistics:**
• Trades Detected: {stats['total_detected']}
• Trades Copied: {stats['total_copied']}
• Trades Skipped: {stats['total_skipped']}
• Success Rate: {stats['success_rate']:.1f}%

**Settings:**
• Sizing Mode: {self.settings.copy_trading.sizing_mode}
• Copy Percentage: {self.settings.copy_trading.copy_percentage}%
• Delay: {self.settings.copy_trading.copy_delay_seconds}s
"""
            
            await update.message.reply_text(
                message.strip(),
                parse_mode="Markdown",
            )
        
        elif subcommand == "enable":
            self.settings.copy_trading.enabled = True
            await self.copy_trader.start()
            await update.message.reply_text("✅ Copy trading enabled.")
        
        elif subcommand == "disable":
            self.settings.copy_trading.enabled = False
            await self.copy_trader.stop()
            await update.message.reply_text("⏹️ Copy trading disabled.")
        
        else:
            await update.message.reply_text(
                "Usage: `/copy [status|enable|disable]`",
                parse_mode="Markdown",
            )
    
    async def cmd_pnl(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /pnl [address] command."""
        if not await self._check_admin(update):
            return
        
        if not self.pnl_tracker:
            await update.message.reply_text("PnL tracking not enabled.")
            return
        
        args = context.args
        
        if args:
            # Show PnL for specific wallet
            address = args[0]
            report = self.pnl_tracker.format_pnl_report(address)
            await update.message.reply_text(report, parse_mode="Markdown")
        else:
            # Show summary of all wallets
            wallets = self.pnl_tracker.get_all_wallets_pnl()
            
            if not wallets:
                await update.message.reply_text("No PnL data available yet.")
                return
            
            message = "📊 **PnL Summary**\n\n"
            
            for w in wallets[:10]:  # Top 10
                emoji = "🟢" if w['total_pnl'] >= 0 else "🔴"
                message += (
                    f"{emoji} **{w['name']}**\n"
                    f"   PnL: {w['total_pnl']:+.4f} SOL\n"
                    f"   Win Rate: {w['win_rate']:.1f}%\n\n"
                )
            
            await update.message.reply_text(
                message.strip(),
                parse_mode="Markdown",
            )
    
    async def cmd_settings(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /settings command."""
        if not await self._check_admin(update):
            return
        
        trading = self.settings.trading
        risk = self.settings.risk
        
        message = f"""
⚙️ **Current Settings**

**Trading:**
• Default Slippage: {trading.default_slippage_bps} bps ({trading.default_slippage_bps/100}%)
• Max Slippage: {trading.max_slippage_bps} bps
• Default Amount: {trading.default_amount_sol} SOL

**Risk Management:**
• Max Position: {risk.max_position_percentage}%
• Daily Loss Limit: {risk.daily_loss_limit_sol} SOL
• Confirm Above: {risk.confirm_above_sol} SOL

**Copy Trading:**
• Enabled: {self.settings.copy_trading.enabled}
• Sizing Mode: {self.settings.copy_trading.sizing_mode}

**Network:** {self.settings.network}
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
        
        if not args:
            await update.message.reply_text(
                f"Current slippage: {self.settings.trading.default_slippage_bps} bps\n"
                f"Usage: `/slippage <bps>` (e.g., `/slippage 150` for 1.5%)",
                parse_mode="Markdown",
            )
            return
        
        try:
            new_slippage = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid value. Use an integer (basis points).")
            return
        
        if new_slippage > self.settings.trading.max_slippage_bps:
            await update.message.reply_text(
                f"❌ Exceeds max slippage ({self.settings.trading.max_slippage_bps} bps)."
            )
            return
        
        self.settings.trading.default_slippage_bps = new_slippage
        
        await update.message.reply_text(
            f"✅ Slippage set to {new_slippage} bps ({new_slippage/100}%)"
        )
    
    async def cmd_stats(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /stats <address> command - analyze wallet history."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "📊 **Wallet Stats**\n\n"
                "Analyze any wallet's trading history.\n\n"
                "Usage: `/stats <wallet_address>`\n\n"
                "Example:\n"
                "`/stats 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        
        # Validate address
        if not WalletManager.is_valid_address(address):
            await update.message.reply_text("❌ Invalid wallet address.")
            return
        
        # Send loading message
        loading_msg = await update.message.reply_text(
            f"🔄 **Analyzing wallet...**\n\n"
            f"`{address[:8]}...{address[-4:]}`\n\n"
            f"_Fetching historical trades..._",
            parse_mode="Markdown",
        )
        
        try:
            # Analyze wallet
            stats = await self._wallet_analyzer.analyze_wallet(address, limit=50)
            
            # Format and send results
            message = self._wallet_analyzer.format_stats_message(stats)
            
            await loading_msg.edit_text(
                message,
                parse_mode="Markdown",
            )
            
        except Exception as e:
            logger.error("stats_command_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error analyzing wallet: {e}")
    
    async def cmd_token(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /token <address> command - get token info."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "🪙 **Token Info**\n\n"
                "Get comprehensive info about any token.\n\n"
                "Usage: `/token <token_address>`\n\n"
                "Example:\n"
                "`/token EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`",
                parse_mode="Markdown",
            )
            return
        
        address = args[0]
        
        # Validate address (basic check)
        if len(address) < 32 or len(address) > 50:
            await update.message.reply_text("❌ Invalid token address.")
            return
        
        # Send loading message
        loading_msg = await update.message.reply_text(
            f"🔄 **Fetching token info...**\n\n"
            f"`{address[:8]}...{address[-4:]}`\n\n"
            f"_Getting price, market cap, liquidity..._",
            parse_mode="Markdown",
        )
        
        try:
            # Get token info
            info = await self._token_service.get_token_info(address)
            
            if not info:
                await loading_msg.edit_text(
                    f"❌ Token not found or no trading data.\n\n"
                    f"Address: `{address}`\n\n"
                    f"Make sure this is a valid SPL token with trading activity.",
                    parse_mode="Markdown",
                )
                return
            
            # Format and send results
            message = self._token_service.format_token_message(info)
            
            # Add buy/sell buttons
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            keyboard = [
                [
                    InlineKeyboardButton("🟢 Buy 0.1 SOL", callback_data=f"quickbuy_{address[:20]}_0.1"),
                    InlineKeyboardButton("🟢 Buy 0.5 SOL", callback_data=f"quickbuy_{address[:20]}_0.5"),
                ],
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_token_{address[:20]}"),
                    InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{address}"),
                ],
            ]
            
            await loading_msg.edit_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )
            
        except Exception as e:
            logger.error("token_command_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error fetching token info: {e}")
    
    async def cmd_limit(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /limit command - create limit orders."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if not args or len(args) < 4:
            await update.message.reply_text(
                "📋 **Limit Orders**\n\n"
                "Create buy/sell orders at specific prices.\n\n"
                "**Usage:**\n"
                "`/limit buy <token> <price_usd> <sol_amount>`\n"
                "`/limit sell <token> <price_usd> <sol_amount>`\n"
                "`/limit sl <token> <price_usd> <sol_amount>` (Stop Loss)\n"
                "`/limit tp <token> <price_usd> <sol_amount>` (Take Profit)\n\n"
                "**Examples:**\n"
                "`/limit buy BONK 0.00002 0.5`\n"
                "_Buy BONK when price drops to $0.00002, spend 0.5 SOL_\n\n"
                "`/limit sl BONK 0.00001 100000`\n"
                "_Sell 100k BONK if price drops to $0.00001_\n\n"
                "**Other Commands:**\n"
                "• `/orders` - View all orders\n"
                "• `/cancelorder <id>` - Cancel an order",
                parse_mode="Markdown",
            )
            return
        
        order_type_str = args[0].lower()
        token_input = args[1]
        
        try:
            target_price = float(args[2])
            amount = float(args[3])
        except ValueError:
            await update.message.reply_text("❌ Invalid price or amount. Use numbers.")
            return
        
        # Determine order type
        type_map = {
            "buy": OrderType.LIMIT_BUY,
            "sell": OrderType.LIMIT_SELL,
            "sl": OrderType.STOP_LOSS,
            "stoploss": OrderType.STOP_LOSS,
            "tp": OrderType.TAKE_PROFIT,
            "takeprofit": OrderType.TAKE_PROFIT,
        }
        
        order_type = type_map.get(order_type_str)
        if not order_type:
            await update.message.reply_text(
                f"❌ Unknown order type: {order_type_str}\n"
                "Use: buy, sell, sl (stop loss), tp (take profit)"
            )
            return
        
        # Resolve token address
        if len(token_input) > 30:
            # It's an address
            token_address = token_input
            token_symbol = token_input[:8]
        else:
            # It's a symbol - need to search
            await update.message.reply_text(
                f"🔍 Searching for token: {token_input}..."
            )
            
            results = await self._token_service.search_token(token_input)
            if not results:
                await update.message.reply_text(
                    f"❌ Token not found: {token_input}\n\n"
                    "Use the full token address instead."
                )
                return
            
            # Use first match
            token_address = results[0].address
            token_symbol = results[0].symbol
        
        # Get current price for reference
        token_info = await self._token_service.get_token_info(token_address)
        current_price = token_info.price_usd if token_info else 0
        
        # Create the order
        order = self._limit_service.create_order(
            order_type=order_type,
            token_address=token_address,
            token_symbol=token_symbol,
            target_price_usd=target_price,
            amount_sol=amount,
            expires_hours=24,  # 24 hour expiry
        )
        
        # Format response
        type_emoji = {
            OrderType.LIMIT_BUY: "🟢 Limit Buy",
            OrderType.LIMIT_SELL: "🔴 Limit Sell",
            OrderType.STOP_LOSS: "🛑 Stop Loss",
            OrderType.TAKE_PROFIT: "🎯 Take Profit",
        }
        
        price_diff = ""
        if current_price > 0:
            diff_pct = ((target_price - current_price) / current_price) * 100
            price_diff = f"\n📈 Current: ${current_price:.8f} ({diff_pct:+.2f}%)"
        
        message = f"""
✅ **Limit Order Created**

**Order ID:** `{order.id}`
**Type:** {type_emoji.get(order_type, order_type.value)}

**Token:** {token_symbol}
**Target Price:** ${target_price:.8f}{price_diff}
**Amount:** {amount} SOL

⏰ **Expires:** 24 hours

The bot will automatically execute when price reaches target.

Use `/orders` to view all orders.
Use `/cancelorder {order.id}` to cancel.
"""
        
        await update.message.reply_text(message.strip(), parse_mode="Markdown")
        
        # Start limit order service if not running
        if not self._limit_service._running:
            await self._limit_service.start()
    
    async def cmd_orders(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /orders command - view limit orders."""
        if not await self._check_admin(update):
            return
        
        orders = self._limit_service.get_all_orders()
        
        if not orders:
            await update.message.reply_text(
                "📋 **No Limit Orders**\n\n"
                "You have no limit orders.\n\n"
                "Create one with:\n"
                "`/limit buy <token> <price> <amount>`",
                parse_mode="Markdown",
            )
            return
        
        # Group by status
        pending = [o for o in orders if o.status == OrderStatus.PENDING]
        filled = [o for o in orders if o.status == OrderStatus.FILLED]
        other = [o for o in orders if o.status not in [OrderStatus.PENDING, OrderStatus.FILLED]]
        
        message = "📋 **Your Limit Orders**\n\n"
        
        if pending:
            message += "**⏳ Pending:**\n"
            for o in pending[:5]:
                type_emoji = "🟢" if "buy" in o.order_type.value else "🔴"
                message += f"• `{o.id}` {type_emoji} {o.token_symbol} @ ${o.target_price_usd:.6f}\n"
            message += "\n"
        
        if filled:
            message += "**✅ Filled (Recent):**\n"
            for o in filled[:3]:
                type_emoji = "🟢" if "buy" in o.order_type.value else "🔴"
                message += f"• `{o.id}` {type_emoji} {o.token_symbol}\n"
            message += "\n"
        
        if other:
            message += "**Other:**\n"
            for o in other[:3]:
                status = "❌" if o.status == OrderStatus.CANCELLED else "💥" if o.status == OrderStatus.FAILED else "⏰"
                message += f"• `{o.id}` {status} {o.token_symbol}\n"
        
        message += f"\n_Total: {len(orders)} orders_"
        
        await update.message.reply_text(message.strip(), parse_mode="Markdown")
    
    async def cmd_cancelorder(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /cancelorder <id> command."""
        if not await self._check_admin(update):
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "Usage: `/cancelorder <order_id>`\n\n"
                "Use `/orders` to see order IDs.",
                parse_mode="Markdown",
            )
            return
        
        order_id = args[0]
        
        if self._limit_service.cancel_order(order_id):
            await update.message.reply_text(f"✅ Order `{order_id}` cancelled.", parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"❌ Could not cancel order `{order_id}`.\n\n"
                "Order may not exist or is already filled/cancelled.",
                parse_mode="Markdown",
            )

