"""
Callback query handlers for inline button interactions.
Simplified and enhanced with auto-trading features.
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
from src.trading.token_info import TokenInfoService
from src.trading.position_manager import PositionManager
from src.trading.user_settings import UserSettingsManager
from src.tracking.wallet_tracker import WalletTracker
from src.tracking.copy_trader import CopyTrader
from src.tracking.pnl_tracker import PnLTracker
from src.tracking.wallet_analyzer import WalletAnalyzer
from src.tg_bot.keyboards import (
    build_main_menu,
    build_back_button,
    build_settings_menu,
    build_slippage_options,
    build_wallet_menu,
    build_positions_menu,
    build_position_detail_menu,
    build_buy_menu,
    build_buy_confirm_menu,
    build_sell_menu,
    build_token_action_menu,
    build_buy_amount_options,
    build_tp_options,
    build_sl_options,
    build_copy_trade_menu,
    build_tracked_wallets_menu,
    build_confirm_cancel,
)
from src.tg_bot.wallet_connection import WalletConnectionManager, TokenExtractor
from src.tg_bot.user_wallet_manager import UserWalletManager

logger = get_logger(__name__)


class CallbackHandler:
    """
    Handles callback queries from inline keyboard buttons.
    Simplified with focus on trading, positions, and settings.
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
        
        # Pending actions (user_id -> action data)
        self._pending: Dict[int, Dict[str, Any]] = {}
        
        # Services
        self._wallet_analyzer = WalletAnalyzer(solana)
        self._wallet_connection = WalletConnectionManager()
        self._user_wallets = UserWalletManager()
        self._token_service = TokenInfoService()
        self._user_settings = UserSettingsManager()
        self._position_manager = PositionManager(
            token_service=self._token_service,
            executor=executor,
        )
    
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
        await query.answer()
        
        if not self._is_admin(query.from_user.id):
            await query.edit_message_text("⛔ Unauthorized")
            return
        
        data = query.data
        user_id = query.from_user.id
        
        try:
            # ==========================================
            # MAIN MENU
            # ==========================================
            if data == "menu_main":
                await self._show_main_menu(query)
            elif data == "menu_refresh":
                await self._show_main_menu(query)
            
            # ==========================================
            # TRADING
            # ==========================================
            elif data == "trade_buy":
                await self._show_buy_prompt(query)
            elif data == "trade_sell":
                await self._show_sell_prompt(query)
            elif data.startswith("buy_exec_"):
                await self._handle_buy_exec(query, data)
            elif data.startswith("buy_confirm_"):
                await self._handle_buy_confirm(query, data)
            elif data.startswith("sell_exec_"):
                await self._handle_sell_exec(query, data)
            elif data.startswith("qbuy_"):
                await self._handle_quick_buy(query, data)
            elif data.startswith("qsell_"):
                await self._handle_quick_sell(query, data)
            elif data.startswith("token_refresh_"):
                await self._refresh_token_info(query, data)
            
            # ==========================================
            # POSITIONS
            # ==========================================
            elif data == "menu_positions":
                await self._show_positions(query)
            elif data.startswith("pos_view_"):
                await self._show_position_detail(query, data)
            elif data.startswith("pos_tp_"):
                await self._show_tp_options_for_position(query, data)
            elif data.startswith("pos_sl_"):
                await self._show_sl_options_for_position(query, data)
            elif data.startswith("pos_close_"):
                await self._close_position(query, data)
            
            # ==========================================
            # WALLET
            # ==========================================
            elif data == "wallet_manage":
                await self._show_wallet_menu(query)
            elif data == "wallet_balance":
                await self._show_balance(query)
            elif data == "wallet_deposit":
                await self._show_deposit_info(query)
            elif data == "wallet_withdraw":
                await self._show_withdraw_prompt(query)
            elif data == "wallet_export":
                await self._show_export_warning(query)
            elif data == "wallet_generate":
                await self._generate_wallet(query)
            elif data == "wallet_import":
                await self._show_import_prompt(query)
            
            # ==========================================
            # SETTINGS
            # ==========================================
            elif data == "menu_settings":
                await self._show_settings(query)
            elif data == "set_buy_amount":
                await self._show_buy_amount_options(query)
            elif data == "set_tp":
                await self._show_tp_options(query)
            elif data == "set_sl":
                await self._show_sl_options(query)
            elif data == "set_slippage":
                await self._show_slippage_options(query)
            elif data == "set_auto_confirm":
                await self._toggle_auto_confirm(query)
            elif data.startswith("setamt_"):
                await self._set_buy_amount(query, data)
            elif data.startswith("settp_"):
                await self._set_tp(query, data)
            elif data.startswith("setsl_"):
                await self._set_sl(query, data)
            elif data.startswith("setslip_"):
                await self._set_slippage(query, data)
            
            # ==========================================
            # COPY TRADING
            # ==========================================
            elif data == "menu_copy":
                await self._show_copy_status(query)
            elif data == "copy_enable":
                await self._enable_copy_trading(query)
            elif data == "copy_disable":
                await self._disable_copy_trading(query)
            elif data == "copy_add_wallet":
                await self._show_add_wallet_prompt(query)
            elif data == "copy_view_wallets":
                await self._show_tracked_wallets(query)
            elif data.startswith("copy_wallet_"):
                await self._show_wallet_detail(query, data)
            elif data.startswith("copy_remove_"):
                await self._remove_tracked_wallet(query, data)
            
            # ==========================================
            # NO-OP
            # ==========================================
            elif data == "noop":
                pass
            else:
                logger.warning("unknown_callback", data=data)
                
        except Exception as e:
            logger.error("callback_error", error=str(e), data=data)
            await query.edit_message_text(
                f"❌ Error: {str(e)[:100]}",
                reply_markup=build_back_button(),
            )
    
    # ==========================================
    # MAIN MENU HANDLERS
    # ==========================================
    
    async def _show_main_menu(self, query) -> None:
        """Show main menu."""
        user_id = query.from_user.id
        user_settings = self._user_settings.get_settings(user_id)
        
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
        except:
            sol_balance = 0.0
        
        open_positions = len(self._position_manager.get_all_positions(open_only=True))
        
        message = f"""
🚀 **Solana Trading Bot**

💰 **Balance:** {sol_balance:.4f} SOL
📊 **Open Positions:** {open_positions}

**Settings:**
• Amount: {user_settings.default_buy_amount_sol} SOL
• TP: {user_settings.take_profit_pct}%
• SL: {user_settings.stop_loss_pct}%

Select an option:
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_main_menu(),
            parse_mode="Markdown",
        )
    
    # ==========================================
    # TRADING HANDLERS
    # ==========================================
    
    async def _show_buy_prompt(self, query) -> None:
        """Prompt user for token address to buy."""
        user_id = query.from_user.id
        settings = self._user_settings.get_settings(user_id)
        
        self._pending[user_id] = {"action": "buy"}
        
        message = f"""
🟢 **Buy Token**

Current Settings:
• Amount: **{settings.default_buy_amount_sol} SOL**
• TP: {settings.take_profit_pct}% | SL: {settings.stop_loss_pct}%

━━━━━━━━━━━━━━━━━━━━

📝 **Now paste the token address:**

_Or paste a DEX Screener/Pump.fun link_
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button(),
            parse_mode="Markdown",
        )
    
    async def _show_sell_prompt(self, query) -> None:
        """Prompt user for token address to sell."""
        user_id = query.from_user.id
        self._pending[user_id] = {"action": "sell"}
        
        # Show open positions
        positions = self._position_manager.get_all_positions(open_only=True)
        
        if positions:
            message = "🔴 **Sell Token**\n\n**Open Positions:**\n\n"
            for pos in positions[:5]:
                pnl_emoji = "🟢" if pos.current_pnl_pct >= 0 else "🔴"
                message += f"{pnl_emoji} **{pos.token_symbol}** ({pos.current_pnl_pct:+.1f}%)\n"
            message += "\n📝 **Paste token address to sell:**"
        else:
            message = "🔴 **Sell Token**\n\n📝 Paste the token address to sell:"
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button(),
            parse_mode="Markdown",
        )
    
    async def _handle_buy_exec(self, query, data: str) -> None:
        """Handle buy execution with amount selection."""
        # Format: buy_exec_{amount}_{token_prefix}
        parts = data.replace("buy_exec_", "").split("_", 1)
        amount_str = parts[0]
        token_prefix = parts[1] if len(parts) > 1 else ""
        
        user_id = query.from_user.id
        settings = self._user_settings.get_settings(user_id)
        
        if amount_str == "default":
            amount = settings.default_buy_amount_sol
        else:
            amount = float(amount_str)
        
        # Get full token address from pending
        pending = self._pending.get(user_id, {})
        token_address = pending.get("token_address", "")
        
        if not token_address and token_prefix:
            # Try to find in recent tokens
            token_address = token_prefix  # Simplified for now
        
        if not token_address:
            await query.edit_message_text(
                "❌ Token address not found. Please try again.",
                reply_markup=build_back_button(),
            )
            return
        
        # Execute buy
        await self._execute_buy(query, token_address, amount, settings)
    
    async def _handle_buy_confirm(self, query, data: str) -> None:
        """Handle confirmed buy execution."""
        # Format: buy_confirm_{amount}_{token_prefix}
        parts = data.replace("buy_confirm_", "").split("_", 1)
        amount = float(parts[0])
        token_prefix = parts[1] if len(parts) > 1 else ""
        
        user_id = query.from_user.id
        settings = self._user_settings.get_settings(user_id)
        pending = self._pending.get(user_id, {})
        token_address = pending.get("token_address", token_prefix)
        
        await self._execute_buy(query, token_address, amount, settings)
    
    async def _execute_buy(self, query, token_address: str, amount: float, settings) -> None:
        """Execute buy order."""
        await query.edit_message_text(
            f"🔄 **Executing Buy...**\n\n"
            f"Amount: {amount} SOL\n"
            f"Token: `{token_address[:12]}...`",
            parse_mode="Markdown",
        )
        
        try:
            # Get token info
            token_info = await self._token_service.get_token_info(token_address)
            
            # Execute
            result = await self.executor.buy_token(
                token_mint=token_address,
                amount_sol=amount,
                slippage_bps=settings.slippage_bps,
            )
            
            if result.is_success:
                entry_price = token_info.price_usd if token_info else 0
                token_symbol = token_info.symbol if token_info else token_address[:8]
                
                # Add position
                if entry_price > 0 and settings.auto_tp_sl:
                    position = self._position_manager.add_position(
                        token_address=token_address,
                        token_symbol=token_symbol,
                        entry_price_usd=entry_price,
                        entry_amount_sol=amount,
                        entry_token_amount=result.output_amount or 0,
                        take_profit_pct=settings.take_profit_pct,
                        stop_loss_pct=settings.stop_loss_pct,
                    )
                    
                    await query.edit_message_text(
                        f"✅ **Buy Successful!**\n\n"
                        f"**Token:** {token_symbol}\n"
                        f"**Spent:** {amount} SOL\n\n"
                        f"📈 **TP:** {settings.take_profit_pct}%\n"
                        f"📉 **SL:** {settings.stop_loss_pct}%\n\n"
                        f"🔗 [View TX]({result.solscan_url})\n\n"
                        f"_Position #{position.id}_",
                        parse_mode="Markdown",
                        reply_markup=build_back_button(),
                    )
                else:
                    await query.edit_message_text(
                        f"✅ **Buy Successful!**\n\n"
                        f"🔗 [View TX]({result.solscan_url})",
                        parse_mode="Markdown",
                        reply_markup=build_back_button(),
                    )
            else:
                await query.edit_message_text(
                    f"❌ **Buy Failed**\n\n{result.error}",
                    parse_mode="Markdown",
                    reply_markup=build_back_button(),
                )
        except Exception as e:
            logger.error("execute_buy_error", error=str(e))
            await query.edit_message_text(
                f"❌ Error: {e}",
                reply_markup=build_back_button(),
            )
    
    async def _handle_quick_buy(self, query, data: str) -> None:
        """Quick buy from token info page."""
        # Format: qbuy_{amount}_{token_prefix}
        parts = data.replace("qbuy_", "").split("_", 1)
        amount = float(parts[0])
        token_prefix = parts[1] if len(parts) > 1 else ""
        
        user_id = query.from_user.id
        settings = self._user_settings.get_settings(user_id)
        
        await self._execute_buy(query, token_prefix, amount, settings)
    
    async def _handle_sell_exec(self, query, data: str) -> None:
        """Handle sell execution."""
        # TODO: Implement sell
        await query.edit_message_text(
            "🔴 Sell feature coming soon!",
            reply_markup=build_back_button(),
        )
    
    async def _handle_quick_sell(self, query, data: str) -> None:
        """Quick sell from token info page."""
        # TODO: Implement sell
        await query.edit_message_text(
            "🔴 Sell feature coming soon!",
            reply_markup=build_back_button(),
        )
    
    async def _refresh_token_info(self, query, data: str) -> None:
        """Refresh token info."""
        token_prefix = data.replace("token_refresh_", "")
        # TODO: Refetch and display token info
        await query.answer("Refreshing...")
    
    # ==========================================
    # POSITIONS HANDLERS
    # ==========================================
    
    async def _show_positions(self, query) -> None:
        """Show open positions."""
        positions = self._position_manager.get_all_positions(open_only=True)
        
        if not positions:
            message = "📊 **Open Positions**\n\nNo open positions.\n\nBuy a token to start!"
        else:
            message = "📊 **Open Positions**\n\n"
            for pos in positions:
                pnl_emoji = "🟢" if pos.current_pnl_pct >= 0 else "🔴"
                message += (
                    f"{pnl_emoji} **{pos.token_symbol}**\n"
                    f"   PnL: {pos.current_pnl_pct:+.1f}%\n"
                    f"   TP: {pos.take_profit_pct}% | SL: {pos.stop_loss_pct}%\n\n"
                )
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_positions_menu([p.to_dict() for p in positions]),
            parse_mode="Markdown",
        )
    
    async def _show_position_detail(self, query, data: str) -> None:
        """Show position detail."""
        pos_id = data.replace("pos_view_", "")
        position = self._position_manager.get_position(pos_id)
        
        if not position:
            await query.edit_message_text(
                "Position not found.",
                reply_markup=build_back_button("menu_positions"),
            )
            return
        
        pnl_emoji = "🟢" if position.current_pnl_pct >= 0 else "🔴"
        
        message = f"""
📊 **Position #{position.id}**

**Token:** {position.token_symbol}

**Entry:**
• Price: ${position.entry_price_usd:.8f}
• Amount: {position.entry_amount_sol} SOL
• Time: {position.entry_time.strftime("%H:%M %d/%m")}

**Current:**
• Price: ${position.current_price_usd:.8f}
• PnL: {pnl_emoji} {position.current_pnl_pct:+.1f}%

**Targets:**
• 📈 TP: {position.take_profit_pct}% (${position.tp_price:.8f})
• 📉 SL: {position.stop_loss_pct}% (${position.sl_price:.8f})
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_position_detail_menu(pos_id),
            parse_mode="Markdown",
        )
    
    async def _show_tp_options_for_position(self, query, data: str) -> None:
        """Show TP options for a position."""
        pos_id = data.replace("pos_tp_", "")
        # Show TP options with position ID
        await query.edit_message_text(
            "📈 **Update Take Profit**\n\nSelect new TP percentage:",
            reply_markup=build_tp_options(),
            parse_mode="Markdown",
        )
    
    async def _show_sl_options_for_position(self, query, data: str) -> None:
        """Show SL options for a position."""
        pos_id = data.replace("pos_sl_", "")
        await query.edit_message_text(
            "📉 **Update Stop Loss**\n\nSelect new SL percentage:",
            reply_markup=build_sl_options(),
            parse_mode="Markdown",
        )
    
    async def _close_position(self, query, data: str) -> None:
        """Close a position manually."""
        pos_id = data.replace("pos_close_", "")
        position = self._position_manager.close_position(pos_id, "manual")
        
        if position:
            await query.edit_message_text(
                f"✅ Position #{pos_id} closed.",
                reply_markup=build_back_button("menu_positions"),
            )
        else:
            await query.edit_message_text(
                "❌ Could not close position.",
                reply_markup=build_back_button("menu_positions"),
            )
    
    # ==========================================
    # WALLET HANDLERS
    # ==========================================
    
    async def _show_wallet_menu(self, query) -> None:
        """Show wallet management menu."""
        try:
            sol_balance = await self.solana.get_balance(self.wallet.address)
        except:
            sol_balance = 0.0
        
        message = f"""
💼 **Wallet**

**Address:**
`{self.wallet.address}`

**Balance:** {sol_balance:.4f} SOL

🔗 [View on Solscan](https://solscan.io/account/{self.wallet.address})
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_wallet_menu(),
            parse_mode="Markdown",
        )
    
    async def _show_balance(self, query) -> None:
        """Show wallet balance."""
        await self._show_wallet_menu(query)
    
    async def _show_deposit_info(self, query) -> None:
        """Show deposit information."""
        message = f"""
📥 **Deposit SOL**

Send SOL to this address:

`{self.wallet.address}`

⚠️ Only send SOL on Solana network!
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("wallet_manage"),
            parse_mode="Markdown",
        )
    
    async def _show_withdraw_prompt(self, query) -> None:
        """Show withdraw prompt."""
        message = """
📤 **Withdraw SOL**

To withdraw, use:
`/withdraw <address> <amount>`

Example:
`/withdraw 7xKXtg2CW87... 1.5`
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("wallet_manage"),
            parse_mode="Markdown",
        )
    
    async def _show_export_warning(self, query) -> None:
        """Show export key warning."""
        message = """
⚠️ **Export Private Key**

Your private key will be shown.
**Never share it with anyone!**

Use `/export` command in chat.
_The message will be auto-deleted after 30 seconds._
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("wallet_manage"),
            parse_mode="Markdown",
        )
    
    async def _generate_wallet(self, query) -> None:
        """Generate new wallet."""
        # Note: This bot uses a single configured wallet
        message = """
🆕 **Generate Wallet**

This bot uses your configured wallet.
Update `.env` file to change wallet.
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("wallet_manage"),
            parse_mode="Markdown",
        )
    
    async def _show_import_prompt(self, query) -> None:
        """Show import wallet prompt."""
        message = """
📥 **Import Wallet**

This bot uses your configured wallet.
Update `SOLANA_PRIVATE_KEY` in `.env` file.
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("wallet_manage"),
            parse_mode="Markdown",
        )
    
    # ==========================================
    # SETTINGS HANDLERS
    # ==========================================
    
    async def _show_settings(self, query) -> None:
        """Show settings menu."""
        user_id = query.from_user.id
        settings = self._user_settings.get_settings(user_id)
        message = self._user_settings.format_settings_message(user_id)
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_settings_menu(settings.to_dict()),
            parse_mode="Markdown",
        )
    
    async def _show_buy_amount_options(self, query) -> None:
        """Show buy amount options."""
        await query.edit_message_text(
            "💰 **Default Buy Amount**\n\nSelect amount:",
            reply_markup=build_buy_amount_options(),
            parse_mode="Markdown",
        )
    
    async def _show_tp_options(self, query) -> None:
        """Show TP options."""
        await query.edit_message_text(
            "📈 **Take Profit**\n\nSelect percentage:",
            reply_markup=build_tp_options(),
            parse_mode="Markdown",
        )
    
    async def _show_sl_options(self, query) -> None:
        """Show SL options."""
        await query.edit_message_text(
            "📉 **Stop Loss**\n\nSelect percentage:",
            reply_markup=build_sl_options(),
            parse_mode="Markdown",
        )
    
    async def _show_slippage_options(self, query) -> None:
        """Show slippage options."""
        await query.edit_message_text(
            "📊 **Slippage**\n\nSelect percentage:",
            reply_markup=build_slippage_options(),
            parse_mode="Markdown",
        )
    
    async def _toggle_auto_confirm(self, query) -> None:
        """Toggle auto buy confirmation."""
        user_id = query.from_user.id
        settings = self._user_settings.toggle_auto_confirm(user_id)
        
        status = "✅ ON" if settings.auto_buy_confirm else "❌ OFF"
        await query.answer(f"Auto Confirm: {status}")
        await self._show_settings(query)
    
    async def _set_buy_amount(self, query, data: str) -> None:
        """Set buy amount."""
        amount = float(data.replace("setamt_", ""))
        user_id = query.from_user.id
        self._user_settings.set_buy_amount(user_id, amount)
        
        await query.answer(f"Buy amount set to {amount} SOL")
        await self._show_settings(query)
    
    async def _set_tp(self, query, data: str) -> None:
        """Set take profit."""
        tp = float(data.replace("settp_", ""))
        user_id = query.from_user.id
        self._user_settings.set_tp(user_id, tp)
        
        await query.answer(f"Take Profit set to {tp}%")
        await self._show_settings(query)
    
    async def _set_sl(self, query, data: str) -> None:
        """Set stop loss."""
        sl = float(data.replace("setsl_", ""))
        user_id = query.from_user.id
        self._user_settings.set_sl(user_id, sl)
        
        await query.answer(f"Stop Loss set to {sl}%")
        await self._show_settings(query)
    
    async def _set_slippage(self, query, data: str) -> None:
        """Set slippage."""
        slippage = int(data.replace("setslip_", ""))
        user_id = query.from_user.id
        self._user_settings.update_settings(user_id, slippage_bps=slippage)
        
        await query.answer(f"Slippage set to {slippage/100}%")
        await self._show_settings(query)
    
    # ==========================================
    # COPY TRADING HANDLERS
    # ==========================================
    
    async def _show_copy_status(self, query) -> None:
        """Show copy trading status."""
        enabled = self.settings.copy_trading.enabled
        tracked = len(self.tracker.get_all_wallets()) if self.tracker else 0
        
        stats = {}
        if self.copy_trader:
            stats = self.copy_trader.get_stats()
        
        message = f"""
📋 **Copy Trading**

**Status:** {"🟢 Enabled" if enabled else "🔴 Disabled"}
**Tracked Wallets:** {tracked}

**Stats:**
• Detected: {stats.get('total_detected', 0)}
• Copied: {stats.get('total_copied', 0)}
• Skipped: {stats.get('total_skipped', 0)}
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_copy_trade_menu(enabled, tracked),
            parse_mode="Markdown",
        )
    
    async def _enable_copy_trading(self, query) -> None:
        """Enable copy trading."""
        self.settings.copy_trading.enabled = True
        if self.copy_trader:
            await self.copy_trader.start()
        await query.answer("Copy trading enabled!")
        await self._show_copy_status(query)
    
    async def _disable_copy_trading(self, query) -> None:
        """Disable copy trading."""
        self.settings.copy_trading.enabled = False
        if self.copy_trader:
            await self.copy_trader.stop()
        await query.answer("Copy trading disabled!")
        await self._show_copy_status(query)
    
    async def _show_add_wallet_prompt(self, query) -> None:
        """Show add wallet prompt."""
        message = """
➕ **Add Wallet to Track**

Use command:
`/track <wallet_address> <name>`

Example:
`/track 7xKXtg2CW87... AlphaTrader`
"""
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_back_button("menu_copy"),
            parse_mode="Markdown",
        )
    
    async def _show_tracked_wallets(self, query) -> None:
        """Show tracked wallets list."""
        if not self.tracker:
            await query.edit_message_text(
                "Wallet tracking not enabled.",
                reply_markup=build_back_button("menu_copy"),
            )
            return
        
        wallets = self.tracker.get_all_wallets()
        
        if not wallets:
            message = "📋 No wallets tracked.\n\nUse `/track <address>` to add one."
        else:
            message = "📋 **Tracked Wallets**\n\n"
            for w in wallets[:5]:
                message += f"**{w['name']}**\n`{w['address'][:12]}...`\n\n"
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=build_tracked_wallets_menu(wallets),
            parse_mode="Markdown",
        )
    
    async def _show_wallet_detail(self, query, data: str) -> None:
        """Show tracked wallet detail."""
        addr_prefix = data.replace("copy_wallet_", "")
        # Find wallet
        if not self.tracker:
            return
        
        wallets = self.tracker.get_all_wallets()
        wallet = None
        for w in wallets:
            if w['address'].startswith(addr_prefix):
                wallet = w
                break
        
        if not wallet:
            await query.edit_message_text(
                "Wallet not found.",
                reply_markup=build_back_button("copy_view_wallets"),
            )
            return
        
        message = f"""
👛 **{wallet['name']}**

**Address:**
`{wallet['address']}`

**Activity:**
• Swaps: {wallet['total_swaps']}
• Buys: 🟢 {wallet['total_buys']}
• Sells: 🔴 {wallet['total_sells']}

🔗 [View on Solscan](https://solscan.io/account/{wallet['address']})
"""
        short = wallet['address'][:16]
        keyboard = [
            [InlineKeyboardButton("🗑️ Remove", callback_data=f"copy_remove_{short}")],
            [InlineKeyboardButton("◀️ Back", callback_data="copy_view_wallets")],
        ]
        
        await query.edit_message_text(
            message.strip(),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    
    async def _remove_tracked_wallet(self, query, data: str) -> None:
        """Remove tracked wallet."""
        addr_prefix = data.replace("copy_remove_", "")
        
        if self.tracker:
            # Find and remove
            wallets = self.tracker.get_all_wallets()
            for w in wallets:
                if w['address'].startswith(addr_prefix):
                    self.tracker.remove_wallet(w['address'])
                    await query.answer("Wallet removed!")
                    break
        
        await self._show_tracked_wallets(query)
    
    # ==========================================
    # TEXT MESSAGE HANDLER
    # ==========================================
    
    async def process_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> bool:
        """
        Process text messages (token addresses, URLs).
        Returns True if handled.
        """
        if not self._is_admin(update.effective_user.id):
            return False
        
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        # Check for pending action
        pending = self._pending.get(user_id, {})
        
        # Try to extract token address
        token_address = TokenExtractor.extract_token(text)
        
        if token_address:
            # Store token address
            self._pending[user_id] = {
                **pending,
                "token_address": token_address,
            }
            
            action = pending.get("action")
            
            if action == "buy":
                # Show token info and buy confirmation
                await self._show_token_buy_prompt(update, token_address)
                return True
            elif action == "sell":
                # Show sell options
                await self._show_token_sell_prompt(update, token_address)
                return True
            else:
                # Default: show token info with quick actions
                await self._show_token_info(update, token_address)
                return True
        
        return False
    
    async def _show_token_buy_prompt(self, update: Update, token_address: str) -> None:
        """Show token info and buy options."""
        loading_msg = await update.message.reply_text("🔄 Fetching token info...")
        
        user_id = update.effective_user.id
        settings = self._user_settings.get_settings(user_id)
        
        try:
            info = await self._token_service.get_token_info(token_address)
            
            if info:
                tp_price = info.price_usd * (1 + settings.take_profit_pct / 100)
                sl_price = info.price_usd * (1 - settings.stop_loss_pct / 100)
                
                message = f"""
🟢 **Buy: {info.name} ({info.symbol})**

💵 **Price:** ${info.price_usd:.8f}
📊 **Market Cap:** ${info.market_cap:,.0f}
💧 **Liquidity:** ${info.liquidity_usd:,.0f}

━━━━━━━━━━━━━━━━━━━━

**Your Settings:**
• Amount: **{settings.default_buy_amount_sol} SOL**
• 📈 TP: {settings.take_profit_pct}% (${tp_price:.8f})
• 📉 SL: {settings.stop_loss_pct}% (${sl_price:.8f})

Select amount to buy:
"""
                await loading_msg.edit_text(
                    message.strip(),
                    reply_markup=build_buy_menu(token_address),
                    parse_mode="Markdown",
                )
            else:
                await loading_msg.edit_text(
                    f"⚠️ Token not found.\n\n`{token_address}`\n\nBuy anyway?",
                    reply_markup=build_buy_menu(token_address),
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error("show_token_buy_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error: {e}")
    
    async def _show_token_sell_prompt(self, update: Update, token_address: str) -> None:
        """Show token sell options."""
        message = f"""
🔴 **Sell Token**

`{token_address[:20]}...`

Select percentage to sell:
"""
        await update.message.reply_text(
            message.strip(),
            reply_markup=build_sell_menu(token_address),
            parse_mode="Markdown",
        )
    
    async def _show_token_info(self, update: Update, token_address: str) -> None:
        """Show token info with quick trade buttons."""
        loading_msg = await update.message.reply_text("🔄 Fetching token info...")
        
        try:
            info = await self._token_service.get_token_info(token_address)
            
            if info:
                message = self._token_service.format_token_message(info)
                await loading_msg.edit_text(
                    message,
                    reply_markup=build_token_action_menu(token_address, info.symbol),
                    parse_mode="Markdown",
                )
            else:
                await loading_msg.edit_text(
                    f"❌ Token not found.\n\n`{token_address}`",
                    reply_markup=build_back_button(),
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error("show_token_info_error", error=str(e))
            await loading_msg.edit_text(f"❌ Error: {e}")
    
    # ==========================================
    # PROPERTY ACCESSORS
    # ==========================================
    
    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager
    
    @property  
    def user_settings(self) -> UserSettingsManager:
        return self._user_settings
    
    @property
    def token_service(self) -> TokenInfoService:
        return self._token_service
