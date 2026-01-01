"""
Jupiter Ultra Swap API client for DEX trading.

Uses the Jupiter Ultra API for optimal routing, MEV protection,
and fast transaction landing.
"""

import base64
from dataclasses import dataclass
from typing import Any, Dict, Optional
import asyncio

import httpx
from solders.transaction import VersionedTransaction

from src.config.logging_config import get_logger
from src.config.settings import Settings

logger = get_logger(__name__)


# Jupiter API endpoints
JUPITER_ULTRA_API = "https://api.jup.ag/ultra/v1"


@dataclass
class QuoteResponse:
    """
    Response from Jupiter Ultra order endpoint.
    """
    # Quote details
    input_mint: str
    output_mint: str
    in_amount: int
    out_amount: int
    
    # Transaction data
    transaction: str  # Base64 encoded transaction
    request_id: str
    
    # Swap metadata
    swap_type: str
    slippage_bps: int
    price_impact_pct: Optional[float] = None
    
    # Fee info
    platform_fee_bps: Optional[int] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "QuoteResponse":
        """Create QuoteResponse from API response."""
        return cls(
            input_mint=data.get("inputMint", ""),
            output_mint=data.get("outputMint", ""),
            in_amount=int(data.get("inAmount", 0)),
            out_amount=int(data.get("outAmount", 0)),
            transaction=data.get("transaction", ""),
            request_id=data.get("requestId", ""),
            swap_type=data.get("swapType", ""),
            slippage_bps=int(data.get("slippageBps", 0)),
            price_impact_pct=data.get("priceImpactPct"),
            platform_fee_bps=data.get("platformFeeBps"),
        )
    
    @property
    def price(self) -> float:
        """Calculate the swap price."""
        if self.in_amount > 0:
            return self.out_amount / self.in_amount
        return 0.0
    
    def get_transaction_bytes(self) -> bytes:
        """Decode transaction to bytes."""
        return base64.b64decode(self.transaction)
    
    def get_versioned_transaction(self) -> VersionedTransaction:
        """Deserialize to VersionedTransaction."""
        tx_bytes = self.get_transaction_bytes()
        return VersionedTransaction.from_bytes(tx_bytes)


@dataclass
class ExecuteResponse:
    """Response from Jupiter execute endpoint."""
    signature: str
    status: str
    slot: Optional[int] = None
    
    # Input/output amounts after execution
    input_amount: Optional[int] = None
    output_amount: Optional[int] = None
    
    # Error info
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "ExecuteResponse":
        """Create ExecuteResponse from API response."""
        return cls(
            signature=data.get("signature", ""),
            status=data.get("status", "Unknown"),
            slot=data.get("slot"),
            input_amount=data.get("inputAmount"),
            output_amount=data.get("outputAmount"),
            error=data.get("error"),
            error_code=data.get("code"),
        )
    
    @property
    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.status == "Success"
    
    @property
    def solscan_url(self) -> str:
        """Get Solscan URL for the transaction."""
        return f"https://solscan.io/tx/{self.signature}"


class JupiterError(Exception):
    """Jupiter API error."""
    
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class JupiterClient:
    """
    Client for Jupiter Ultra Swap API.
    
    The Ultra API provides:
    - RPC-less architecture (Jupiter handles RPC)
    - MEV protection
    - Sub-second transaction landing
    - Real-time slippage estimation
    - Gasless support for some swaps
    
    Flow:
    1. Get Order (quote + transaction)
    2. Sign transaction locally
    3. Execute (send signed tx to Jupiter)
    4. Poll for confirmation
    """
    
    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize Jupiter client.
        
        Args:
            api_key: Jupiter API key from portal.jup.ag
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            # Only add API key header if provided (works without for basic usage)
            if self.api_key:
                headers["x-api-key"] = self.api_key
            
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=headers,
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Make an API request with retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            json: JSON body
            
        Returns:
            API response data
            
        Raises:
            JupiterError: If request fails
        """
        client = await self._get_client()
        url = f"{JUPITER_ULTRA_API}/{endpoint}"
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                if method == "GET":
                    response = await client.get(url, params=params)
                else:
                    response = await client.post(url, json=json)
                
                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "jupiter_rate_limited",
                        retry_after=retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                
                # Parse response
                data = response.json()
                
                # Check for API errors
                if response.status_code >= 400:
                    error_msg = data.get("error", response.text)
                    error_code = data.get("code")
                    raise JupiterError(error_msg, error_code)
                
                return data
                
            except httpx.TimeoutException as e:
                last_error = JupiterError(f"Request timeout: {e}")
                logger.warning(
                    "jupiter_request_timeout",
                    attempt=attempt + 1,
                    endpoint=endpoint,
                )
            except httpx.HTTPError as e:
                last_error = JupiterError(f"HTTP error: {e}")
                logger.warning(
                    "jupiter_http_error",
                    attempt=attempt + 1,
                    error=str(e),
                )
            except JupiterError:
                raise
            except Exception as e:
                last_error = JupiterError(f"Unexpected error: {e}")
                logger.error(
                    "jupiter_unexpected_error",
                    attempt=attempt + 1,
                    error=str(e),
                )
            
            # Exponential backoff
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        raise last_error or JupiterError("Request failed after retries")
    
    async def get_order(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        taker: str,
        slippage_bps: Optional[int] = None,
    ) -> QuoteResponse:
        """
        Get a swap order (quote + transaction).
        
        This is the first step of the Ultra swap flow. Returns a
        transaction that needs to be signed before execution.
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest units (lamports/raw)
            taker: Wallet address that will execute the swap
            slippage_bps: Optional slippage tolerance in basis points
            
        Returns:
            QuoteResponse with transaction to sign
            
        Raises:
            JupiterError: If quote fails
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "taker": taker,
        }
        
        if slippage_bps is not None:
            params["slippageBps"] = str(slippage_bps)
        
        logger.info(
            "jupiter_get_order",
            input_mint=input_mint[:8] + "...",
            output_mint=output_mint[:8] + "...",
            amount=amount,
        )
        
        data = await self._request("GET", "order", params=params)
        quote = QuoteResponse.from_api_response(data)
        
        logger.info(
            "jupiter_order_received",
            in_amount=quote.in_amount,
            out_amount=quote.out_amount,
            request_id=quote.request_id,
        )
        
        return quote
    
    async def execute_order(
        self,
        signed_transaction: str,
        request_id: str,
    ) -> ExecuteResponse:
        """
        Execute a signed swap transaction.
        
        This is the second step of the Ultra swap flow. Send the
        signed transaction to Jupiter for execution.
        
        Args:
            signed_transaction: Base64 encoded signed transaction
            request_id: Request ID from get_order response
            
        Returns:
            ExecuteResponse with signature and status
            
        Raises:
            JupiterError: If execution fails
        """
        logger.info(
            "jupiter_execute_order",
            request_id=request_id,
        )
        
        data = await self._request(
            "POST",
            "execute",
            json={
                "signedTransaction": signed_transaction,
                "requestId": request_id,
            },
        )
        
        result = ExecuteResponse.from_api_response(data)
        
        if result.is_success:
            logger.info(
                "jupiter_execution_success",
                signature=result.signature,
                status=result.status,
            )
        else:
            logger.error(
                "jupiter_execution_failed",
                signature=result.signature,
                status=result.status,
                error=result.error,
            )
        
        return result
    
    async def poll_transaction_status(
        self,
        signed_transaction: str,
        request_id: str,
        max_attempts: int = 10,
        poll_interval: float = 2.0,
    ) -> ExecuteResponse:
        """
        Poll for transaction status until confirmed or failed.
        
        Jupiter allows resubmitting the same signed transaction
        to poll for status without double execution risk.
        
        Args:
            signed_transaction: Base64 encoded signed transaction
            request_id: Request ID from get_order response
            max_attempts: Maximum polling attempts
            poll_interval: Seconds between polls
            
        Returns:
            Final ExecuteResponse
        """
        for attempt in range(max_attempts):
            result = await self.execute_order(signed_transaction, request_id)
            
            if result.status in {"Success", "Failed"}:
                return result
            
            logger.debug(
                "jupiter_poll_status",
                attempt=attempt + 1,
                status=result.status,
            )
            
            await asyncio.sleep(poll_interval)
        
        # Return last result if max attempts reached
        return result
    
    async def search_token(
        self,
        query: str,
    ) -> list[Dict[str, Any]]:
        """
        Search for tokens by symbol or address.
        
        Args:
            query: Search query (symbol or address)
            
        Returns:
            List of matching tokens
        """
        data = await self._request(
            "GET",
            "search",
            params={"query": query},
        )
        return data.get("tokens", [])
    
    async def get_holdings(
        self,
        wallet: str,
    ) -> Dict[str, Any]:
        """
        Get token holdings for a wallet.
        
        Args:
            wallet: Wallet address
            
        Returns:
            Holdings data
        """
        data = await self._request(
            "GET",
            "holdings",
            params={"wallet": wallet},
        )
        return data
    
    async def get_shield(
        self,
        mint: str,
    ) -> Dict[str, Any]:
        """
        Get token safety information (rug check).
        
        Args:
            mint: Token mint address
            
        Returns:
            Shield/safety data
        """
        data = await self._request(
            "GET",
            "shield",
            params={"mint": mint},
        )
        return data


async def create_jupiter_client(settings: Settings) -> JupiterClient:
    """
    Create a configured Jupiter client.
    
    Args:
        settings: Application settings
        
    Returns:
        Configured JupiterClient
    """
    return JupiterClient(
        api_key=settings.jupiter_api_key.get_secret_value(),
        timeout=settings.advanced.rpc_timeout,
        max_retries=settings.advanced.rpc_retries,
    )
