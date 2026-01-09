"""
Position Manager - Automatic TP/SL Trading

Manages open positions with:
- Take Profit (TP) monitoring
- Stop Loss (SL) monitoring
- Auto-sell when targets hit
- Multiple position support
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable
from enum import Enum

from src.config.logging_config import get_logger
from src.trading.token_info import TokenInfoService

logger = get_logger(__name__)


class PositionStatus(Enum):
    """Position status."""
    OPEN = "open"
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    MANUAL_CLOSE = "manual_close"
    FAILED = "failed"


@dataclass
class Position:
    """
    Represents an open trading position.
    """
    id: str
    token_address: str
    token_symbol: str
    
    # Entry details
    entry_price_usd: float
    entry_amount_sol: float
    entry_token_amount: float
    entry_time: datetime
    
    # TP/SL settings (percentages)
    take_profit_pct: float = 50.0  # 50% gain = sell
    stop_loss_pct: float = 25.0   # 25% loss = sell
    
    # Current state
    current_price_usd: float = 0.0
    current_pnl_pct: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    
    # Exit details
    exit_price_usd: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    exit_signature: Optional[str] = None
    
    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = PositionStatus(self.status)
        if isinstance(self.entry_time, str):
            self.entry_time = datetime.fromisoformat(self.entry_time)
        if isinstance(self.exit_time, str):
            self.exit_time = datetime.fromisoformat(self.exit_time)
    
    @property
    def tp_price(self) -> float:
        """Calculate Take Profit price."""
        return self.entry_price_usd * (1 + self.take_profit_pct / 100)
    
    @property
    def sl_price(self) -> float:
        """Calculate Stop Loss price."""
        return self.entry_price_usd * (1 - self.stop_loss_pct / 100)
    
    @property
    def is_open(self) -> bool:
        """Check if position is still open."""
        return self.status == PositionStatus.OPEN
    
    def check_targets(self) -> Optional[str]:
        """
        Check if TP or SL is hit.
        
        Returns:
            'tp' if take profit hit, 'sl' if stop loss hit, None otherwise
        """
        if not self.is_open or self.current_price_usd <= 0:
            return None
        
        # Calculate current PnL percentage
        self.current_pnl_pct = ((self.current_price_usd - self.entry_price_usd) / self.entry_price_usd) * 100
        
        # Check Take Profit
        if self.current_pnl_pct >= self.take_profit_pct:
            return "tp"
        
        # Check Stop Loss
        if self.current_pnl_pct <= -self.stop_loss_pct:
            return "sl"
        
        return None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['status'] = self.status.value
        data['entry_time'] = self.entry_time.isoformat()
        if self.exit_time:
            data['exit_time'] = self.exit_time.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        """Create from dictionary."""
        return cls(**data)


class PositionManager:
    """
    Manages trading positions with automatic TP/SL monitoring.
    
    Features:
    - Track multiple open positions
    - Background price monitoring
    - Auto-execute sells on TP/SL hit
    - Persistent storage
    """
    
    def __init__(
        self,
        token_service: TokenInfoService,
        executor=None,  # TradeExecutor
        data_dir: str = "data",
        poll_interval: float = 10.0,  # Check prices every 10 seconds
    ):
        self.token_service = token_service
        self.executor = executor
        self.poll_interval = poll_interval
        
        # Storage
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.positions_file = self.data_dir / "positions.json"
        
        # Positions
        self.positions: Dict[str, Position] = {}
        
        # Callbacks
        self._on_tp_hit: Optional[Callable[[Position], Awaitable[None]]] = None
        self._on_sl_hit: Optional[Callable[[Position], Awaitable[None]]] = None
        self._on_position_closed: Optional[Callable[[Position], Awaitable[None]]] = None
        
        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Load existing positions
        self._load_positions()
    
    def _load_positions(self) -> None:
        """Load positions from file."""
        if not self.positions_file.exists():
            return
        
        try:
            with open(self.positions_file, "r") as f:
                data = json.load(f)
            
            for pos_data in data.get("positions", []):
                try:
                    pos = Position.from_dict(pos_data)
                    if pos.is_open:
                        self.positions[pos.id] = pos
                except Exception as e:
                    logger.error("load_position_error", error=str(e))
            
            logger.info("positions_loaded", count=len(self.positions))
        except Exception as e:
            logger.error("load_positions_file_error", error=str(e))
    
    def _save_positions(self) -> None:
        """Save positions to file."""
        try:
            data = {
                "positions": [p.to_dict() for p in self.positions.values()],
                "last_updated": datetime.now().isoformat(),
            }
            with open(self.positions_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("save_positions_error", error=str(e))
    
    def on_tp_hit(self, callback: Callable[[Position], Awaitable[None]]) -> None:
        """Register callback for Take Profit hit."""
        self._on_tp_hit = callback
    
    def on_sl_hit(self, callback: Callable[[Position], Awaitable[None]]) -> None:
        """Register callback for Stop Loss hit."""
        self._on_sl_hit = callback
    
    def on_position_closed(self, callback: Callable[[Position], Awaitable[None]]) -> None:
        """Register callback for position closed."""
        self._on_position_closed = callback
    
    async def start(self) -> None:
        """Start the position monitoring loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("position_manager_started")
    
    async def stop(self) -> None:
        """Stop the position monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        self._save_positions()
        logger.info("position_manager_stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main loop that monitors all open positions."""
        while self._running:
            try:
                await self._check_all_positions()
            except Exception as e:
                logger.error("monitoring_loop_error", error=str(e))
            
            await asyncio.sleep(self.poll_interval)
    
    async def _check_all_positions(self) -> None:
        """Check TP/SL for all open positions."""
        if not self.positions:
            return
        
        for pos_id, position in list(self.positions.items()):
            if not position.is_open:
                continue
            
            try:
                # Get current price
                token_info = await self.token_service.get_token_info(position.token_address)
                if not token_info:
                    continue
                
                position.current_price_usd = token_info.price_usd
                
                # Check targets
                target_hit = position.check_targets()
                
                if target_hit == "tp":
                    await self._execute_tp(position)
                elif target_hit == "sl":
                    await self._execute_sl(position)
                
            except Exception as e:
                logger.error(
                    "check_position_error",
                    position_id=pos_id,
                    error=str(e),
                )
    
    async def _execute_tp(self, position: Position) -> None:
        """Execute Take Profit sell."""
        logger.info(
            "take_profit_hit",
            token=position.token_symbol,
            entry_price=position.entry_price_usd,
            current_price=position.current_price_usd,
            pnl_pct=position.current_pnl_pct,
        )
        
        position.status = PositionStatus.TP_HIT
        position.exit_price_usd = position.current_price_usd
        position.exit_time = datetime.now()
        position.exit_reason = "Take Profit"
        
        # Execute sell if executor available
        if self.executor:
            try:
                result = await self.executor.sell_token(
                    token_mint=position.token_address,
                    amount=position.entry_token_amount,
                    decimals=9,  # Most memecoins use 9
                )
                position.exit_signature = result.signature
            except Exception as e:
                logger.error("tp_sell_error", error=str(e))
                position.status = PositionStatus.FAILED
        
        self._save_positions()
        
        if self._on_tp_hit:
            await self._on_tp_hit(position)
        if self._on_position_closed:
            await self._on_position_closed(position)
    
    async def _execute_sl(self, position: Position) -> None:
        """Execute Stop Loss sell."""
        logger.info(
            "stop_loss_hit",
            token=position.token_symbol,
            entry_price=position.entry_price_usd,
            current_price=position.current_price_usd,
            pnl_pct=position.current_pnl_pct,
        )
        
        position.status = PositionStatus.SL_HIT
        position.exit_price_usd = position.current_price_usd
        position.exit_time = datetime.now()
        position.exit_reason = "Stop Loss"
        
        # Execute sell if executor available
        if self.executor:
            try:
                result = await self.executor.sell_token(
                    token_mint=position.token_address,
                    amount=position.entry_token_amount,
                    decimals=9,
                )
                position.exit_signature = result.signature
            except Exception as e:
                logger.error("sl_sell_error", error=str(e))
                position.status = PositionStatus.FAILED
        
        self._save_positions()
        
        if self._on_sl_hit:
            await self._on_sl_hit(position)
        if self._on_position_closed:
            await self._on_position_closed(position)
    
    def add_position(
        self,
        token_address: str,
        token_symbol: str,
        entry_price_usd: float,
        entry_amount_sol: float,
        entry_token_amount: float,
        take_profit_pct: float = 50.0,
        stop_loss_pct: float = 25.0,
    ) -> Position:
        """
        Add a new position to track.
        
        Args:
            token_address: Token mint address
            token_symbol: Token symbol
            entry_price_usd: Price at entry in USD
            entry_amount_sol: SOL amount spent
            entry_token_amount: Token amount received
            take_profit_pct: Take profit percentage (default 50%)
            stop_loss_pct: Stop loss percentage (default 25%)
        
        Returns:
            Created Position
        """
        import uuid
        pos_id = str(uuid.uuid4())[:8]
        
        position = Position(
            id=pos_id,
            token_address=token_address,
            token_symbol=token_symbol,
            entry_price_usd=entry_price_usd,
            entry_amount_sol=entry_amount_sol,
            entry_token_amount=entry_token_amount,
            entry_time=datetime.now(),
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            current_price_usd=entry_price_usd,
        )
        
        self.positions[pos_id] = position
        self._save_positions()
        
        logger.info(
            "position_added",
            id=pos_id,
            token=token_symbol,
            entry_price=entry_price_usd,
            tp_pct=take_profit_pct,
            sl_pct=stop_loss_pct,
        )
        
        return position
    
    def close_position(self, position_id: str, reason: str = "manual") -> Optional[Position]:
        """
        Manually close a position.
        
        Args:
            position_id: Position ID
            reason: Close reason
        
        Returns:
            Closed position or None
        """
        if position_id not in self.positions:
            return None
        
        position = self.positions[position_id]
        position.status = PositionStatus.MANUAL_CLOSE
        position.exit_time = datetime.now()
        position.exit_reason = reason
        
        self._save_positions()
        
        logger.info("position_closed", id=position_id, reason=reason)
        return position
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a position by ID."""
        return self.positions.get(position_id)
    
    def get_position_by_token(self, token_address: str) -> Optional[Position]:
        """Get open position for a token."""
        for pos in self.positions.values():
            if pos.token_address == token_address and pos.is_open:
                return pos
        return None
    
    def get_all_positions(self, open_only: bool = True) -> List[Position]:
        """Get all positions."""
        if open_only:
            return [p for p in self.positions.values() if p.is_open]
        return list(self.positions.values())
    
    def get_stats(self) -> dict:
        """Get position statistics."""
        all_positions = list(self.positions.values())
        open_positions = [p for p in all_positions if p.is_open]
        closed_positions = [p for p in all_positions if not p.is_open]
        
        tp_wins = len([p for p in closed_positions if p.status == PositionStatus.TP_HIT])
        sl_losses = len([p for p in closed_positions if p.status == PositionStatus.SL_HIT])
        
        return {
            "total_positions": len(all_positions),
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "tp_wins": tp_wins,
            "sl_losses": sl_losses,
            "win_rate": (tp_wins / len(closed_positions) * 100) if closed_positions else 0,
        }
    
    def update_tp_sl(
        self,
        position_id: str,
        take_profit_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
    ) -> Optional[Position]:
        """
        Update TP/SL for a position.
        
        Args:
            position_id: Position ID
            take_profit_pct: New TP percentage
            stop_loss_pct: New SL percentage
        
        Returns:
            Updated position or None
        """
        if position_id not in self.positions:
            return None
        
        position = self.positions[position_id]
        
        if take_profit_pct is not None:
            position.take_profit_pct = take_profit_pct
        
        if stop_loss_pct is not None:
            position.stop_loss_pct = stop_loss_pct
        
        self._save_positions()
        return position
