"""
PnL tracker for monitored wallets.

Tracks profit and loss for wallets over time by analyzing
their trading history.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import json

from src.config.logging_config import get_logger
from src.blockchain.transaction import SwapInfo, SwapDirection

logger = get_logger(__name__)


@dataclass
class TokenPosition:
    """Tracks a position in a single token."""
    mint: str
    symbol: str = ""
    
    # Entry info
    total_bought: float = 0.0
    total_sold: float = 0.0
    total_cost_sol: float = 0.0
    total_proceeds_sol: float = 0.0
    
    # Current state
    current_holdings: float = 0.0
    current_value_sol: float = 0.0
    
    # First/last activity
    first_buy_time: Optional[datetime] = None
    last_activity_time: Optional[datetime] = None
    
    @property
    def average_buy_price(self) -> float:
        """Average price paid per token."""
        if self.total_bought > 0:
            return self.total_cost_sol / self.total_bought
        return 0.0
    
    @property
    def average_sell_price(self) -> float:
        """Average price received per token."""
        if self.total_sold > 0:
            return self.total_proceeds_sol / self.total_sold
        return 0.0
    
    @property
    def realized_pnl(self) -> float:
        """Realized PnL in SOL from closed positions."""
        if self.total_sold == 0:
            return 0.0
        
        # Cost basis for sold tokens
        sold_cost = self.average_buy_price * self.total_sold
        return self.total_proceeds_sol - sold_cost
    
    @property
    def unrealized_pnl(self) -> float:
        """Unrealized PnL in SOL from current holdings."""
        if self.current_holdings == 0:
            return 0.0
        
        # Cost basis for held tokens
        held_cost = self.average_buy_price * self.current_holdings
        return self.current_value_sol - held_cost
    
    @property
    def total_pnl(self) -> float:
        """Total PnL (realized + unrealized) in SOL."""
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def roi_percentage(self) -> float:
        """Return on investment percentage."""
        if self.total_cost_sol > 0:
            return (self.total_pnl / self.total_cost_sol) * 100
        return 0.0
    
    def record_buy(
        self,
        amount: float,
        cost_sol: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record a buy transaction."""
        self.total_bought += amount
        self.total_cost_sol += cost_sol
        self.current_holdings += amount
        
        timestamp = timestamp or datetime.now()
        
        if self.first_buy_time is None:
            self.first_buy_time = timestamp
        
        self.last_activity_time = timestamp
    
    def record_sell(
        self,
        amount: float,
        proceeds_sol: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record a sell transaction."""
        self.total_sold += amount
        self.total_proceeds_sol += proceeds_sol
        self.current_holdings = max(0, self.current_holdings - amount)
        
        self.last_activity_time = timestamp or datetime.now()
    
    def update_current_value(self, price_per_token: float) -> None:
        """Update current value based on market price."""
        self.current_value_sol = self.current_holdings * price_per_token
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "mint": self.mint,
            "symbol": self.symbol,
            "total_bought": self.total_bought,
            "total_sold": self.total_sold,
            "total_cost_sol": self.total_cost_sol,
            "total_proceeds_sol": self.total_proceeds_sol,
            "current_holdings": self.current_holdings,
            "current_value_sol": self.current_value_sol,
            "average_buy_price": self.average_buy_price,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_pnl": self.total_pnl,
            "roi_percentage": self.roi_percentage,
        }


@dataclass
class WalletPnL:
    """PnL tracking for a single wallet."""
    address: str
    name: str
    
    # Token positions
    positions: Dict[str, TokenPosition] = field(default_factory=dict)
    
    # Aggregate stats
    total_trades: int = 0
    total_buys: int = 0
    total_sells: int = 0
    
    # Time tracking
    tracking_since: Optional[datetime] = None
    
    def get_position(self, mint: str) -> TokenPosition:
        """Get or create a position for a token."""
        if mint not in self.positions:
            self.positions[mint] = TokenPosition(mint=mint)
        return self.positions[mint]
    
    @property
    def total_realized_pnl(self) -> float:
        """Total realized PnL across all positions."""
        return sum(p.realized_pnl for p in self.positions.values())
    
    @property
    def total_unrealized_pnl(self) -> float:
        """Total unrealized PnL across all positions."""
        return sum(p.unrealized_pnl for p in self.positions.values())
    
    @property
    def total_pnl(self) -> float:
        """Total PnL (realized + unrealized) across all positions."""
        return self.total_realized_pnl + self.total_unrealized_pnl
    
    @property
    def total_invested(self) -> float:
        """Total SOL invested."""
        return sum(p.total_cost_sol for p in self.positions.values())
    
    @property
    def winning_positions(self) -> int:
        """Count of positions with positive PnL."""
        return sum(1 for p in self.positions.values() if p.total_pnl > 0)
    
    @property
    def losing_positions(self) -> int:
        """Count of positions with negative PnL."""
        return sum(1 for p in self.positions.values() if p.total_pnl < 0)
    
    @property
    def win_rate(self) -> float:
        """Win rate percentage."""
        total = self.winning_positions + self.losing_positions
        if total > 0:
            return (self.winning_positions / total) * 100
        return 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "address": self.address,
            "name": self.name,
            "total_trades": self.total_trades,
            "total_buys": self.total_buys,
            "total_sells": self.total_sells,
            "total_realized_pnl": self.total_realized_pnl,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_pnl": self.total_pnl,
            "total_invested": self.total_invested,
            "winning_positions": self.winning_positions,
            "losing_positions": self.losing_positions,
            "win_rate": self.win_rate,
            "positions_count": len(self.positions),
        }


class PnLTracker:
    """
    Tracks PnL for monitored wallets.
    
    Analyzes swap transactions to build position data
    and calculate realized/unrealized PnL.
    """
    
    # SOL mint address
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    # Stablecoin mints (treated as SOL-equivalent for PnL)
    STABLE_MINTS = {
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    }
    
    def __init__(self):
        """Initialize PnL tracker."""
        self._wallets: Dict[str, WalletPnL] = {}
    
    def add_wallet(self, address: str, name: str = "Unknown") -> WalletPnL:
        """
        Add a wallet to track.
        
        Args:
            address: Wallet address
            name: Human-readable name
            
        Returns:
            WalletPnL instance
        """
        if address not in self._wallets:
            self._wallets[address] = WalletPnL(
                address=address,
                name=name,
                tracking_since=datetime.now(),
            )
            logger.info(
                "pnl_wallet_added",
                address=address[:8] + "...",
                name=name,
            )
        return self._wallets[address]
    
    def process_swap(self, swap: SwapInfo) -> None:
        """
        Process a swap transaction for PnL tracking.
        
        Args:
            swap: SwapInfo from transaction parser
        """
        wallet = self._wallets.get(swap.signer)
        if not wallet:
            wallet = self.add_wallet(swap.signer)
        
        wallet.total_trades += 1
        
        # Determine trade direction and update positions
        if swap.direction == SwapDirection.BUY:
            # Bought token with SOL/stable
            wallet.total_buys += 1
            
            position = wallet.get_position(swap.output_mint)
            position.record_buy(
                amount=swap.output_amount,
                cost_sol=self._to_sol_value(swap.input_mint, swap.input_amount),
                timestamp=swap.block_time,
            )
            
            logger.debug(
                "pnl_buy_recorded",
                wallet=wallet.name,
                token=swap.output_mint[:8] + "...",
                amount=swap.output_amount,
                cost=swap.input_amount,
            )
        
        elif swap.direction == SwapDirection.SELL:
            # Sold token for SOL/stable
            wallet.total_sells += 1
            
            position = wallet.get_position(swap.input_mint)
            position.record_sell(
                amount=swap.input_amount,
                proceeds_sol=self._to_sol_value(swap.output_mint, swap.output_amount),
                timestamp=swap.block_time,
            )
            
            logger.debug(
                "pnl_sell_recorded",
                wallet=wallet.name,
                token=swap.input_mint[:8] + "...",
                amount=swap.input_amount,
                proceeds=swap.output_amount,
            )
        
        else:
            # Token-to-token swap - treat as sell + buy
            logger.debug(
                "pnl_token_swap",
                input=swap.input_mint[:8] + "...",
                output=swap.output_mint[:8] + "...",
            )
    
    def _to_sol_value(self, mint: str, amount: float) -> float:
        """
        Convert an amount to SOL value.
        
        Args:
            mint: Token mint
            amount: Token amount
            
        Returns:
            Equivalent SOL value
        """
        if mint == self.SOL_MINT:
            return amount
        
        if mint in self.STABLE_MINTS:
            # Approximate: 1 USDC ≈ current SOL price
            # In production, fetch real price
            return amount / 200  # Placeholder
        
        return amount  # Fallback
    
    def get_wallet_pnl(self, address: str) -> Optional[WalletPnL]:
        """Get PnL data for a wallet."""
        return self._wallets.get(address)
    
    def get_all_wallets_pnl(self) -> List[Dict]:
        """Get PnL summary for all wallets."""
        return [wallet.to_dict() for wallet in self._wallets.values()]
    
    def get_top_performers(self, limit: int = 10) -> List[WalletPnL]:
        """Get wallets sorted by total PnL."""
        sorted_wallets = sorted(
            self._wallets.values(),
            key=lambda w: w.total_pnl,
            reverse=True,
        )
        return sorted_wallets[:limit]
    
    def get_top_positions(
        self,
        wallet_address: Optional[str] = None,
        limit: int = 10,
    ) -> List[TokenPosition]:
        """Get top positions by PnL."""
        if wallet_address:
            wallet = self._wallets.get(wallet_address)
            if not wallet:
                return []
            positions = list(wallet.positions.values())
        else:
            positions = []
            for wallet in self._wallets.values():
                positions.extend(wallet.positions.values())
        
        sorted_positions = sorted(
            positions,
            key=lambda p: p.total_pnl,
            reverse=True,
        )
        return sorted_positions[:limit]
    
    def format_pnl_report(self, address: str) -> str:
        """
        Generate a formatted PnL report for a wallet.
        
        Args:
            address: Wallet address
            
        Returns:
            Formatted report string
        """
        wallet = self._wallets.get(address)
        if not wallet:
            return "Wallet not found"
        
        report = f"""
📊 **PnL Report: {wallet.name}**
`{address[:8]}...{address[-4:]}`

**Summary:**
• Total Trades: {wallet.total_trades} ({wallet.total_buys} buys, {wallet.total_sells} sells)
• Total Invested: {wallet.total_invested:.4f} SOL

**Performance:**
• Realized PnL: {wallet.total_realized_pnl:+.4f} SOL
• Unrealized PnL: {wallet.total_unrealized_pnl:+.4f} SOL
• **Total PnL: {wallet.total_pnl:+.4f} SOL**

**Win Rate:**
• 🟢 Winning: {wallet.winning_positions}
• 🔴 Losing: {wallet.losing_positions}
• Rate: {wallet.win_rate:.1f}%
"""
        
        # Add top positions
        if wallet.positions:
            report += "\n**Top Positions:**\n"
            sorted_positions = sorted(
                wallet.positions.values(),
                key=lambda p: abs(p.total_pnl),
                reverse=True,
            )[:5]
            
            for pos in sorted_positions:
                emoji = "🟢" if pos.total_pnl >= 0 else "🔴"
                report += f"{emoji} {pos.mint[:8]}...: {pos.total_pnl:+.4f} SOL ({pos.roi_percentage:+.1f}%)\n"
        
        return report.strip()
    
    def save_to_file(self, filepath: str) -> None:
        """Save PnL data to file."""
        data = {
            address: wallet.to_dict()
            for address, wallet in self._wallets.items()
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info("pnl_data_saved", filepath=filepath)
    
    def load_from_file(self, filepath: str) -> None:
        """Load PnL data from file."""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            # TODO: Reconstruct WalletPnL objects from data
            logger.info("pnl_data_loaded", filepath=filepath)
        except Exception as e:
            logger.error("pnl_load_error", error=str(e))
