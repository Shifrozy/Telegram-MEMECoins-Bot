"""
Solana RPC client wrapper with retry logic and error handling.
Provides both HTTP and WebSocket connectivity.
"""

import asyncio
from typing import Any, Dict, List, Optional, Callable
from contextlib import asynccontextmanager

from solana.rpc.async_api import AsyncClient
from solana.rpc.websocket_api import connect
from solana.rpc.commitment import Commitment
from solders.pubkey import Pubkey
from solders.signature import Signature

from src.config.logging_config import get_logger

logger = get_logger(__name__)


class SolanaClient:
    """
    Wrapper around Solana RPC client with enhanced error handling,
    retry logic, and WebSocket support.
    """
    
    def __init__(
        self,
        rpc_url: str,
        ws_url: str,
        commitment: str = "confirmed",
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize the Solana client.
        
        Args:
            rpc_url: HTTP RPC endpoint
            ws_url: WebSocket endpoint
            commitment: Transaction commitment level
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts for failed requests
        """
        self.rpc_url = rpc_url
        self.ws_url = ws_url
        self.commitment = Commitment(commitment)
        self.timeout = timeout
        self.max_retries = max_retries
        
        self._client: Optional[AsyncClient] = None
        self._ws_connection = None
        self._ws_subscriptions: Dict[int, Callable] = {}
    
    async def connect(self) -> None:
        """Establish connection to the Solana RPC."""
        if self._client is None:
            self._client = AsyncClient(
                self.rpc_url,
                commitment=self.commitment,
                timeout=self.timeout,
            )
            logger.info("solana_client_connected", rpc_url=self.rpc_url)
    
    async def disconnect(self) -> None:
        """Close all connections."""
        if self._client:
            await self._client.close()
            self._client = None
        
        if self._ws_connection:
            await self._ws_connection.close()
            self._ws_connection = None
        
        logger.info("solana_client_disconnected")
    
    async def _ensure_connected(self) -> AsyncClient:
        """Ensure client is connected and return it."""
        if self._client is None:
            await self.connect()
        return self._client
    
    async def _retry_request(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a request with retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result from the function
            
        Raises:
            Exception: If all retries fail
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    "rpc_request_failed",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    error=str(e),
                )
                
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
        
        raise last_error
    
    # ===========================================
    # ACCOUNT METHODS
    # ===========================================
    
    async def get_balance(self, pubkey: str) -> float:
        """
        Get SOL balance for an account.
        
        Args:
            pubkey: Public key of the account
            
        Returns:
            Balance in SOL
        """
        client = await self._ensure_connected()
        
        async def _get_balance():
            result = await client.get_balance(Pubkey.from_string(pubkey))
            return result.value / 1_000_000_000  # Convert lamports to SOL
        
        return await self._retry_request(_get_balance)
    
    async def get_token_accounts(
        self,
        owner: str,
        mint: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get token accounts for a wallet.
        
        Args:
            owner: Wallet public key
            mint: Optional token mint to filter by
            
        Returns:
            List of token account info
        """
        client = await self._ensure_connected()
        owner_pubkey = Pubkey.from_string(owner)
        
        async def _get_token_accounts():
            if mint:
                result = await client.get_token_accounts_by_owner(
                    owner_pubkey,
                    {"mint": Pubkey.from_string(mint)},
                )
            else:
                result = await client.get_token_accounts_by_owner(
                    owner_pubkey,
                    {"programId": Pubkey.from_string(
                        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
                    )},
                )
            
            accounts = []
            for account in result.value:
                accounts.append({
                    "pubkey": str(account.pubkey),
                    "data": account.account.data,
                })
            return accounts
        
        return await self._retry_request(_get_token_accounts)
    
    async def get_account_info(self, pubkey: str) -> Optional[Dict[str, Any]]:
        """
        Get account information.
        
        Args:
            pubkey: Account public key
            
        Returns:
            Account info or None if not found
        """
        client = await self._ensure_connected()
        
        async def _get_account_info():
            result = await client.get_account_info(
                Pubkey.from_string(pubkey),
                encoding="jsonParsed",
            )
            if result.value is None:
                return None
            return {
                "lamports": result.value.lamports,
                "owner": str(result.value.owner),
                "data": result.value.data,
            }
        
        return await self._retry_request(_get_account_info)
    
    # ===========================================
    # TRANSACTION METHODS
    # ===========================================
    
    async def get_transaction(
        self,
        signature: str,
        max_supported_version: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Get transaction details by signature.
        
        Args:
            signature: Transaction signature
            max_supported_version: Max transaction version to support
            
        Returns:
            Transaction details or None
        """
        client = await self._ensure_connected()
        
        async def _get_transaction():
            result = await client.get_transaction(
                Signature.from_string(signature),
                encoding="jsonParsed",
                max_supported_transaction_version=max_supported_version,
            )
            return result.value
        
        return await self._retry_request(_get_transaction)
    
    async def get_signatures_for_address(
        self,
        address: str,
        limit: int = 10,
        before: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent transaction signatures for an address.
        
        Args:
            address: Account address
            limit: Maximum number of signatures to return
            before: Get signatures before this signature
            
        Returns:
            List of signature info
        """
        client = await self._ensure_connected()
        pubkey = Pubkey.from_string(address)
        
        async def _get_signatures():
            before_sig = Signature.from_string(before) if before else None
            result = await client.get_signatures_for_address(
                pubkey,
                limit=limit,
                before=before_sig,
            )
            return [
                {
                    "signature": str(sig.signature),
                    "slot": sig.slot,
                    "err": sig.err,
                    "block_time": sig.block_time,
                }
                for sig in result.value
            ]
        
        return await self._retry_request(_get_signatures)
    
    async def send_transaction(
        self,
        serialized_tx: bytes,
        skip_preflight: bool = False,
    ) -> str:
        """
        Send a signed transaction to the network.
        
        Args:
            serialized_tx: Serialized transaction bytes
            skip_preflight: Skip preflight checks
            
        Returns:
            Transaction signature
        """
        client = await self._ensure_connected()
        
        async def _send_transaction():
            result = await client.send_raw_transaction(
                serialized_tx,
                opts={
                    "skip_preflight": skip_preflight,
                    "preflight_commitment": self.commitment,
                },
            )
            return str(result.value)
        
        signature = await self._retry_request(_send_transaction)
        logger.info("transaction_sent", signature=signature)
        return signature
    
    async def confirm_transaction(
        self,
        signature: str,
        timeout: Optional[int] = None,
    ) -> bool:
        """
        Wait for transaction confirmation.
        
        Args:
            signature: Transaction signature
            timeout: Confirmation timeout in seconds
            
        Returns:
            True if confirmed, False if failed/timed out
        """
        client = await self._ensure_connected()
        timeout = timeout or self.timeout
        
        try:
            result = await asyncio.wait_for(
                client.confirm_transaction(
                    Signature.from_string(signature),
                    commitment=self.commitment,
                ),
                timeout=timeout,
            )
            
            if result.value[0].err:
                logger.error(
                    "transaction_failed",
                    signature=signature,
                    error=str(result.value[0].err),
                )
                return False
            
            logger.info("transaction_confirmed", signature=signature)
            return True
            
        except asyncio.TimeoutError:
            logger.error("transaction_timeout", signature=signature)
            return False
        except Exception as e:
            logger.error("transaction_error", signature=signature, error=str(e))
            return False
    
    # ===========================================
    # WEBSOCKET METHODS
    # ===========================================
    
    @asynccontextmanager
    async def subscribe_account(
        self,
        pubkey: str,
        callback: Callable[[Dict[str, Any]], None],
    ):
        """
        Subscribe to account changes via WebSocket.
        
        Args:
            pubkey: Account public key to monitor
            callback: Function to call on account changes
            
        Yields:
            Subscription ID
        """
        async with connect(self.ws_url) as ws:
            # Subscribe to account
            await ws.account_subscribe(
                Pubkey.from_string(pubkey),
                commitment=self.commitment,
                encoding="jsonParsed",
            )
            
            subscription_id = (await ws.recv())[0].result
            logger.info(
                "websocket_subscribed",
                pubkey=pubkey,
                subscription_id=subscription_id,
            )
            
            try:
                yield subscription_id
                
                # Process incoming messages
                async for msg in ws:
                    if msg[0].result:
                        await callback(msg[0].result)
                        
            finally:
                # Unsubscribe
                await ws.account_unsubscribe(subscription_id)
                logger.info(
                    "websocket_unsubscribed",
                    pubkey=pubkey,
                    subscription_id=subscription_id,
                )
    
    async def subscribe_logs(
        self,
        address: str,
        callback: Callable[[Dict[str, Any]], None],
    ):
        """
        Subscribe to transaction logs for an address.
        
        Args:
            address: Account address to monitor
            callback: Function to call on new logs
        """
        async with connect(self.ws_url) as ws:
            await ws.logs_subscribe(
                filter_={"mentions": [address]},
                commitment=self.commitment,
            )
            
            subscription_id = (await ws.recv())[0].result
            logger.info(
                "logs_subscribed",
                address=address,
                subscription_id=subscription_id,
            )
            
            try:
                async for msg in ws:
                    if msg[0].result:
                        await callback(msg[0].result)
            finally:
                await ws.logs_unsubscribe(subscription_id)
    
    # ===========================================
    # UTILITY METHODS
    # ===========================================
    
    async def get_latest_blockhash(self) -> str:
        """Get the latest blockhash."""
        client = await self._ensure_connected()
        
        async def _get_blockhash():
            result = await client.get_latest_blockhash()
            return str(result.value.blockhash)
        
        return await self._retry_request(_get_blockhash)
    
    async def get_slot(self) -> int:
        """Get the current slot."""
        client = await self._ensure_connected()
        
        async def _get_slot():
            result = await client.get_slot()
            return result.value
        
        return await self._retry_request(_get_slot)
    
    async def is_healthy(self) -> bool:
        """Check if the RPC is healthy."""
        try:
            await self.get_slot()
            return True
        except Exception:
            return False
