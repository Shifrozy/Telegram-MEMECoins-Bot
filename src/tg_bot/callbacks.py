"""
Callback query handlers for inline button interactions.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.blockchain.client import SolanaClient
from src.blockchain.wallet import WalletManager
from src.trading.executor import TradeExecutor
from src.tracking.wallet_tracker import WalletTracker
from src.tracking.copy_trader import CopyTrader
from src.tracking.pnl_tracker import PnLTracker
from src.tracking.wallet_analyzer import WalletAnalyzer
from src.tg_bot.keyboards import (
    build_main_menu,
    build_back_button,
    build_trading_menu,
    build_quick_buy_amounts,
    build_quick_sell_percentages,
    build_wallet_menu,
    build_wallet_actions,
    build_settings_menu,
    build_slippage_options,
    build_network_menu,
)

logger = get_logger(__name__)


class CallbackHandler:
    """
    Handles callback queries from inline keyboard buttons.
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
        
        # Store pending actions (user_id -> action data)
        self._pending_actions: Dict[int, Dict[str, Any]] = {}
        
        # Wallet analyzer for historical data
        self._wallet_analyzer = WalletAnalyzer(solana)
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        return user_id == self.admin_id
    
    async def handle_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Main callback handler - routes to specific handlers."""
        query = update.callback_query
        await query.answer()  # Acknowledge the callback
        
        if not self._is_admin(query.from_user.id):
            await query.edit_message_text("⛔ Unauthorized")
            return
        
        data = query.data
        
        try:
            # Route to appropriate handler
            if data == "menu_main":
                await self._show_main_menu(query)
            elif data == "menu_balance":
                await self._show_balance(query)
            elif data == "menu_portfolio":
                await self._show_portfolio(query)
            elif data == "menu_buy":
                await self._show_buy_menu(query)
            elif data == "menu_sell":
                await self._show_sell_menu(query)
            elif data == "menu_wallets":
                await self._show_wallets_menu(query)
            elif data == "menu_activity":
                await self._show_activity(query)
            elif data == "menu_copy":
                await self._show_copy_status(query)
            elif data == "menu_pnl":
                await self._show_pnl(query)
            elif data == "menu_settings":
                await self._show_settings(query)
            elif data == "menu_status":
                await self._show_status(query)
            
            # Buy amount handlers
            elif data.startswith("buy_"):
                await self._handle_buy_amount(query, data)
            
            # Sell percentage handlers
            elif data.startswith("sell_"):
                await self._handle_sell_percentage(query, data)
            
            # Wallet handlers
            elif data.startswith("wallet_"):
                await self._handle_wallet_action(query, data)
            elif data.startswith("wact_"):
                await self._show_wallet_activity(query, data[5:])
            elif data.startswith("wpnl_"):
                await self._show_wallet_pnl(query, data[5:])
            elif data.startswith("wremove_"):
                await self._remove_wallet(query, data[8:])
            elif data.startswith("wstats_"):
                await self._show_wallet_stats(query, data[7:])
            
            # Settings handlers
            elif data == "set_slippage":
                await self._show_slippage_options(query)
            elif data.startswith("slip_"):
                await self._set_slippage(query, data)
            elif data == "set_network":
                await self._show_network_options(query)
            elif data.startswith("network_"):
                await self._set_network(query, data)
            elif data == "set_copy":
                await self._show_copy_settings(query)
            elif data == "set_alerts":
                await self._show_alerts_settings(query)
            elif data == "set_amount":
                await self._show_amount_settings(query)
            elif data == "set_risk":
                await self._show_risk_settings(query)
            elif data == "copy_enable":
                await self._enable_copy_trading(query)
            elif data == "copy_disable":
                await self._disable_copy_trading(query)
            
            # Follow/unfollow
            elif data.startswith("follow_"):
                await self._follow_wallet(query, data[7:])
            elif data.startswith("unfollow_"):
                await self._unfollow_wallet(query, data[9:])
            
            # No-op for info buttons
            elif data == "noop":
                pass
            
            else:
                await query.edit_message_text(
                    f"Unknown action: {data}",
                    reply_markup=build_back_button(),
                )
                
        except Exception as e:
            logger.error("callback_error", error=str(e), data=data)
            await query.edit_message_text(
                f"Error: {str(e)[:100]}",
                reply_markup=build_back_button(),
            )
    
    async def _show_main_menu(self, query) -> None:
        """Show main menu."""
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
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_main_menu(),
            parse_mode="Markdown",
        )
    
    async def _show_balance(self, query) -> None:
        """Show wallet balance."""
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
            
            message = f"""
💰 **Wallet Balance**

**Address:** 
`{self.wallet.address}`

**SOL Balance:** {sol_balance:.4f} SOL

🔗 [View on Solscan](https://solscan.io/account/{self.wallet.address})
"""
            await query.edit_message_text(
                message.strip(),
                reply_markup=build_back_button(),
                parse_mode="Markdown",
            )
        except Exception as e:
            await query.edit_message_text(
                f"Error fetching balance: {e}",
                reply_markup=build_back_button(),
            )
    
    async def _show_portfolio(self, query) -> None:
        """Show portfolio dashboard."""
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
            
            # Get token balances (placeholder for now)
            message = f"""
📊 **Portfolio Dashboard**

**Total Value:** ~{sol_balance:.2f} SOL

━━━━━━━━━━━━━━━━━━━━
**Holdings:**

💎 **SOL** 
   {sol_balance:.4f} SOL

_Token balances coming soon..._
━━━━━━━━━━━━━━━━━━━━

🔗 [View Full Portfolio](https://solscan.io/account/{self.wallet.address})
"""
            await query.edit_message_text(
                message.strip(),
                reply_markup=build_back_button(),
                parse_mode="Markdown",
            )
        except Exception as e:
            await query.edit_message_text(
                f"Error: {e}",
                reply_markup=build_back_button(),
            )
    
    async def _show_buy_menu(self, query) -> None:
        """Show buy amount selection."""
        message = """
🟢 **Quick Buy**

Select amount of SOL to spend:

_Paste a token address after selecting amount_
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_quick_buy_amounts(),
            parse_mode="Markdown",
        )
    
    async def _show_sell_menu(self, query) -> None:
        """Show sell percentage selection."""
        message = """
🔴 **Quick Sell**

Select percentage to sell:

_Choose a token from your portfolio_
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_quick_sell_percentages(),
            parse_mode="Markdown",
        )
    
    async def _show_wallets_menu(self, query) -> None:
        """Show tracked wallets menu."""
        if not self.tracker:
            await query.edit_message_text(
                "Wallet tracking not enabled.",
                reply_markup=build_back_button(),
            )
            return
        
        wallets = self.tracker.get_all_wallets()
        
        if not wallets:
            message = """
👛 **Tracked Wallets**

No wallets being tracked yet.

Use the button below to add a wallet,
or send: `/track <address> <name>`
"""
        else:
            message = f"""
👛 **Tracked Wallets** ({len(wallets)})

Select a wallet to view details:
"""
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_wallet_menu(wallets),
            parse_mode="Markdown",
        )
    
    async def _show_activity(self, query) -> None:
        """Show recent activity."""
        if not self.tracker:
            await query.edit_message_text(
                "Wallet tracking not enabled.",
                reply_markup=build_back_button(),
            )
            return
        
        activities = self.tracker.get_recent_activities(limit=5)
        
        if not activities:
            message = """
📋 **Recent Activity**

No activity detected yet.

Track wallets to monitor their swaps.
"""
        else:
            message = "📋 **Recent Activity**\n\n"
            
            for act in activities:
                time = act.timestamp.strftime("%H:%M")
                
                if act.swap_info:
                    swap = act.swap_info
                    direction = "🟢" if swap.direction.value == "buy" else "🔴"
                    message += (
                        f"{direction} **{act.wallet_name}** ({time})\n"
                        f"   {swap.input_amount:.4f} → {swap.output_amount:.4f}\n\n"
                    )
                else:
                    message += f"⚪ **{act.wallet_name}** ({time})\n\n"
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button(),
            parse_mode="Markdown",
        )
    
    async def _show_copy_status(self, query) -> None:
        """Show copy trading status."""
        enabled = self.settings.copy_trading.enabled
        
        stats = {}
        if self.copy_trader:
            stats = self.copy_trader.get_stats()
        
        status_emoji = "🟢" if enabled else "🔴"
        
        message = f"""
📑 **Copy Trading**

**Status:** {status_emoji} {"Enabled" if enabled else "Disabled"}

**Statistics:**
• Trades Detected: {stats.get('total_detected', 0)}
• Trades Copied: {stats.get('total_copied', 0)}  
• Trades Skipped: {stats.get('total_skipped', 0)}

**Settings:**
• Mode: {self.settings.copy_trading.sizing_mode}
• Size: {self.settings.copy_trading.copy_percentage}%
• Delay: {self.settings.copy_trading.copy_delay_seconds}s

Use `/copy enable` or `/copy disable` to toggle.
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button(),
            parse_mode="Markdown",
        )
    
    async def _show_pnl(self, query) -> None:
        """Show PnL summary."""
        if not self.pnl_tracker:
            await query.edit_message_text(
                "PnL tracking not enabled.",
                reply_markup=build_back_button(),
            )
            return
        
        wallets = self.pnl_tracker.get_all_wallets_pnl()
        
        if not wallets:
            message = """
📈 **PnL Report**

No trading data yet.

Start trading or track wallets to see PnL.
"""
        else:
            message = "📈 **PnL Summary**\n\n"
            
            for w in wallets[:5]:
                emoji = "🟢" if w['total_pnl'] >= 0 else "🔴"
                message += (
                    f"{emoji} **{w['name']}**\n"
                    f"   PnL: {w['total_pnl']:+.4f} SOL\n"
                    f"   Win Rate: {w['win_rate']:.0f}%\n\n"
                )
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button(),
            parse_mode="Markdown",
        )
    
    async def _show_settings(self, query) -> None:
        """Show settings menu."""
        trading = self.settings.trading
        network = self.settings.network
        network_emoji = "🟢" if network == "mainnet" else "🟡"
        
        message = f"""
⚙️ **Settings**

**Trading:**
• Slippage: {trading.default_slippage_bps} bps ({trading.default_slippage_bps/100}%)
• Default Amount: {trading.default_amount_sol} SOL

**Copy Trading:**
• Enabled: {self.settings.copy_trading.enabled}
• Mode: {self.settings.copy_trading.sizing_mode}

**Network:** {network_emoji} {network.upper()}

Select an option to modify:
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_settings_menu(network),
            parse_mode="Markdown",
        )
    
    async def _show_status(self, query) -> None:
        """Show bot status."""
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
            is_healthy = await self.solana.is_healthy()
            
            stats = self.executor.get_stats()
            
            tracked = 0
            if self.tracker:
                tracked = len(self.tracker.get_all_wallets())
            
            health = "🟢 Healthy" if is_healthy else "🔴 Unhealthy"
            
            message = f"""
🔄 **Bot Status**

**System:**
• RPC: {health}
• Network: {self.settings.network}

**Wallet:**
• Balance: {sol_balance:.4f} SOL

**Trading:**
• Total: {stats['total_trades']}
• Success: {stats['successful_trades']}
• Rate: {stats['success_rate']:.0f}%

**Tracking:**
• Wallets: {tracked}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
            await query.edit_message_text(
                message.strip(),
                reply_markup=build_back_button(),
                parse_mode="Markdown",
            )
        except Exception as e:
            await query.edit_message_text(
                f"Error: {e}",
                reply_markup=build_back_button(),
            )
    
    async def _handle_buy_amount(self, query, data: str) -> None:
        """Handle buy amount selection."""
        amount = data.replace("buy_", "")
        
        if amount == "custom":
            message = """
🟢 **Custom Buy**

Send the amount and token address:
`/buy <token_address> <sol_amount>`

Example:
`/buy EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v 0.1`
"""
        else:
            user_id = query.from_user.id
            self._pending_actions[user_id] = {
                "action": "buy",
                "amount": float(amount),
            }
            
            message = f"""
🟢 **Buy {amount} SOL**

Now paste the **token address** you want to buy:

_(Just send the address in the next message)_
"""
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button(),
            parse_mode="Markdown",
        )
    
    async def _handle_sell_percentage(self, query, data: str) -> None:
        """Handle sell percentage selection."""
        pct = data.replace("sell_", "")
        
        message = f"""
🔴 **Sell {pct}%**

Send the **token address** to sell:
`/sell <token_address> <amount>`
"""
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button(),
            parse_mode="Markdown",
        )
    
    async def _handle_wallet_action(self, query, data: str) -> None:
        """Handle wallet-related actions."""
        action = data.replace("wallet_", "")
        
        if action == "add":
            message = """
➕ **Add Wallet to Track**

Send wallet address and name:
`/track <address> <name>`

Example:
`/track 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU TopTrader`
"""
            await query.edit_message_text(
                message.strip(),
                reply_markup=build_back_button("menu_wallets"),
                parse_mode="Markdown",
            )
        else:
            # Show wallet details
            if self.tracker:
                wallet_info = None
                for w in self.tracker.get_all_wallets():
                    if w['address'].startswith(action):
                        wallet_info = w
                        break
                
                if wallet_info:
                    message = f"""
👛 **{wallet_info['name']}**

**Address:**
`{wallet_info['address']}`

**Stats:**
• Total Swaps: {wallet_info['total_swaps']}
• Buys: 🟢 {wallet_info['total_buys']}
• Sells: 🔴 {wallet_info['total_sells']}

🔗 [Solscan](https://solscan.io/account/{wallet_info['address']})
"""
                    await query.edit_message_text(
                        message.strip(),
                        reply_markup=build_wallet_actions(wallet_info['address'], wallet_info['name']),
                        parse_mode="Markdown",
                    )
                    return
            
            await query.edit_message_text(
                "Wallet not found.",
                reply_markup=build_back_button("menu_wallets"),
            )
    
    async def _show_wallet_activity(self, query, address_prefix: str) -> None:
        """Show activity for specific wallet."""
        if not self.tracker:
            return
        
        # Find full address
        full_address = None
        for w in self.tracker.get_all_wallets():
            if w['address'].startswith(address_prefix):
                full_address = w['address']
                break
        
        if not full_address:
            await query.edit_message_text(
                "Wallet not found.",
                reply_markup=build_back_button("menu_wallets"),
            )
            return
        
        activities = self.tracker.get_recent_activities(address=full_address, limit=5)
        
        if not activities:
            message = f"No recent activity for this wallet."
        else:
            message = "📋 **Wallet Activity**\n\n"
            for act in activities:
                time = act.timestamp.strftime("%H:%M")
                if act.swap_info:
                    swap = act.swap_info
                    direction = "🟢 BUY" if swap.direction.value == "buy" else "🔴 SELL"
                    message += f"{direction} ({time})\n"
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("menu_wallets"),
            parse_mode="Markdown",
        )
    
    async def _show_wallet_pnl(self, query, address_prefix: str) -> None:
        """Show PnL for specific wallet."""
        if not self.pnl_tracker:
            await query.edit_message_text(
                "PnL tracking not enabled.",
                reply_markup=build_back_button("menu_wallets"),
            )
            return
        
        # Find full address
        full_address = None
        if self.tracker:
            for w in self.tracker.get_all_wallets():
                if w['address'].startswith(address_prefix):
                    full_address = w['address']
                    break
        
        if not full_address:
            await query.edit_message_text(
                "Wallet not found.",
                reply_markup=build_back_button("menu_wallets"),
            )
            return
        
        report = self.pnl_tracker.format_pnl_report(full_address)
        
        await query.edit_message_text(
            report,
            reply_markup=build_back_button("menu_wallets"),
            parse_mode="Markdown",
        )
    
    async def _remove_wallet(self, query, address_prefix: str) -> None:
        """Remove wallet from tracking."""
        if not self.tracker:
            return
        
        # Find and remove
        for w in self.tracker.get_all_wallets():
            if w['address'].startswith(address_prefix):
                self.tracker.remove_wallet(w['address'])
                await query.edit_message_text(
                    f"✅ Stopped tracking `{w['address'][:8]}...`",
                    reply_markup=build_back_button("menu_wallets"),
                    parse_mode="Markdown",
                )
                return
        
        await query.edit_message_text(
            "Wallet not found.",
            reply_markup=build_back_button("menu_wallets"),
        )
    
    async def _show_wallet_stats(self, query, address_prefix: str) -> None:
        """Show historical wallet statistics."""
        # Find full address
        full_address = None
        wallet_name = "Unknown"
        
        if self.tracker:
            for w in self.tracker.get_all_wallets():
                if w['address'].startswith(address_prefix):
                    full_address = w['address']
                    wallet_name = w.get('name', 'Unknown')
                    break
        
        if not full_address:
            # Maybe it's a direct address prefix
            full_address = address_prefix
        
        # Show loading message
        await query.edit_message_text(
            f"🔄 **Analyzing wallet...**\n\n"
            f"Fetching historical trades for\n`{full_address[:8]}...{full_address[-4:] if len(full_address) > 8 else ''}`\n\n"
            f"_This may take a moment..._",
            parse_mode="Markdown",
        )
        
        try:
            # Analyze wallet
            stats = await self._wallet_analyzer.analyze_wallet(full_address, limit=50)
            
            # Format and display
            message = self._wallet_analyzer.format_stats_message(stats)
            
            await query.edit_message_text(
                message,
                reply_markup=build_back_button("menu_wallets"),
                parse_mode="Markdown",
            )
            
        except Exception as e:
            logger.error("wallet_stats_error", error=str(e))
            await query.edit_message_text(
                f"❌ Error analyzing wallet: {str(e)[:100]}",
                reply_markup=build_back_button("menu_wallets"),
            )
    
    async def _show_slippage_options(self, query) -> None:
        """Show slippage options."""
        current = self.settings.trading.default_slippage_bps
        
        message = f"""
📊 **Slippage Settings**

Current: {current} bps ({current/100}%)

Select new slippage:
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_slippage_options(),
            parse_mode="Markdown",
        )
    
    async def _set_slippage(self, query, data: str) -> None:
        """Set slippage."""
        bps = int(data.replace("slip_", ""))
        self.settings.trading.default_slippage_bps = bps
        
        await query.edit_message_text(
            f"✅ Slippage set to {bps} bps ({bps/100}%)",
            reply_markup=build_back_button("menu_settings"),
        )
    
    async def _show_network_options(self, query) -> None:
        """Show network selection options."""
        current = self.settings.network
        current_emoji = "🟢" if current == "mainnet" else "🟡"
        
        message = f"""
🌐 **Network Settings**

Current: {current_emoji} **{current.upper()}**

⚠️ **Warning:**
• **Mainnet** = Real money, real trades
• **Devnet** = Test network, fake SOL

Select network:
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_network_menu(current),
            parse_mode="Markdown",
        )
    
    async def _set_network(self, query, data: str) -> None:
        """Set network (mainnet/devnet)."""
        new_network = data.replace("network_", "")
        old_network = self.settings.network
        
        if new_network == old_network:
            await query.edit_message_text(
                f"Already on {new_network.upper()}",
                reply_markup=build_back_button("menu_settings"),
            )
            return
        
        # Update settings
        self.settings.network = new_network
        
        # Show confirmation with warning
        if new_network == "mainnet":
            emoji = "🟢"
            warning = "\n\n⚠️ **You are now on MAINNET!**\nAll trades use REAL money!"
        else:
            emoji = "🟡"
            warning = "\n\n✅ You are now on DEVNET (test mode)\nTrades use fake SOL."
        
        message = f"""
{emoji} **Network Changed**

Switched from {old_network.upper()} to **{new_network.upper()}**
{warning}

⚠️ **Note:** Restart the bot to apply RPC changes.
`python run.py`
"""
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("menu_settings"),
            parse_mode="Markdown",
        )
    
    async def _show_copy_settings(self, query) -> None:
        """Show copy trading settings."""
        enabled = self.settings.copy_trading.enabled
        status_emoji = "🟢" if enabled else "🔴"
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Enable" if not enabled else "🟢 Enabled",
                    callback_data="copy_enable"
                ),
                InlineKeyboardButton(
                    "❌ Disable" if enabled else "🔴 Disabled",
                    callback_data="copy_disable"
                ),
            ],
            [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
        ]
        
        message = f"""
📋 **Copy Trading Settings**

**Status:** {status_emoji} {"Enabled" if enabled else "Disabled"}

**Settings:**
• Mode: {self.settings.copy_trading.sizing_mode}
• Copy %: {self.settings.copy_trading.copy_percentage}%
• Delay: {self.settings.copy_trading.copy_delay_seconds}s
• Fixed Size: {self.settings.copy_trading.fixed_size_sol} SOL

**Tracked Wallets:** {len(self.tracker.get_all_wallets()) if self.tracker else 0}

Toggle copy trading:
"""
        from telegram import InlineKeyboardMarkup
        await query.edit_message_text(
            message.strip(),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    
    async def _enable_copy_trading(self, query) -> None:
        """Enable copy trading."""
        self.settings.copy_trading.enabled = True
        
        # Start copy trader if available
        if self.copy_trader:
            await self.copy_trader.start()
        
        await query.edit_message_text(
            "✅ **Copy Trading Enabled!**\n\n"
            "The bot will now copy trades from tracked wallets.",
            reply_markup=build_back_button("set_copy"),
            parse_mode="Markdown",
        )
    
    async def _disable_copy_trading(self, query) -> None:
        """Disable copy trading."""
        self.settings.copy_trading.enabled = False
        
        # Stop copy trader if available
        if self.copy_trader:
            await self.copy_trader.stop()
        
        await query.edit_message_text(
            "🔴 **Copy Trading Disabled**\n\n"
            "The bot will no longer copy trades.",
            reply_markup=build_back_button("set_copy"),
            parse_mode="Markdown",
        )
    
    async def _show_alerts_settings(self, query) -> None:
        """Show alerts settings."""
        alerts = self.settings.telegram.alerts
        
        message = f"""
🔔 **Alert Settings**

**Current Settings:**
• Trade Execution: {"✅" if alerts.trade_execution else "❌"}
• Trade Failure: {"✅" if alerts.trade_failure else "❌"}
• Copy Trade: {"✅" if alerts.copy_trade else "❌"}
• Wallet Activity: {"✅" if alerts.wallet_activity else "❌"}
• Balance Change: {"✅" if alerts.balance_change else "❌"}
• Error Notifications: {"✅" if alerts.error_notifications else "❌"}

_Edit config.yaml to change these settings._
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("menu_settings"),
            parse_mode="Markdown",
        )
    
    async def _show_amount_settings(self, query) -> None:
        """Show default amount settings."""
        current = self.settings.trading.default_amount_sol
        
        keyboard = [
            [
                InlineKeyboardButton("0.05 SOL", callback_data="amt_0.05"),
                InlineKeyboardButton("0.1 SOL", callback_data="amt_0.1"),
                InlineKeyboardButton("0.25 SOL", callback_data="amt_0.25"),
            ],
            [
                InlineKeyboardButton("0.5 SOL", callback_data="amt_0.5"),
                InlineKeyboardButton("1 SOL", callback_data="amt_1"),
            ],
            [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
        ]
        
        message = f"""
💵 **Default Trade Amount**

Current: **{current} SOL**

Select new default amount:
"""
        from telegram import InlineKeyboardMarkup
        await query.edit_message_text(
            message.strip(),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    
    async def _show_risk_settings(self, query) -> None:
        """Show risk management settings."""
        risk = self.settings.risk
        
        message = f"""
⚠️ **Risk Management**

**Current Settings:**
• Max Position: {risk.max_position_percentage}% of balance
• Daily Loss Limit: {risk.daily_loss_limit_sol} SOL
• Stop on Daily Limit: {"✅" if risk.stop_on_daily_limit else "❌"}
• Max Concurrent Positions: {risk.max_concurrent_positions}
• Confirm Above: {risk.confirm_above_sol} SOL

_Edit config.yaml to change these settings._
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("menu_settings"),
            parse_mode="Markdown",
        )
    
    async def _follow_wallet(self, query, address_prefix: str) -> None:
        """Follow a wallet."""
        if self.tracker:
            self.tracker.add_wallet(address_prefix, "Followed")
            await query.edit_message_text(
                f"✅ Now following wallet",
                reply_markup=build_back_button("menu_wallets"),
            )
    
    async def _unfollow_wallet(self, query, address_prefix: str) -> None:
        """Unfollow a wallet."""
        if self.tracker:
            for w in self.tracker.get_all_wallets():
                if w['address'].startswith(address_prefix):
                    self.tracker.remove_wallet(w['address'])
                    break
            await query.edit_message_text(
                f"✅ Unfollowed wallet",
                reply_markup=build_back_button("menu_wallets"),
            )
    
    def get_pending_action(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get pending action for user."""
        return self._pending_actions.get(user_id)
    
    def clear_pending_action(self, user_id: int) -> None:
        """Clear pending action for user."""
        if user_id in self._pending_actions:
            del self._pending_actions[user_id]
