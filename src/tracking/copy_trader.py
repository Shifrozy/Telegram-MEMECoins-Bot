"""
Copy trading implementation for the Solana Trading Bot.

Automatically copies trades from tracked wallets based on
configurable rules and filters.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable, Awaitable, Dict, List

from src.config.logging_config import get_logger
from src.config.settings import Settings, CopyTradingConfig
from src.trading.models import TradeOrder, TradeResult, TradeStatus, TradeSource
from src.trading.executor import TradeExecutor
from src.tracking.wallet_tracker import WalletTracker, WalletActivity

logger = get_logger(__name__)


@dataclass
class CopyTradeDecision:
    """Decision about whether to copy a trade."""
    should_copy: bool
    reason: str
    adjusted_amount: Optional[int] = None
    
    @classmethod
    def accept(cls, amount: int, reason: str = "Passed all filters") -> "CopyTradeDecision":
        return cls(should_copy=True, reason=reason, adjusted_amount=amount)
    
    @classmethod
    def reject(cls, reason: str) -> "CopyTradeDecision":
        return cls(should_copy=False, reason=reason)


class CopyTrader:
    """
    Copies trades from tracked wallets.
    
    Features:
    - Configurable copy size (fixed, percentage, proportional)
    - Token whitelist/blacklist filtering
    - Min/max trade size limits
    - Buy/sell direction filtering
    - Configurable delay before copying
    """
    
    def __init__(
        self,
        settings: Settings,
        wallet_tracker: WalletTracker,
        trade_executor: TradeExecutor,
    ):
        """
        Initialize copy trader.
        
        Args:
            settings: Application settings
            wallet_tracker: Wallet tracker for detecting trades
            trade_executor: Executor for placing copy trades
        """
        self.settings = settings
        self.config = settings.copy_trading
        self.wallet_tracker = wallet_tracker
        self.executor = trade_executor
        
        # Callbacks
        self._on_copy_decision: Optional[Callable[[WalletActivity, CopyTradeDecision], Awaitable[None]]] = None
        self._on_copy_executed: Optional[Callable[[TradeResult], Awaitable[None]]] = None
        
        # Statistics
        self._total_detected = 0
        self._total_copied = 0
        self._total_skipped = 0
        self._copy_results: List[TradeResult] = []
        
        # State
        self._running = False
    
    def on_copy_decision(
        self,
        callback: Callable[[WalletActivity, CopyTradeDecision], Awaitable[None]],
    ) -> None:
        """Register callback for copy decisions."""
        self._on_copy_decision = callback
    
    def on_copy_executed(
        self,
        callback: Callable[[TradeResult], Awaitable[None]],
    ) -> None:
        """Register callback for executed copies."""
        self._on_copy_executed = callback
    
    async def start(self) -> None:
        """Start the copy trader."""
        if not self.config.enabled:
            logger.info("copy_trading_disabled")
            return
        
        if not self.config.tracked_wallets:
            logger.warning("no_wallets_to_copy")
            return
        
        self._running = True
        
        # Register callback with wallet tracker
        self.wallet_tracker.on_swap(self._on_swap_detected)
        
        logger.info(
            "copy_trader_started",
            tracked_wallets=len(self.config.tracked_wallets),
        )
    
    async def stop(self) -> None:
        """Stop the copy trader."""
        self._running = False
        logger.info("copy_trader_stopped")
    
    async def _on_swap_detected(self, activity: WalletActivity) -> None:
        """
        Handle a detected swap from a tracked wallet.
        
        Args:
            activity: Detected wallet activity
        """
        if not self._running or not activity.swap_info:
            return
        
        self._total_detected += 1
        
        logger.info(
            "copy_trade_candidate",
            wallet=activity.wallet_name,
            direction=activity.swap_info.direction.value,
            input_amount=activity.swap_info.input_amount,
        )
        
        # Evaluate if we should copy
        decision = await self._evaluate_copy(activity)
        
        # Notify of decision
        if self._on_copy_decision:
            try:
                await self._on_copy_decision(activity, decision)
            except Exception as e:
                logger.error("copy_decision_callback_error", error=str(e))
        
        if not decision.should_copy:
            self._total_skipped += 1
            logger.info(
                "copy_trade_skipped",
                reason=decision.reason,
            )
            return
        
        # Apply copy delay
        if self.config.copy_delay_seconds > 0:
            logger.debug(
                "copy_trade_delayed",
                delay=self.config.copy_delay_seconds,
            )
            await asyncio.sleep(self.config.copy_delay_seconds)
        
        # Execute the copy trade
        result = await self._execute_copy(activity, decision)
        
        self._total_copied += 1
        self._copy_results.append(result)
        
        # Notify of execution
        if self._on_copy_executed:
            try:
                await self._on_copy_executed(result)
            except Exception as e:
                logger.error("copy_executed_callback_error", error=str(e))
    
    async def _evaluate_copy(self, activity: WalletActivity) -> CopyTradeDecision:
        """
        Evaluate whether to copy a trade.
        
        Args:
            activity: Detected wallet activity
            
        Returns:
            CopyTradeDecision with reasoning
        """
        swap = activity.swap_info
        if not swap:
            return CopyTradeDecision.reject("No swap info available")
        
        filters = self.config.filters
        
        # Check direction filters
        if filters.buys_only and swap.direction.value != "buy":
            return CopyTradeDecision.reject("Sells not allowed (buys_only)")
        
        if filters.sells_only and swap.direction.value != "sell":
            return CopyTradeDecision.reject("Buys not allowed (sells_only)")
        
        # Check token whitelist
        if filters.token_whitelist:
            allowed_mints = set(filters.token_whitelist)
            if swap.output_mint not in allowed_mints and swap.input_mint not in allowed_mints:
                return CopyTradeDecision.reject("Token not in whitelist")
        
        # Check token blacklist
        if filters.token_blacklist:
            blocked_mints = set(filters.token_blacklist)
            if swap.output_mint in blocked_mints or swap.input_mint in blocked_mints:
                return CopyTradeDecision.reject("Token in blacklist")
        
        # Check trade size (approximate SOL value)
        trade_value_sol = self._estimate_sol_value(swap)
        
        if trade_value_sol < filters.min_trade_sol:
            return CopyTradeDecision.reject(
                f"Trade too small ({trade_value_sol:.4f} SOL < {filters.min_trade_sol} SOL)"
            )
        
        if trade_value_sol > filters.max_trade_sol:
            return CopyTradeDecision.reject(
                f"Trade too large ({trade_value_sol:.4f} SOL > {filters.max_trade_sol} SOL)"
            )
        
        # Calculate copy amount
        copy_amount = self._calculate_copy_amount(activity, trade_value_sol)
        
        if copy_amount <= 0:
            return CopyTradeDecision.reject("Calculated copy amount is zero")
        
        return CopyTradeDecision.accept(
            amount=copy_amount,
            reason=f"Copying {self.config.sizing_mode} mode",
        )
    
    def _estimate_sol_value(self, swap) -> float:
        """
        Estimate the SOL value of a swap.
        
        Args:
            swap: SwapInfo
            
        Returns:
            Estimated value in SOL
        """
        sol_mint = "So11111111111111111111111111111111111111112"
        
        # If input is SOL, use input amount
        if swap.input_mint == sol_mint:
            return swap.input_amount
        
        # If output is SOL, use output amount
        if swap.output_mint == sol_mint:
            return swap.output_amount
        
        # For token-to-token, estimate (simplified)
        # In production, you'd query price APIs
        return swap.input_amount  # Fallback
    
    def _calculate_copy_amount(
        self,
        activity: WalletActivity,
        original_sol_value: float,
    ) -> int:
        """
        Calculate the amount to copy.
        
        Args:
            activity: Original activity
            original_sol_value: Original trade value in SOL
            
        Returns:
            Amount in lamports
        """
        if self.config.sizing_mode == "fixed":
            # Fixed SOL amount
            sol_amount = self.config.fixed_size_sol
        
        elif self.config.sizing_mode == "percentage":
            # Percentage of original
            sol_amount = original_sol_value * (self.config.copy_percentage / 100)
        
        elif self.config.sizing_mode == "proportional":
            # TODO: Proportional to wallet balance ratio
            sol_amount = self.config.fixed_size_sol
        
        else:
            sol_amount = self.config.fixed_size_sol
        
        # Get wallet-specific override if exists
        for tracked in self.config.tracked_wallets:
            if tracked.address == activity.wallet_address:
                if hasattr(tracked, "copy_percentage") and tracked.copy_percentage:
                    sol_amount = original_sol_value * (tracked.copy_percentage / 100)
                break
        
        # Convert to lamports
        return int(sol_amount * 1_000_000_000)
    
    async def _execute_copy(
        self,
        activity: WalletActivity,
        decision: CopyTradeDecision,
    ) -> TradeResult:
        """
        Execute a copy trade.
        
        Args:
            activity: Original activity to copy
            decision: Copy decision with amount
            
        Returns:
            TradeResult
        """
        swap = activity.swap_info
        
        # Create order mirroring the original
        order = TradeOrder(
            input_mint=swap.input_mint,
            output_mint=swap.output_mint,
            amount=decision.adjusted_amount,
            slippage_bps=self.settings.trading.default_slippage_bps,
            source=TradeSource.COPY_TRADE,
            source_wallet=activity.wallet_address,
            source_signature=activity.signature,
        )
        
        logger.info(
            "executing_copy_trade",
            order_id=order.id,
            source_wallet=activity.wallet_name,
            amount=decision.adjusted_amount,
        )
        
        # Execute the trade
        result = await self.executor.execute_trade(order)
        
        log_level = "info" if result.is_success else "error"
        getattr(logger, log_level)(
            "copy_trade_result",
            order_id=order.id,
            status=result.status.value,
            signature=result.signature,
            error=result.error,
        )
        
        return result
    
    def get_stats(self) -> Dict:
        """Get copy trading statistics."""
        success_count = sum(1 for r in self._copy_results if r.is_success)
        
        return {
            "total_detected": self._total_detected,
            "total_copied": self._total_copied,
            "total_skipped": self._total_skipped,
            "success_count": success_count,
            "success_rate": (success_count / self._total_copied * 100) if self._total_copied > 0 else 0,
        }
    
    def get_recent_copies(self, limit: int = 10) -> List[TradeResult]:
        """Get recent copy trade results."""
        return self._copy_results[-limit:]
