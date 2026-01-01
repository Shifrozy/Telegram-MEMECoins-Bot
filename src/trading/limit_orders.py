"""
Limit Order Service

Manages limit orders (buy/sell at specific prices) with persistent storage.
Monitors prices and automatically executes when conditions are met.
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import uuid

from src.config.logging_config import get_logger
from src.trading.token_info import TokenInfoService
from src.trading.executor import TradeExecutor
from src.trading.models import TradeOrder, TradeSource

logger = get_logger(__name__)


class OrderType(str, Enum):
    """Type of limit order."""
    LIMIT_BUY = "limit_buy"      # Buy when price drops to target
    LIMIT_SELL = "limit_sell"    # Sell when price rises to target
    STOP_LOSS = "stop_loss"      # Sell when price drops to target
    TAKE_PROFIT = "take_profit"  # Sell when price rises to target


class OrderStatus(str, Enum):
    """Status of a limit order."""
    PENDING = "pending"
    TRIGGERED = "triggered"
    EXECUTING = "executing"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class LimitOrder:
    """A limit order."""
    id: str
    order_type: OrderType
    token_address: str
    token_symbol: str
    
    # Price conditions
    target_price_usd: float
    
    # Trade details
    amount_sol: float  # Amount of SOL to spend (buy) or tokens to sell (sell)
    
    # Status
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    triggered_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    
    # Execution details
    fill_price: Optional[float] = None
    fill_amount: Optional[float] = None
    signature: Optional[str] = None
    error: Optional[str] = None
    
    # Settings
    slippage_bps: int = 100
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        data = {
            "id": self.id,
            "order_type": self.order_type.value,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "target_price_usd": self.target_price_usd,
            "amount_sol": self.amount_sol,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "slippage_bps": self.slippage_bps,
        }
        
        if self.triggered_at:
            data["triggered_at"] = self.triggered_at.isoformat()
        if self.filled_at:
            data["filled_at"] = self.filled_at.isoformat()
        if self.fill_price:
            data["fill_price"] = self.fill_price
        if self.fill_amount:
            data["fill_amount"] = self.fill_amount
        if self.signature:
            data["signature"] = self.signature
        if self.error:
            data["error"] = self.error
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
            
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> "LimitOrder":
        """Create from dictionary."""
        order = cls(
            id=data["id"],
            order_type=OrderType(data["order_type"]),
            token_address=data["token_address"],
            token_symbol=data.get("token_symbol", "???"),
            target_price_usd=data["target_price_usd"],
            amount_sol=data["amount_sol"],
            status=OrderStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]),
            slippage_bps=data.get("slippage_bps", 100),
        )
        
        if data.get("triggered_at"):
            order.triggered_at = datetime.fromisoformat(data["triggered_at"])
        if data.get("filled_at"):
            order.filled_at = datetime.fromisoformat(data["filled_at"])
        if data.get("fill_price"):
            order.fill_price = data["fill_price"]
        if data.get("fill_amount"):
            order.fill_amount = data["fill_amount"]
        if data.get("signature"):
            order.signature = data["signature"]
        if data.get("error"):
            order.error = data["error"]
        if data.get("expires_at"):
            order.expires_at = datetime.fromisoformat(data["expires_at"])
            
        return order
    
    def check_condition(self, current_price: float) -> bool:
        """Check if order should be triggered."""
        if self.order_type == OrderType.LIMIT_BUY:
            # Buy when price drops to or below target
            return current_price <= self.target_price_usd
        elif self.order_type == OrderType.LIMIT_SELL:
            # Sell when price rises to or above target
            return current_price >= self.target_price_usd
        elif self.order_type == OrderType.STOP_LOSS:
            # Sell when price drops to or below target
            return current_price <= self.target_price_usd
        elif self.order_type == OrderType.TAKE_PROFIT:
            # Sell when price rises to or above target
            return current_price >= self.target_price_usd
        return False


class LimitOrderService:
    """
    Manages limit orders with price monitoring and automatic execution.
    """
    
    def __init__(
        self,
        token_service: TokenInfoService,
        executor: TradeExecutor,
        poll_interval: float = 10.0,
    ):
        """
        Initialize limit order service.
        
        Args:
            token_service: Token info service for price data
            executor: Trade executor for order execution
            poll_interval: Seconds between price checks
        """
        self.token_service = token_service
        self.executor = executor
        self.poll_interval = poll_interval
        
        # Orders storage
        self._orders: Dict[str, LimitOrder] = {}
        self._storage_path = Path("data/limit_orders.json")
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Callbacks
        self._on_order_triggered: Optional[Callable] = None
        self._on_order_filled: Optional[Callable] = None
        self._on_order_failed: Optional[Callable] = None
        
        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Load saved orders
        self._load_orders()
    
    def on_order_triggered(self, callback: Callable) -> None:
        """Register callback for order triggered."""
        self._on_order_triggered = callback
    
    def on_order_filled(self, callback: Callable) -> None:
        """Register callback for order filled."""
        self._on_order_filled = callback
    
    def on_order_failed(self, callback: Callable) -> None:
        """Register callback for order failed."""
        self._on_order_failed = callback
    
    async def start(self) -> None:
        """Start the limit order monitoring."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        
        pending_count = len(self.get_pending_orders())
        logger.info("limit_order_service_started", pending_orders=pending_count)
    
    async def stop(self) -> None:
        """Stop the limit order monitoring."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        self._save_orders()
        logger.info("limit_order_service_stopped")
    
    def create_order(
        self,
        order_type: OrderType,
        token_address: str,
        token_symbol: str,
        target_price_usd: float,
        amount_sol: float,
        slippage_bps: int = 100,
        expires_hours: Optional[int] = None,
    ) -> LimitOrder:
        """
        Create a new limit order.
        
        Args:
            order_type: Type of order
            token_address: Token mint address
            token_symbol: Token symbol for display
            target_price_usd: Target price in USD
            amount_sol: Amount of SOL
            slippage_bps: Slippage in basis points
            expires_hours: Hours until expiration (None = no expiry)
            
        Returns:
            Created LimitOrder
        """
        order_id = str(uuid.uuid4())[:8]
        
        expires_at = None
        if expires_hours:
            from datetime import timedelta
            expires_at = datetime.now() + timedelta(hours=expires_hours)
        
        order = LimitOrder(
            id=order_id,
            order_type=order_type,
            token_address=token_address,
            token_symbol=token_symbol,
            target_price_usd=target_price_usd,
            amount_sol=amount_sol,
            slippage_bps=slippage_bps,
            expires_at=expires_at,
        )
        
        self._orders[order_id] = order
        self._save_orders()
        
        logger.info(
            "limit_order_created",
            order_id=order_id,
            type=order_type.value,
            token=token_symbol,
            target_price=target_price_usd,
        )
        
        return order
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id not in self._orders:
            return False
        
        order = self._orders[order_id]
        if order.status != OrderStatus.PENDING:
            return False
        
        order.status = OrderStatus.CANCELLED
        self._save_orders()
        
        logger.info("limit_order_cancelled", order_id=order_id)
        return True
    
    def get_order(self, order_id: str) -> Optional[LimitOrder]:
        """Get an order by ID."""
        return self._orders.get(order_id)
    
    def get_pending_orders(self) -> List[LimitOrder]:
        """Get all pending orders."""
        return [o for o in self._orders.values() if o.status == OrderStatus.PENDING]
    
    def get_all_orders(self) -> List[LimitOrder]:
        """Get all orders."""
        return list(self._orders.values())
    
    def get_orders_for_token(self, token_address: str) -> List[LimitOrder]:
        """Get orders for a specific token."""
        return [o for o in self._orders.values() if o.token_address == token_address]
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_orders()
            except Exception as e:
                logger.error("limit_order_monitor_error", error=str(e))
            
            await asyncio.sleep(self.poll_interval)
    
    async def _check_orders(self) -> None:
        """Check all pending orders."""
        pending = self.get_pending_orders()
        
        if not pending:
            return
        
        # Group by token to minimize API calls
        tokens = {}
        for order in pending:
            if order.token_address not in tokens:
                tokens[order.token_address] = []
            tokens[order.token_address].append(order)
        
        # Check each token
        for token_address, orders in tokens.items():
            try:
                # Get current price
                token_info = await self.token_service.get_token_info(token_address)
                
                if not token_info or token_info.price_usd == 0:
                    continue
                
                current_price = token_info.price_usd
                
                # Check each order for this token
                for order in orders:
                    # Check expiration
                    if order.expires_at and datetime.now() > order.expires_at:
                        order.status = OrderStatus.EXPIRED
                        self._save_orders()
                        continue
                    
                    # Check if condition is met
                    if order.check_condition(current_price):
                        await self._execute_order(order, current_price)
                        
            except Exception as e:
                logger.error(
                    "order_check_error",
                    token=token_address[:8],
                    error=str(e),
                )
    
    async def _execute_order(self, order: LimitOrder, current_price: float) -> None:
        """Execute a triggered order."""
        order.status = OrderStatus.TRIGGERED
        order.triggered_at = datetime.now()
        
        logger.info(
            "limit_order_triggered",
            order_id=order.id,
            token=order.token_symbol,
            target=order.target_price_usd,
            current=current_price,
        )
        
        # Notify
        if self._on_order_triggered:
            try:
                await self._on_order_triggered(order, current_price)
            except Exception as e:
                logger.error("trigger_callback_error", error=str(e))
        
        order.status = OrderStatus.EXECUTING
        self._save_orders()
        
        try:
            # Determine if buy or sell
            is_buy = order.order_type in [OrderType.LIMIT_BUY]
            
            if is_buy:
                # Execute buy
                result = await self.executor.buy(
                    token_mint=order.token_address,
                    sol_amount=order.amount_sol,
                    slippage_bps=order.slippage_bps,
                    source=TradeSource.LIMIT_ORDER,
                )
            else:
                # Execute sell
                result = await self.executor.sell(
                    token_mint=order.token_address,
                    token_amount=order.amount_sol,  # This should be token amount
                    slippage_bps=order.slippage_bps,
                    source=TradeSource.LIMIT_ORDER,
                )
            
            if result.is_success:
                order.status = OrderStatus.FILLED
                order.filled_at = datetime.now()
                order.fill_price = current_price
                order.fill_amount = result.output_amount
                order.signature = result.signature
                
                logger.info(
                    "limit_order_filled",
                    order_id=order.id,
                    signature=result.signature,
                )
                
                if self._on_order_filled:
                    try:
                        await self._on_order_filled(order, result)
                    except Exception as e:
                        logger.error("filled_callback_error", error=str(e))
            else:
                order.status = OrderStatus.FAILED
                order.error = result.error
                
                logger.error(
                    "limit_order_failed",
                    order_id=order.id,
                    error=result.error,
                )
                
                if self._on_order_failed:
                    try:
                        await self._on_order_failed(order, result.error)
                    except Exception as e:
                        logger.error("failed_callback_error", error=str(e))
                        
        except Exception as e:
            order.status = OrderStatus.FAILED
            order.error = str(e)
            logger.error("order_execution_error", order_id=order.id, error=str(e))
        
        self._save_orders()
    
    def _save_orders(self) -> None:
        """Save orders to file."""
        try:
            data = [order.to_dict() for order in self._orders.values()]
            
            with open(self._storage_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error("save_orders_error", error=str(e))
    
    def _load_orders(self) -> None:
        """Load orders from file."""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, 'r') as f:
                    data = json.load(f)
                
                for order_data in data:
                    order = LimitOrder.from_dict(order_data)
                    self._orders[order.id] = order
                
                logger.info("limit_orders_loaded", count=len(self._orders))
                
        except Exception as e:
            logger.error("load_orders_error", error=str(e))
    
    def format_order_message(self, order: LimitOrder) -> str:
        """Format order as Telegram message."""
        type_emoji = {
            OrderType.LIMIT_BUY: "🟢 Limit Buy",
            OrderType.LIMIT_SELL: "🔴 Limit Sell",
            OrderType.STOP_LOSS: "🔴 Stop Loss",
            OrderType.TAKE_PROFIT: "🟢 Take Profit",
        }
        
        status_emoji = {
            OrderStatus.PENDING: "⏳ Pending",
            OrderStatus.TRIGGERED: "⚡ Triggered",
            OrderStatus.EXECUTING: "🔄 Executing",
            OrderStatus.FILLED: "✅ Filled",
            OrderStatus.CANCELLED: "❌ Cancelled",
            OrderStatus.FAILED: "💥 Failed",
            OrderStatus.EXPIRED: "⏰ Expired",
        }
        
        message = f"""
📋 **Limit Order** `{order.id}`

**Type:** {type_emoji.get(order.order_type, order.order_type.value)}
**Token:** {order.token_symbol}
**Status:** {status_emoji.get(order.status, order.status.value)}

**Target Price:** ${order.target_price_usd:.8f}
**Amount:** {order.amount_sol} SOL

**Created:** {order.created_at.strftime('%Y-%m-%d %H:%M')}
"""
        
        if order.expires_at:
            message += f"**Expires:** {order.expires_at.strftime('%Y-%m-%d %H:%M')}\n"
        
        if order.status == OrderStatus.FILLED:
            message += f"\n**Fill Price:** ${order.fill_price:.8f}\n"
            if order.signature:
                message += f"🔗 [View TX](https://solscan.io/tx/{order.signature})\n"
        
        if order.error:
            message += f"\n⚠️ **Error:** {order.error}\n"
        
        return message.strip()
    
    def format_orders_list(self, orders: List[LimitOrder]) -> str:
        """Format list of orders."""
        if not orders:
            return "No orders found."
        
        message = "📋 **Your Limit Orders**\n\n"
        
        for order in orders[:10]:  # Show max 10
            type_emoji = "🟢" if "buy" in order.order_type.value or "profit" in order.order_type.value else "🔴"
            status = "⏳" if order.status == OrderStatus.PENDING else "✅" if order.status == OrderStatus.FILLED else "❌"
            
            message += (
                f"{status} `{order.id}` {type_emoji} {order.token_symbol}\n"
                f"   @ ${order.target_price_usd:.6f} • {order.amount_sol} SOL\n\n"
            )
        
        if len(orders) > 10:
            message += f"_...and {len(orders) - 10} more_\n"
        
        return message
