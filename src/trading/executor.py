"""
Trade executor for the Solana Trading Bot.

Orchestrates the full trade flow from order creation through execution.
"""

import base64
from datetime import datetime
from typing import Optional, Callable, Awaitable

from solders.transaction import VersionedTransaction

from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.blockchain.wallet import WalletManager
from src.trading.jupiter import JupiterClient, QuoteResponse, ExecuteResponse, JupiterError
from src.trading.models import TradeOrder, TradeResult, TradeStatus, TradeSource

logger = get_logger(__name__)


class TradeExecutor:
    """
    Executes trades on Solana DEXs via Jupiter.
    
    Handles the complete flow:
    1. Get quote from Jupiter
    2. Sign transaction with wallet
    3. Execute via Jupiter Ultra
    4. Poll for confirmation
    5. Return result
    """
    
    def __init__(
        self,
        settings: Settings,
        jupiter: JupiterClient,
        wallet: WalletManager,
    ):
        """
        Initialize the trade executor.
        
        Args:
            settings: Application settings
            jupiter: Jupiter API client
            wallet: Wallet manager for signing
        """
        self.settings = settings
        self.jupiter = jupiter
        self.wallet = wallet
        
        # Trade callbacks
        self._on_trade_submitted: Optional[Callable[[TradeOrder], Awaitable[None]]] = None
        self._on_trade_completed: Optional[Callable[[TradeResult], Awaitable[None]]] = None
        
        # Statistics
        self._total_trades = 0
        self._successful_trades = 0
        self._failed_trades = 0
    
    def on_trade_submitted(
        self,
        callback: Callable[[TradeOrder], Awaitable[None]],
    ) -> None:
        """Register callback for when trade is submitted."""
        self._on_trade_submitted = callback
    
    def on_trade_completed(
        self,
        callback: Callable[[TradeResult], Awaitable[None]],
    ) -> None:
        """Register callback for when trade completes."""
        self._on_trade_completed = callback
    
    async def execute_trade(
        self,
        order: TradeOrder,
    ) -> TradeResult:
        """
        Execute a trade order.
        
        Flow:
        1. Get order/quote from Jupiter
        2. Sign the transaction
        3. Execute via Jupiter Ultra
        4. Poll for confirmation
        5. Return result
        
        Args:
            order: Trade order to execute
            
        Returns:
            TradeResult with execution status
        """
        self._total_trades += 1
        
        logger.info(
            "trade_execution_started",
            order_id=order.id,
            input_mint=order.input_mint[:8] + "...",
            output_mint=order.output_mint[:8] + "...",
            amount=order.amount,
        )
        
        try:
            # Step 1: Get quote and transaction from Jupiter
            quote = await self._get_quote(order)
            
            # Step 2: Sign the transaction
            signed_tx = await self._sign_transaction(quote)
            
            # Notify that trade is submitted
            if self._on_trade_submitted:
                await self._on_trade_submitted(order)
            
            # Step 3: Execute via Jupiter
            result = await self._execute_and_confirm(
                order=order,
                quote=quote,
                signed_transaction=signed_tx,
            )
            
            # Update statistics
            if result.is_success:
                self._successful_trades += 1
            else:
                self._failed_trades += 1
            
            # Notify completion
            if self._on_trade_completed:
                await self._on_trade_completed(result)
            
            return result
            
        except JupiterError as e:
            logger.error(
                "trade_execution_failed",
                order_id=order.id,
                error=str(e),
                code=e.code,
            )
            
            self._failed_trades += 1
            
            result = TradeResult(
                order_id=order.id,
                order=order,
                status=TradeStatus.FAILED,
                error=str(e),
                error_code=e.code,
            )
            
            if self._on_trade_completed:
                await self._on_trade_completed(result)
            
            return result
            
        except Exception as e:
            logger.error(
                "trade_execution_error",
                order_id=order.id,
                error=str(e),
            )
            
            self._failed_trades += 1
            
            result = TradeResult(
                order_id=order.id,
                order=order,
                status=TradeStatus.FAILED,
                error=f"Unexpected error: {e}",
            )
            
            if self._on_trade_completed:
                await self._on_trade_completed(result)
            
            return result
    
    async def _get_quote(self, order: TradeOrder) -> QuoteResponse:
        """Get quote from Jupiter."""
        quote = await self.jupiter.get_order(
            input_mint=order.input_mint,
            output_mint=order.output_mint,
            amount=order.amount,
            taker=self.wallet.address,
            slippage_bps=order.slippage_bps,
        )
        
        logger.info(
            "trade_quote_received",
            order_id=order.id,
            in_amount=quote.in_amount,
            out_amount=quote.out_amount,
            price=quote.price,
        )
        
        return quote
    
    async def _sign_transaction(self, quote: QuoteResponse) -> str:
        """
        Sign the transaction from Jupiter.
        
        Args:
            quote: Quote response containing transaction
            
        Returns:
            Base64 encoded signed transaction
        """
        # Decode and deserialize transaction
        tx_bytes = base64.b64decode(quote.transaction)
        transaction = VersionedTransaction.from_bytes(tx_bytes)
        
        # Sign with wallet
        signed_tx = self.wallet.sign_transaction(transaction)
        
        # Serialize and encode
        signed_bytes = bytes(signed_tx)
        signed_b64 = base64.b64encode(signed_bytes).decode()
        
        logger.debug(
            "transaction_signed",
            request_id=quote.request_id,
        )
        
        return signed_b64
    
    async def _execute_and_confirm(
        self,
        order: TradeOrder,
        quote: QuoteResponse,
        signed_transaction: str,
    ) -> TradeResult:
        """
        Execute transaction and wait for confirmation.
        
        Args:
            order: Original trade order
            quote: Quote response
            signed_transaction: Signed transaction
            
        Returns:
            TradeResult with final status
        """
        submitted_at = datetime.now()
        
        # Execute via Jupiter Ultra
        response = await self.jupiter.poll_transaction_status(
            signed_transaction=signed_transaction,
            request_id=quote.request_id,
            max_attempts=20,  # ~40 seconds total
            poll_interval=2.0,
        )
        
        confirmed_at = datetime.now() if response.is_success else None
        
        # Build result
        if response.is_success:
            status = TradeStatus.CONFIRMED
        elif response.error:
            status = TradeStatus.FAILED
        else:
            status = TradeStatus.EXPIRED
        
        return TradeResult(
            order_id=order.id,
            order=order,
            status=status,
            signature=response.signature,
            input_amount=response.input_amount or quote.in_amount,
            output_amount=response.output_amount or quote.out_amount,
            error=response.error,
            error_code=response.error_code,
            submitted_at=submitted_at,
            confirmed_at=confirmed_at,
            slot=response.slot,
        )
    
    async def quick_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount_sol: float,
        slippage_bps: Optional[int] = None,
    ) -> TradeResult:
        """
        Quick swap with sensible defaults.
        
        Convenience method for simple swaps without building
        a full TradeOrder.
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount_sol: Amount in SOL (or token UI amount)
            slippage_bps: Optional slippage override
            
        Returns:
            TradeResult
        """
        # Convert to lamports (assuming SOL input)
        amount = int(amount_sol * 1_000_000_000)
        
        order = TradeOrder(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=amount,
            slippage_bps=slippage_bps or self.settings.trading.default_slippage_bps,
            source=TradeSource.MANUAL,
        )
        
        return await self.execute_trade(order)
    
    async def buy_token(
        self,
        token_mint: str,
        amount_sol: float,
        slippage_bps: Optional[int] = None,
    ) -> TradeResult:
        """
        Buy a token with SOL.
        
        Args:
            token_mint: Token to buy
            amount_sol: Amount of SOL to spend
            slippage_bps: Optional slippage override
            
        Returns:
            TradeResult
        """
        sol_mint = "So11111111111111111111111111111111111111112"
        return await self.quick_swap(
            input_mint=sol_mint,
            output_mint=token_mint,
            amount_sol=amount_sol,
            slippage_bps=slippage_bps,
        )
    
    async def sell_token(
        self,
        token_mint: str,
        amount: float,
        decimals: int = 9,
        slippage_bps: Optional[int] = None,
    ) -> TradeResult:
        """
        Sell a token for SOL.
        
        Args:
            token_mint: Token to sell
            amount: Token amount (UI amount, not raw)
            decimals: Token decimals
            slippage_bps: Optional slippage override
            
        Returns:
            TradeResult
        """
        sol_mint = "So11111111111111111111111111111111111111112"
        
        # Convert to raw amount
        raw_amount = int(amount * (10 ** decimals))
        
        order = TradeOrder(
            input_mint=token_mint,
            output_mint=sol_mint,
            amount=raw_amount,
            slippage_bps=slippage_bps or self.settings.trading.default_slippage_bps,
            source=TradeSource.MANUAL,
        )
        
        return await self.execute_trade(order)
    
    def get_stats(self) -> dict:
        """Get execution statistics."""
        success_rate = 0.0
        if self._total_trades > 0:
            success_rate = self._successful_trades / self._total_trades * 100
        
        return {
            "total_trades": self._total_trades,
            "successful_trades": self._successful_trades,
            "failed_trades": self._failed_trades,
            "success_rate": success_rate,
        }


async def create_trade_executor(
    settings: Settings,
    jupiter: JupiterClient,
    wallet: WalletManager,
) -> TradeExecutor:
    """
    Create a configured trade executor.
    
    Args:
        settings: Application settings
        jupiter: Jupiter client
        wallet: Wallet manager
        
    Returns:
        Configured TradeExecutor
    """
    return TradeExecutor(
        settings=settings,
        jupiter=jupiter,
        wallet=wallet,
    )
