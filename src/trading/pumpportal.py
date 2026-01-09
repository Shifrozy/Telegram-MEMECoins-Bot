"""
PumpPortal API client for pump.fun token trading.

Handles buying and selling tokens on pump.fun bonding curve.
"""

import base64
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from src.config.logging_config import get_logger

logger = get_logger(__name__)

PUMPPORTAL_API = "https://pumpportal.fun/api"


@dataclass
class PumpTradeResult:
    """Result from PumpPortal trade."""
    success: bool
    signature: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def solscan_url(self) -> str:
        if self.signature:
            return f"https://solscan.io/tx/{self.signature}"
        return ""


class PumpPortalClient:
    """
    Client for PumpPortal API to trade pump.fun tokens.
    
    Provides:
    - Buy tokens with SOL
    - Sell tokens for SOL
    - Works with pump.fun bonding curve and Raydium pools
    """
    
    def __init__(self, keypair: Keypair, timeout: int = 30):
        """
        Initialize PumpPortal client.
        
        Args:
            keypair: Wallet keypair for signing
            timeout: Request timeout
        """
        self.keypair = keypair
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
    
    async def buy(
        self,
        mint: str,
        amount_sol: float,
        slippage: int = 10,
        priority_fee: float = 0.0001,
    ) -> PumpTradeResult:
        """
        Buy pump.fun token with SOL.
        
        Args:
            mint: Token mint address
            amount_sol: Amount of SOL to spend
            slippage: Slippage percentage (default 10%)
            priority_fee: Priority fee in SOL
            
        Returns:
            PumpTradeResult
        """
        return await self._trade(
            action="buy",
            mint=mint,
            amount=amount_sol,
            denominated_in_sol=True,
            slippage=slippage,
            priority_fee=priority_fee,
        )
    
    async def sell(
        self,
        mint: str,
        amount_tokens: float,
        slippage: int = 10,
        priority_fee: float = 0.0001,
    ) -> PumpTradeResult:
        """
        Sell pump.fun token for SOL.
        
        Args:
            mint: Token mint address
            amount_tokens: Amount of tokens to sell
            slippage: Slippage percentage
            priority_fee: Priority fee in SOL
            
        Returns:
            PumpTradeResult
        """
        return await self._trade(
            action="sell",
            mint=mint,
            amount=amount_tokens,
            denominated_in_sol=False,
            slippage=slippage,
            priority_fee=priority_fee,
        )
    
    async def sell_percent(
        self,
        mint: str,
        percent: int = 100,
        slippage: int = 10,
        priority_fee: float = 0.0001,
    ) -> PumpTradeResult:
        """
        Sell a percentage of held tokens.
        
        Args:
            mint: Token mint address
            percent: Percentage to sell (1-100)
            slippage: Slippage percentage
            priority_fee: Priority fee in SOL
            
        Returns:
            PumpTradeResult
        """
        # Use special amount format for percentage
        return await self._trade(
            action="sell",
            mint=mint,
            amount=f"{percent}%",
            denominated_in_sol=False,
            slippage=slippage,
            priority_fee=priority_fee,
        )
    
    async def _trade(
        self,
        action: str,
        mint: str,
        amount: Any,
        denominated_in_sol: bool,
        slippage: int,
        priority_fee: float,
    ) -> PumpTradeResult:
        """Execute trade via PumpPortal."""
        client = await self._get_client()
        
        payload = {
            "publicKey": str(self.keypair.pubkey()),
            "action": action,
            "mint": mint,
            "amount": amount,
            "denominatedInSol": "true" if denominated_in_sol else "false",
            "slippage": slippage,
            "priorityFee": priority_fee,
            "pool": "auto",  # auto-detect pump or raydium
        }
        
        logger.info(
            "pumpportal_trade_request",
            action=action,
            mint=mint[:8] + "...",
            amount=amount,
        )
        
        try:
            # Step 1: Get transaction from PumpPortal
            resp = await client.post(
                f"{PUMPPORTAL_API}/trade-local",
                data=payload,
            )
            
            if resp.status_code != 200:
                error_text = resp.text
                logger.error("pumpportal_error", status=resp.status_code, error=error_text)
                return PumpTradeResult(success=False, error=error_text)
            
            # Step 2: Decode and sign transaction
            tx_bytes = resp.content
            transaction = VersionedTransaction.from_bytes(tx_bytes)
            
            # Sign the transaction
            signed_tx = VersionedTransaction(
                transaction.message,
                [self.keypair],
            )
            
            # Step 3: Send to Solana network via PumpPortal (or direct RPC)
            signed_bytes = bytes(signed_tx)
            
            send_resp = await client.post(
                "https://api.mainnet-beta.solana.com",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        base64.b64encode(signed_bytes).decode(),
                        {"encoding": "base64", "skipPreflight": True}
                    ]
                },
                headers={"Content-Type": "application/json"},
            )
            
            send_data = send_resp.json()
            
            if "result" in send_data:
                signature = send_data["result"]
                logger.info(
                    "pumpportal_trade_success",
                    signature=signature,
                )
                return PumpTradeResult(success=True, signature=signature)
            else:
                error = send_data.get("error", {}).get("message", "Unknown error")
                logger.error("pumpportal_send_error", error=error)
                return PumpTradeResult(success=False, error=error)
                
        except Exception as e:
            logger.error("pumpportal_exception", error=str(e))
            return PumpTradeResult(success=False, error=str(e))


def is_pump_token(mint: str) -> bool:
    """Check if token is likely a pump.fun token."""
    # Pump.fun tokens usually end with 'pump' in the address
    return mint.lower().endswith('pump')
