"""
Trade data models for the Solana Trading Bot.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class TradeStatus(Enum):
    """Trade execution status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class TradeType(Enum):
    """Type of trade."""
    BUY = "buy"
    SELL = "sell"
    SWAP = "swap"


class TradeSource(Enum):
    """Source of the trade."""
    MANUAL = "manual"           # User-initiated trade
    COPY_TRADE = "copy_trade"   # Copy trade from tracked wallet
    AUTOMATED = "automated"     # Automated strategy
    LIMIT_ORDER = "limit_order" # Limit order execution


@dataclass
class TradeOrder:
    """
    Represents a trade order to be executed.
    
    Contains all parameters needed to execute a swap on Jupiter.
    """
    # Core parameters
    input_mint: str
    output_mint: str
    amount: int  # Raw amount in smallest units
    
    # Trade metadata
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trade_type: TradeType = TradeType.SWAP
    source: TradeSource = TradeSource.MANUAL
    
    # Swap parameters
    slippage_bps: int = 100  # 1%
    
    # Optional parameters
    priority_fee_lamports: int = 0
    exact_in: bool = True  # True = exact input, False = exact output
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    
    # Copy trade reference
    source_wallet: Optional[str] = None
    source_signature: Optional[str] = None
    
    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order (SOL/stable -> token)."""
        base_mints = {
            "So11111111111111111111111111111111111111112",  # SOL
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
        }
        return self.input_mint in base_mints
    
    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order (token -> SOL/stable)."""
        return not self.is_buy
    
    def __str__(self) -> str:
        direction = "BUY" if self.is_buy else "SELL"
        return (
            f"TradeOrder({direction} {self.id}: "
            f"{self.input_mint[:8]}... -> {self.output_mint[:8]}... "
            f"amount={self.amount})"
        )


@dataclass
class QuoteInfo:
    """
    Quote information from the Jupiter API.
    """
    input_mint: str
    output_mint: str
    in_amount: int
    out_amount: int
    price_impact_pct: float
    slippage_bps: int
    
    # Routing info
    route_plan: list = field(default_factory=list)
    
    # Fees
    platform_fee: Optional[int] = None
    
    @property
    def in_amount_sol(self) -> float:
        """Get input amount in SOL (assuming 9 decimals)."""
        return self.in_amount / 1_000_000_000
    
    @property
    def out_amount_human(self) -> float:
        """Get output amount (assuming 6 decimals for USDC)."""
        return self.out_amount / 1_000_000
    
    @property
    def price(self) -> float:
        """Calculate effective price."""
        if self.in_amount > 0:
            return self.out_amount / self.in_amount
        return 0.0


@dataclass
class TradeResult:
    """
    Result of a trade execution attempt.
    
    Contains final status, signature, and any error information.
    """
    # Order reference
    order_id: str
    order: TradeOrder
    
    # Execution result
    status: TradeStatus
    signature: Optional[str] = None
    
    # Amounts
    input_amount: Optional[int] = None
    output_amount: Optional[int] = None
    
    # Error handling
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    # Timestamps
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    
    # Transaction details
    slot: Optional[int] = None
    fee_lamports: Optional[int] = None
    
    @property
    def is_success(self) -> bool:
        """Check if trade was successful."""
        return self.status == TradeStatus.CONFIRMED
    
    @property
    def is_failed(self) -> bool:
        """Check if trade failed."""
        return self.status in {TradeStatus.FAILED, TradeStatus.EXPIRED}
    
    @property
    def solscan_url(self) -> Optional[str]:
        """Get Solscan URL for the transaction."""
        if self.signature:
            return f"https://solscan.io/tx/{self.signature}"
        return None
    
    def format_result(self) -> str:
        """Format result for display."""
        if self.is_success:
            emoji = "✅"
            status_text = "CONFIRMED"
        elif self.is_failed:
            emoji = "❌"
            status_text = "FAILED"
        else:
            emoji = "⏳"
            status_text = self.status.value.upper()
        
        message = f"{emoji} Trade {status_text}"
        
        if self.signature:
            message += f"\n🔗 Signature: {self.signature[:16]}..."
        
        if self.error:
            message += f"\n⚠️ Error: {self.error}"
        
        return message
    
    def __str__(self) -> str:
        return f"TradeResult({self.order_id}: {self.status.value})"


@dataclass
class Position:
    """
    Represents an open position in a token.
    """
    token_mint: str
    entry_price: float
    entry_amount: float
    entry_time: datetime
    
    # Current state
    current_amount: float = 0.0
    current_price: float = 0.0
    
    # Related trades
    entry_signature: Optional[str] = None
    exit_signature: Optional[str] = None
    
    # PnL tracking
    realized_pnl: float = 0.0
    
    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized PnL."""
        if self.entry_price > 0:
            return (self.current_price - self.entry_price) / self.entry_price * 100
        return 0.0
    
    @property
    def value(self) -> float:
        """Current position value."""
        return self.current_amount * self.current_price
    
    @property
    def is_open(self) -> bool:
        """Check if position is still open."""
        return self.current_amount > 0
    
    def __str__(self) -> str:
        return (
            f"Position({self.token_mint[:8]}...: "
            f"amount={self.current_amount:.4f}, "
            f"pnl={self.unrealized_pnl:+.2f}%)"
        )


@dataclass
class DailyStats:
    """Daily trading statistics."""
    date: datetime
    
    # Trade counts
    total_trades: int = 0
    successful_trades: int = 0
    failed_trades: int = 0
    
    # Volumes
    buy_volume_sol: float = 0.0
    sell_volume_sol: float = 0.0
    
    # PnL
    realized_pnl_sol: float = 0.0
    fees_paid_sol: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate trade success rate."""
        if self.total_trades > 0:
            return self.successful_trades / self.total_trades * 100
        return 0.0
    
    @property
    def net_pnl_sol(self) -> float:
        """Net PnL after fees."""
        return self.realized_pnl_sol - self.fees_paid_sol
