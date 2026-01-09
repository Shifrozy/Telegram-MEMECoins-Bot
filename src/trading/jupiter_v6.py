"""
Jupiter V6 Swap API client for broader token support.

The V6 API supports more tokens including those on Raydium pools,
which is needed for graduated pump.fun tokens.
"""

import base64
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Jupiter V6 API (better token support than Ultra)
JUPITER_V6_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUPITER_V6_SWAP = "https://quote-api.jup.ag/v6/swap"


@dataclass 
class SwapResult:
    """Result from swap execution."""
    success: bool
    signature: Optional[str] = None
    input_amount: Optional[int] = None
    output_amount: Optional[int] = None
    error: Optional[str] = None
    
    @property
    def solscan_url(self) -> str:
        if self.signature:
            return f"https://solscan.io/tx/{self.signature}"
        return ""


class JupiterV6Client:
    """
    Jupiter V6 Swap API client.
    
    Supports all tokens including:
    - Raydium pools
    - Orca pools
    - Graduated pump.fun tokens
    - Standard SPL tokens
    """
    
    def __init__(
        self,
        keypair: Keypair,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        timeout: int = 30,
    ):
        """
        Initialize Jupiter V6 client.
        
        Args:
            keypair: Wallet keypair for signing
            rpc_url: Solana RPC endpoint
            timeout: Request timeout
        """
        self.keypair = keypair
        self.rpc_url = rpc_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50,
    ) -> Optional[Dict[str, Any]]:
        """
        Get swap quote from Jupiter V6.
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount: Amount in smallest units
            slippage_bps: Slippage in basis points
            
        Returns:
            Quote data or None
        """
        client = await self._get_client()
        
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps),
            "onlyDirectRoutes": "false",
            "asLegacyTransaction": "false",
        }
        
        try:
            resp = await client.get(JUPITER_V6_QUOTE, params=params)
            
            if resp.status_code == 200:
                data = resp.json()
                logger.info(
                    "jupiter_v6_quote",
                    in_amount=data.get("inAmount"),
                    out_amount=data.get("outAmount"),
                )
                return data
            else:
                logger.error("jupiter_v6_quote_error", status=resp.status_code, error=resp.text[:200])
                return None
                
        except Exception as e:
            logger.error("jupiter_v6_quote_exception", error=str(e))
            return None
    
    async def swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50,
    ) -> SwapResult:
        """
        Execute a swap using Jupiter V6.
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount: Amount in smallest units
            slippage_bps: Slippage in basis points
            
        Returns:
            SwapResult
        """
        client = await self._get_client()
        wallet = str(self.keypair.pubkey())
        
        # Step 1: Get quote
        quote = await self.get_quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=amount,
            slippage_bps=slippage_bps,
        )
        
        if not quote:
            return SwapResult(success=False, error="Failed to get quote")
        
        # Step 2: Get swap transaction
        try:
            swap_resp = await client.post(
                JUPITER_V6_SWAP,
                json={
                    "quoteResponse": quote,
                    "userPublicKey": wallet,
                    "wrapAndUnwrapSol": True,
                    "dynamicComputeUnitLimit": True,
                    "prioritizationFeeLamports": "auto",
                },
            )
            
            if swap_resp.status_code != 200:
                return SwapResult(success=False, error=f"Swap API error: {swap_resp.text[:200]}")
            
            swap_data = swap_resp.json()
            
        except Exception as e:
            return SwapResult(success=False, error=f"Swap request failed: {e}")
        
        # Step 3: Sign and send transaction
        try:
            tx_base64 = swap_data.get("swapTransaction")
            if not tx_base64:
                return SwapResult(success=False, error="No transaction in response")
            
            # Decode transaction
            tx_bytes = base64.b64decode(tx_base64)
            transaction = VersionedTransaction.from_bytes(tx_bytes)
            
            # Sign the transaction
            signed_tx = VersionedTransaction(
                transaction.message,
                [self.keypair],
            )
            
            # Send to Solana
            signed_bytes = bytes(signed_tx)
            
            send_resp = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        base64.b64encode(signed_bytes).decode(),
                        {
                            "encoding": "base64",
                            "skipPreflight": True,
                            "maxRetries": 3,
                        }
                    ]
                },
                headers={"Content-Type": "application/json"},
            )
            
            send_data = send_resp.json()
            
            if "result" in send_data:
                signature = send_data["result"]
                logger.info("jupiter_v6_swap_success", signature=signature)
                return SwapResult(
                    success=True,
                    signature=signature,
                    input_amount=int(quote.get("inAmount", 0)),
                    output_amount=int(quote.get("outAmount", 0)),
                )
            else:
                error = send_data.get("error", {})
                error_msg = error.get("message", str(error))
                logger.error("jupiter_v6_send_error", error=error_msg)
                return SwapResult(success=False, error=error_msg)
                
        except Exception as e:
            logger.error("jupiter_v6_sign_error", error=str(e))
            return SwapResult(success=False, error=str(e))
    
    async def buy_token(
        self,
        token_mint: str,
        amount_sol: float,
        slippage_bps: int = 100,
    ) -> SwapResult:
        """
        Buy a token with SOL.
        
        Args:
            token_mint: Token to buy
            amount_sol: SOL amount to spend
            slippage_bps: Slippage in basis points
            
        Returns:
            SwapResult
        """
        sol_mint = "So11111111111111111111111111111111111111112"
        amount_lamports = int(amount_sol * 1_000_000_000)
        
        logger.info(
            "jupiter_v6_buy",
            token=token_mint[:8] + "...",
            amount_sol=amount_sol,
        )
        
        return await self.swap(
            input_mint=sol_mint,
            output_mint=token_mint,
            amount=amount_lamports,
            slippage_bps=slippage_bps,
        )
    
    async def sell_token(
        self,
        token_mint: str,
        amount: int,
        slippage_bps: int = 100,
    ) -> SwapResult:
        """
        Sell a token for SOL.
        
        Args:
            token_mint: Token to sell
            amount: Token amount (in smallest units)
            slippage_bps: Slippage in basis points
            
        Returns:
            SwapResult
        """
        sol_mint = "So11111111111111111111111111111111111111112"
        
        logger.info(
            "jupiter_v6_sell",
            token=token_mint[:8] + "...",
            amount=amount,
        )
        
        return await self.swap(
            input_mint=token_mint,
            output_mint=sol_mint,
            amount=amount,
            slippage_bps=slippage_bps,
        )
