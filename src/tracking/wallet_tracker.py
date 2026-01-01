"""
Wallet tracker for monitoring Solana wallets in real-time.

Uses WebSocket subscriptions and periodic polling to detect
wallet activity including DEX swaps.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from collections import deque

from src.config.logging_config import get_logger
from src.config.settings import Settings, TrackedWallet
from src.blockchain.client import SolanaClient
from src.blockchain.transaction import TransactionParser, SwapInfo

logger = get_logger(__name__)


@dataclass
class WalletActivity:
    """Represents an activity detected on a tracked wallet."""
    wallet_address: str
    wallet_name: str
    signature: str
    activity_type: str  # 'swap', 'transfer', 'unknown'
    timestamp: datetime
    
    # Swap details (if applicable)
    swap_info: Optional[SwapInfo] = None
    
    # Raw transaction data for further processing
    raw_data: Optional[Dict] = None


@dataclass
class TrackedWalletState:
    """State of a tracked wallet."""
    address: str
    name: str
    
    # Last known signature
    last_signature: Optional[str] = None
    
    # Activity history
    recent_activities: deque = field(
        default_factory=lambda: deque(maxlen=100)
    )
    
    # Statistics
    total_swaps: int = 0
    total_buys: int = 0
    total_sells: int = 0
    
    # Tracking state
    is_active: bool = True
    last_checked: Optional[datetime] = None


class WalletTracker:
    """
    Monitors Solana wallets for trading activity.
    
    Uses a hybrid approach:
    - Periodic polling of transaction signatures
    - WebSocket subscriptions for real-time updates (when available)
    
    Detects:
    - DEX swap transactions
    - Token transfers
    - New token acquisitions
    """
    
    def __init__(
        self,
        settings: Settings,
        solana_client: SolanaClient,
        poll_interval: float = 5.0,
    ):
        """
        Initialize the wallet tracker.
        
        Args:
            settings: Application settings
            solana_client: Solana RPC client
            poll_interval: Seconds between polling cycles
        """
        self.settings = settings
        self.solana = solana_client
        self.poll_interval = poll_interval
        
        self.tx_parser = TransactionParser()
        
        # Tracked wallets
        self._wallets: Dict[str, TrackedWalletState] = {}
        
        # Callbacks
        self._on_swap: Optional[Callable[[WalletActivity], None]] = None
        self._on_activity: Optional[Callable[[WalletActivity], None]] = None
        
        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Processed signatures cache (prevent duplicates)
        self._processed_signatures: Set[str] = set()
        self._max_cache_size = 10000
        
        # Persistent storage path
        self._storage_path = Path("data/tracked_wallets.json")
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load saved wallets on init
        self._load_wallets()
    
    def add_wallet(
        self,
        address: str,
        name: str = "Unknown",
        save: bool = True,
    ) -> None:
        """
        Add a wallet to track.
        
        Args:
            address: Wallet public key
            name: Human-readable name
            save: Whether to persist to storage
        """
        if address not in self._wallets:
            self._wallets[address] = TrackedWalletState(
                address=address,
                name=name,
            )
            logger.info(
                "wallet_added",
                address=address,
                name=name,
            )
            
            # Save to persistent storage
            if save:
                self._save_wallets()
    
    def remove_wallet(self, address: str) -> None:
        """Remove a wallet from tracking."""
        if address in self._wallets:
            del self._wallets[address]
            logger.info("wallet_removed", address=address)
            
            # Save to persistent storage
            self._save_wallets()
    
    def on_swap(
        self,
        callback: Callable[[WalletActivity], None],
    ) -> None:
        """Register callback for swap detection."""
        self._on_swap = callback
    
    def on_activity(
        self,
        callback: Callable[[WalletActivity], None],
    ) -> None:
        """Register callback for any activity."""
        self._on_activity = callback
    
    async def start(self) -> None:
        """Start the wallet tracker."""
        if self._running:
            logger.warning("wallet_tracker_already_running")
            return
        
        self._running = True
        
        # Load wallets from settings (config file)
        for wallet in self.settings.wallet_tracking.monitored_wallets:
            self.add_wallet(wallet.address, wallet.name, save=False)
        
        for wallet in self.settings.copy_trading.tracked_wallets:
            self.add_wallet(wallet.address, wallet.name, save=False)
        
        # Note: Wallets from JSON are already loaded in __init__
        
        # Start polling task
        self._task = asyncio.create_task(self._poll_loop())
        
        logger.info(
            "wallet_tracker_started",
            wallet_count=len(self._wallets),
        )
    
    def _save_wallets(self) -> None:
        """Save tracked wallets to JSON file."""
        try:
            wallets_data = [
                {"address": w.address, "name": w.name}
                for w in self._wallets.values()
            ]
            
            with open(self._storage_path, 'w') as f:
                json.dump(wallets_data, f, indent=2)
            
            logger.debug(
                "wallets_saved",
                count=len(wallets_data),
                path=str(self._storage_path),
            )
        except Exception as e:
            logger.error("save_wallets_error", error=str(e))
    
    def _load_wallets(self) -> None:
        """Load tracked wallets from JSON file."""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, 'r') as f:
                    wallets_data = json.load(f)
                
                for wallet in wallets_data:
                    address = wallet.get("address")
                    name = wallet.get("name", "Unknown")
                    
                    if address and address not in self._wallets:
                        self._wallets[address] = TrackedWalletState(
                            address=address,
                            name=name,
                        )
                
                logger.info(
                    "wallets_loaded",
                    count=len(wallets_data),
                    path=str(self._storage_path),
                )
        except Exception as e:
            logger.error("load_wallets_error", error=str(e))
    
    async def stop(self) -> None:
        """Stop the wallet tracker."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("wallet_tracker_stopped")
    
    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_all_wallets()
            except Exception as e:
                logger.error("poll_loop_error", error=str(e))
            
            await asyncio.sleep(self.poll_interval)
    
    async def _poll_all_wallets(self) -> None:
        """Poll all tracked wallets for new activity."""
        tasks = [
            self._poll_wallet(wallet)
            for wallet in self._wallets.values()
            if wallet.is_active
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _poll_wallet(self, wallet: TrackedWalletState) -> None:
        """
        Poll a single wallet for new transactions.
        
        Args:
            wallet: Wallet state to poll
        """
        try:
            # Get recent signatures
            signatures = await self.solana.get_signatures_for_address(
                wallet.address,
                limit=10,
            )
            
            if not signatures:
                return
            
            # Process new signatures
            for sig_info in reversed(signatures):  # Oldest first
                signature = sig_info["signature"]
                
                # Skip already processed
                if signature in self._processed_signatures:
                    continue
                
                # Skip if before our last known signature
                if wallet.last_signature == signature:
                    continue
                
                # Skip failed transactions
                if sig_info.get("err"):
                    self._mark_processed(signature)
                    continue
                
                # Get full transaction
                tx_data = await self.solana.get_transaction(signature)
                
                if tx_data:
                    await self._process_transaction(wallet, signature, tx_data)
                
                self._mark_processed(signature)
            
            # Update last signature
            if signatures:
                wallet.last_signature = signatures[0]["signature"]
            
            wallet.last_checked = datetime.now()
            
        except Exception as e:
            logger.error(
                "wallet_poll_error",
                address=wallet.address,
                error=str(e),
            )
    
    def _mark_processed(self, signature: str) -> None:
        """Mark signature as processed."""
        self._processed_signatures.add(signature)
        
        # Limit cache size
        if len(self._processed_signatures) > self._max_cache_size:
            # Remove oldest (arbitrary since sets are unordered)
            self._processed_signatures.pop()
    
    async def _process_transaction(
        self,
        wallet: TrackedWalletState,
        signature: str,
        tx_data: Dict[str, Any],
    ) -> None:
        """
        Process a transaction and detect activity type.
        
        Args:
            wallet: Wallet that initiated the transaction
            signature: Transaction signature
            tx_data: Full transaction data
        """
        # Try to parse as swap
        swap_info = self.tx_parser.parse_swap(
            tx_data,
            wallet_address=wallet.address,
        )
        
        if swap_info:
            # This is a DEX swap
            activity = WalletActivity(
                wallet_address=wallet.address,
                wallet_name=wallet.name,
                signature=signature,
                activity_type="swap",
                timestamp=swap_info.block_time or datetime.now(),
                swap_info=swap_info,
                raw_data=tx_data,
            )
            
            # Update wallet stats
            wallet.total_swaps += 1
            if swap_info.direction.value == "buy":
                wallet.total_buys += 1
            elif swap_info.direction.value == "sell":
                wallet.total_sells += 1
            
            wallet.recent_activities.append(activity)
            
            logger.info(
                "swap_detected",
                wallet=wallet.name,
                direction=swap_info.direction.value,
                input_mint=swap_info.input_mint[:8] + "...",
                output_mint=swap_info.output_mint[:8] + "...",
                input_amount=swap_info.input_amount,
            )
            
            # Trigger callbacks
            if self._on_swap:
                await self._safe_callback(self._on_swap, activity)
            
            if self._on_activity:
                await self._safe_callback(self._on_activity, activity)
        
        else:
            # Unknown transaction type
            activity = WalletActivity(
                wallet_address=wallet.address,
                wallet_name=wallet.name,
                signature=signature,
                activity_type="unknown",
                timestamp=datetime.now(),
                raw_data=tx_data,
            )
            
            wallet.recent_activities.append(activity)
            
            if self._on_activity:
                await self._safe_callback(self._on_activity, activity)
    
    async def _safe_callback(
        self,
        callback: Callable,
        *args,
        **kwargs,
    ) -> None:
        """Execute callback safely."""
        try:
            result = callback(*args, **kwargs)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error("callback_error", error=str(e))
    
    def get_wallet_stats(self, address: str) -> Optional[Dict]:
        """Get statistics for a tracked wallet."""
        wallet = self._wallets.get(address)
        if not wallet:
            return None
        
        return {
            "address": wallet.address,
            "name": wallet.name,
            "total_swaps": wallet.total_swaps,
            "total_buys": wallet.total_buys,
            "total_sells": wallet.total_sells,
            "last_checked": wallet.last_checked,
            "recent_activities": len(wallet.recent_activities),
        }
    
    def get_all_wallets(self) -> List[Dict]:
        """Get info for all tracked wallets."""
        return [
            self.get_wallet_stats(address)
            for address in self._wallets
        ]
    
    def get_recent_activities(
        self,
        address: Optional[str] = None,
        limit: int = 20,
    ) -> List[WalletActivity]:
        """
        Get recent activities.
        
        Args:
            address: Optional wallet address filter
            limit: Maximum number to return
            
        Returns:
            List of recent activities
        """
        activities = []
        
        if address:
            wallet = self._wallets.get(address)
            if wallet:
                activities = list(wallet.recent_activities)
        else:
            for wallet in self._wallets.values():
                activities.extend(wallet.recent_activities)
            
            # Sort by timestamp
            activities.sort(key=lambda a: a.timestamp, reverse=True)
        
        return activities[:limit]
