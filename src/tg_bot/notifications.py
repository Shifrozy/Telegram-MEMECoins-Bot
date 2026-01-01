"""
Notification service for sending alerts via Telegram.
"""

from typing import Optional
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.trading.models import TradeResult, TradeStatus
from src.tracking.wallet_tracker import WalletActivity
from src.tracking.copy_trader import CopyTradeDecision
from src.blockchain.transaction import SwapInfo, SwapDirection, format_swap_message, TransactionParser
from src.tg_bot.keyboards import build_main_menu

logger = get_logger(__name__)


class NotificationService:
    """
    Handles sending notifications to Telegram.
    
    Provides formatted alerts for:
    - Trade executions
    - Trade failures
    - Wallet activity
    - Copy trading events
    - Balance changes
    - Errors
    """
    
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        settings: Settings,
    ):
        """
        Initialize notification service.
        
        Args:
            bot: Telegram Bot instance
            chat_id: Chat ID to send messages to
            settings: Application settings
        """
        self.bot = bot
        self.chat_id = chat_id
        self.settings = settings
        self.alerts = settings.telegram.alerts
        
        self.tx_parser = TransactionParser()
    
    async def send_message(
        self,
        text: str,
        parse_mode: str = ParseMode.MARKDOWN,
        disable_notification: bool = False,
    ) -> bool:
        """
        Send a message to the configured chat.
        
        Args:
            text: Message text
            parse_mode: Telegram parse mode
            disable_notification: Silent message
            
        Returns:
            True if sent successfully
        """
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
            )
            return True
        except TelegramError as e:
            logger.error("telegram_send_error", error=str(e))
            return False
    
    async def notify_trade_executed(self, result: TradeResult) -> None:
        """
        Notify about a trade execution.
        
        Args:
            result: TradeResult from execution
        """
        if not self.alerts.trade_execution and result.is_success:
            return
        
        if result.is_success:
            emoji = "✅"
            title = "Trade Executed"
        else:
            if not self.alerts.trade_failure:
                return
            emoji = "❌"
            title = "Trade Failed"
        
        order = result.order
        direction = "BUY" if order.is_buy else "SELL"
        
        # Format amounts
        input_amount = result.input_amount or order.amount
        output_amount = result.output_amount or 0
        
        # Convert from raw amounts
        in_display = input_amount / 1e9  # Assuming SOL decimals
        out_display = output_amount / 1e9
        
        message = f"""
{emoji} **{title}**

**{direction}** Trade `{order.id}`

📤 Input: `{order.input_mint[:8]}...`
   Amount: {in_display:.6f}
   
📥 Output: `{order.output_mint[:8]}...`
   Amount: {out_display:.6f}
"""
        
        if result.signature:
            message += f"\n🔗 [View on Solscan]({result.solscan_url})"
        
        if result.error:
            message += f"\n\n⚠️ **Error:** {result.error}"
        
        await self.send_message(message.strip())
    
    async def notify_wallet_activity(self, activity: WalletActivity) -> None:
        """
        Notify about wallet activity.
        
        Args:
            activity: Detected wallet activity
        """
        if not self.alerts.wallet_activity:
            return
        
        if activity.swap_info:
            # Format swap notification
            swap = activity.swap_info
            message = format_swap_message(swap, self.tx_parser)
            message = f"👁️ **Wallet Activity: {activity.wallet_name}**\n\n" + message
        else:
            message = f"""
👁️ **Wallet Activity**

Wallet: {activity.wallet_name}
`{activity.wallet_address[:8]}...{activity.wallet_address[-4:]}`

Type: {activity.activity_type}

🔗 [View Transaction](https://solscan.io/tx/{activity.signature})
"""
        
        await self.send_message(message.strip())
    
    async def notify_copy_trade(
        self,
        activity: WalletActivity,
        decision: CopyTradeDecision,
        result: Optional[TradeResult] = None,
    ) -> None:
        """
        Notify about a copy trade decision/execution.
        
        Args:
            activity: Original wallet activity
            decision: Copy decision made
            result: Optional trade result if executed
        """
        if not self.alerts.copy_trade:
            return
        
        swap = activity.swap_info
        if not swap:
            return
        
        direction = swap.direction.value.upper()
        emoji = "🟢" if swap.direction == SwapDirection.BUY else "🔴"
        
        if decision.should_copy:
            copy_amount_sol = (decision.adjusted_amount or 0) / 1e9
            
            message = f"""
📋 **Copy Trade**

{emoji} Copying **{direction}** from {activity.wallet_name}

**Original Trade:**
• Input: {swap.input_amount:.6f}
• Output: {swap.output_amount:.6f}

**Copy Amount:** {copy_amount_sol:.4f} SOL
"""
            
            if result:
                if result.is_success:
                    message += f"\n✅ **Executed:** [View]({result.solscan_url})"
                else:
                    message += f"\n❌ **Failed:** {result.error}"
        else:
            message = f"""
📋 **Copy Trade Skipped**

{emoji} {activity.wallet_name} {direction}

**Reason:** {decision.reason}

🔗 [Original TX](https://solscan.io/tx/{activity.signature})
"""
        
        await self.send_message(message.strip())
    
    async def notify_balance_change(
        self,
        token: str,
        old_balance: float,
        new_balance: float,
        token_symbol: str = "Unknown",
    ) -> None:
        """
        Notify about a balance change.
        
        Args:
            token: Token mint address
            old_balance: Previous balance
            new_balance: New balance
            token_symbol: Token symbol
        """
        if not self.alerts.balance_change:
            return
        
        change = new_balance - old_balance
        emoji = "📈" if change > 0 else "📉"
        
        message = f"""
{emoji} **Balance Change**

**{token_symbol}**
`{token[:8]}...{token[-4:]}`

Old: {old_balance:.6f}
New: {new_balance:.6f}
Change: {change:+.6f}
"""
        
        await self.send_message(message.strip())
    
    async def notify_error(
        self,
        error_type: str,
        message: str,
        details: Optional[str] = None,
    ) -> None:
        """
        Send an error notification.
        
        Args:
            error_type: Type of error
            message: Error message
            details: Optional additional details
        """
        if not self.alerts.error_notifications:
            return
        
        error_msg = f"""
🚨 **Error: {error_type}**

{message}
"""
        
        if details:
            error_msg += f"\n```\n{details[:500]}\n```"
        
        await self.send_message(error_msg.strip())
    
    async def send_startup_message(
        self,
        wallet_address: str,
        sol_balance: float,
    ) -> None:
        """
        Send bot startup confirmation with menu buttons.
        
        Args:
            wallet_address: Bot's wallet address
            sol_balance: Current SOL balance
        """
        message = f"""
🚀 **Solana Trading Bot Started**

**Wallet:** `{wallet_address[:8]}...{wallet_address[-4:]}`
**Balance:** {sol_balance:.4f} SOL
**Network:** {self.settings.network}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━
**Select an option below:**
"""
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message.strip(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=build_main_menu(),
            )
        except TelegramError as e:
            logger.error("startup_message_error", error=str(e))
            # Fallback without buttons
            await self.send_message(message.strip())
    
    async def send_shutdown_message(self) -> None:
        """Send bot shutdown notification."""
        message = """
⏹️ **Bot Shutting Down**

The trading bot is going offline.
"""
        
        await self.send_message(message.strip())
