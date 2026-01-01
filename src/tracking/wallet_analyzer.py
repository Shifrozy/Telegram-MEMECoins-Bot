"""
Wallet Analyzer - Fetches and analyzes historical trading data for wallets.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import httpx

from src.config.logging_config import get_logger
from src.blockchain.client import SolanaClient

logger = get_logger(__name__)

# Known DEX program IDs
DEX_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter v4",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca v1",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
}

# SOL mint address
SOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass
class TradeRecord:
    """Individual trade record."""
    signature: str
    timestamp: datetime
    direction: str  # 'buy' or 'sell'
    token_mint: str
    token_symbol: str
    input_amount: float
    output_amount: float
    sol_value: float  # Value in SOL
    dex: str


@dataclass
class WalletStats:
    """Aggregated wallet statistics."""
    address: str
    total_trades: int = 0
    total_buys: int = 0
    total_sells: int = 0
    win_rate: float = 0.0
    total_pnl_sol: float = 0.0
    avg_trade_size_sol: float = 0.0
    largest_win_sol: float = 0.0
    largest_loss_sol: float = 0.0
    most_traded_token: str = ""
    first_trade_time: Optional[datetime] = None
    last_trade_time: Optional[datetime] = None
    recent_trades: List[TradeRecord] = field(default_factory=list)
    tokens_traded: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    @property
    def is_profitable(self) -> bool:
        """Check if wallet is overall profitable."""
        return self.total_pnl_sol > 0
    
    @property
    def grade(self) -> str:
        """Get wallet grade based on performance."""
        if self.win_rate >= 70 and self.total_pnl_sol > 10:
            return "🏆 S-Tier"
        elif self.win_rate >= 60 and self.total_pnl_sol > 5:
            return "🥇 A-Tier"
        elif self.win_rate >= 50 and self.total_pnl_sol > 0:
            return "🥈 B-Tier"
        elif self.win_rate >= 40:
            return "🥉 C-Tier"
        else:
            return "📉 D-Tier"


class WalletAnalyzer:
    """
    Analyzes wallet trading history to provide performance metrics.
    
    Uses Solana RPC and Helius API for fetching transaction history.
    """
    
    def __init__(
        self,
        solana: SolanaClient,
        helius_api_key: Optional[str] = None,
    ):
        """
        Initialize wallet analyzer.
        
        Args:
            solana: Solana client for RPC calls
            helius_api_key: Optional Helius API key for enhanced data
        """
        self.solana = solana
        self.helius_api_key = helius_api_key
        self._client: Optional[httpx.AsyncClient] = None
        
        # Cache for analyzed wallets
        self._cache: Dict[str, WalletStats] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_times: Dict[str, datetime] = {}
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def analyze_wallet(
        self,
        address: str,
        limit: int = 100,
        force_refresh: bool = False,
    ) -> WalletStats:
        """
        Analyze a wallet's trading history.
        
        Args:
            address: Wallet address to analyze
            limit: Maximum number of transactions to fetch
            force_refresh: Force refresh even if cached
            
        Returns:
            WalletStats with performance metrics
        """
        # Check cache
        if not force_refresh and address in self._cache:
            cache_time = self._cache_times.get(address)
            if cache_time and (datetime.now() - cache_time).seconds < self._cache_ttl:
                logger.debug("wallet_stats_cached", address=address[:8])
                return self._cache[address]
        
        logger.info("analyzing_wallet", address=address[:8], limit=limit)
        
        try:
            # Fetch transaction signatures
            signatures = await self._fetch_signatures(address, limit)
            
            if not signatures:
                return WalletStats(address=address)
            
            # Fetch and parse transactions
            trades = await self._parse_transactions(address, signatures)
            
            # Calculate statistics
            stats = self._calculate_stats(address, trades)
            
            # Cache results
            self._cache[address] = stats
            self._cache_times[address] = datetime.now()
            
            logger.info(
                "wallet_analyzed",
                address=address[:8],
                trades=stats.total_trades,
                win_rate=f"{stats.win_rate:.1f}%",
            )
            
            return stats
            
        except Exception as e:
            logger.error("wallet_analysis_error", address=address[:8], error=str(e))
            return WalletStats(address=address)
    
    async def _fetch_signatures(
        self,
        address: str,
        limit: int = 100,
    ) -> List[str]:
        """Fetch recent transaction signatures for a wallet."""
        try:
            # Use Solana RPC getSignaturesForAddress
            client = await self.solana._ensure_connected()
            
            from solders.pubkey import Pubkey
            
            result = await client.get_signatures_for_address(
                Pubkey.from_string(address),
                limit=limit,
            )
            
            signatures = [str(sig.signature) for sig in result.value]
            
            logger.debug(
                "fetched_signatures",
                address=address[:8],
                count=len(signatures),
            )
            
            return signatures
            
        except Exception as e:
            logger.error("fetch_signatures_error", error=str(e))
            return []
    
    async def _parse_transactions(
        self,
        wallet_address: str,
        signatures: List[str],
    ) -> List[TradeRecord]:
        """Parse transactions to extract trade records."""
        trades = []
        
        # Process in batches to avoid rate limits
        batch_size = 10
        
        for i in range(0, len(signatures), batch_size):
            batch = signatures[i:i + batch_size]
            
            # Fetch transaction details
            for sig in batch:
                try:
                    trade = await self._parse_single_transaction(wallet_address, sig)
                    if trade:
                        trades.append(trade)
                except Exception as e:
                    logger.debug("parse_tx_error", signature=sig[:16], error=str(e))
            
            # Small delay between batches
            if i + batch_size < len(signatures):
                await asyncio.sleep(0.2)
        
        return trades
    
    async def _parse_single_transaction(
        self,
        wallet_address: str,
        signature: str,
    ) -> Optional[TradeRecord]:
        """Parse a single transaction for trade info."""
        try:
            client = await self.solana._ensure_connected()
            
            from solders.signature import Signature
            
            # Fetch transaction with parsed accounts
            result = await client.get_transaction(
                Signature.from_string(signature),
                encoding="jsonParsed",
                max_supported_transaction_version=0,
            )
            
            if not result.value:
                return None
            
            tx = result.value
            
            # Check if it's a DEX transaction
            if not self._is_dex_transaction(tx):
                return None
            
            # Extract trade details from token balance changes
            trade = self._extract_trade_from_balances(wallet_address, tx, signature)
            
            return trade
            
        except Exception as e:
            logger.debug("parse_tx_error", signature=signature[:16], error=str(e))
            return None
    
    def _is_dex_transaction(self, tx) -> bool:
        """Check if transaction involves a DEX."""
        try:
            if not tx.transaction:
                return False
            
            # Get account keys from transaction
            message = tx.transaction.transaction.message
            
            account_keys = []
            if hasattr(message, 'account_keys'):
                account_keys = [str(k) for k in message.account_keys]
            elif hasattr(message, 'static_account_keys'):
                account_keys = [str(k) for k in message.static_account_keys]
            
            # Check if any DEX program is in the accounts
            for key in account_keys:
                if key in DEX_PROGRAMS:
                    return True
            
            return False
            
        except Exception:
            return False
    
    def _extract_trade_from_balances(
        self,
        wallet_address: str,
        tx,
        signature: str,
    ) -> Optional[TradeRecord]:
        """Extract trade details from token balance changes."""
        try:
            meta = tx.transaction.meta
            if not meta:
                return None
            
            # Get pre and post token balances
            pre_balances = meta.pre_token_balances or []
            post_balances = meta.post_token_balances or []
            
            # Find balance changes for this wallet
            sol_change = 0
            token_changes = {}
            
            # Calculate SOL change
            if hasattr(meta, 'pre_balances') and hasattr(meta, 'post_balances'):
                # Find wallet index in accounts
                message = tx.transaction.transaction.message
                account_keys = []
                if hasattr(message, 'account_keys'):
                    account_keys = [str(k) for k in message.account_keys]
                elif hasattr(message, 'static_account_keys'):
                    account_keys = [str(k) for k in message.static_account_keys]
                
                try:
                    wallet_idx = account_keys.index(wallet_address)
                    pre_sol = meta.pre_balances[wallet_idx] / 1e9
                    post_sol = meta.post_balances[wallet_idx] / 1e9
                    sol_change = post_sol - pre_sol
                except (ValueError, IndexError):
                    pass
            
            # Calculate token changes
            pre_amounts = {}
            for bal in pre_balances:
                if bal.owner == wallet_address:
                    mint = str(bal.mint)
                    amount = float(bal.ui_token_amount.ui_amount or 0)
                    pre_amounts[mint] = amount
            
            for bal in post_balances:
                if bal.owner == wallet_address:
                    mint = str(bal.mint)
                    post_amount = float(bal.ui_token_amount.ui_amount or 0)
                    pre_amount = pre_amounts.get(mint, 0)
                    change = post_amount - pre_amount
                    if abs(change) > 0.0001:
                        token_changes[mint] = change
            
            # Determine trade direction and create record
            if not token_changes:
                return None
            
            # Find the main token (not SOL)
            main_token = None
            main_change = 0
            for mint, change in token_changes.items():
                if mint != SOL_MINT:
                    if main_token is None or abs(change) > abs(main_change):
                        main_token = mint
                        main_change = change
            
            if not main_token:
                return None
            
            # Determine direction
            if main_change > 0:
                direction = "buy"
                input_amount = abs(sol_change) if sol_change < 0 else 0
                output_amount = main_change
            else:
                direction = "sell"
                input_amount = abs(main_change)
                output_amount = abs(sol_change) if sol_change > 0 else 0
            
            # Get timestamp
            timestamp = datetime.now()
            if tx.block_time:
                timestamp = datetime.fromtimestamp(tx.block_time)
            
            # Determine DEX used
            dex = "Unknown"
            message = tx.transaction.transaction.message
            account_keys = []
            if hasattr(message, 'account_keys'):
                account_keys = [str(k) for k in message.account_keys]
            elif hasattr(message, 'static_account_keys'):
                account_keys = [str(k) for k in message.static_account_keys]
            
            for key in account_keys:
                if key in DEX_PROGRAMS:
                    dex = DEX_PROGRAMS[key]
                    break
            
            return TradeRecord(
                signature=signature,
                timestamp=timestamp,
                direction=direction,
                token_mint=main_token,
                token_symbol=main_token[:8],  # Shortened for now
                input_amount=input_amount,
                output_amount=output_amount,
                sol_value=abs(sol_change) if sol_change else 0,
                dex=dex,
            )
            
        except Exception as e:
            logger.debug("extract_trade_error", error=str(e))
            return None
    
    def _calculate_stats(
        self,
        address: str,
        trades: List[TradeRecord],
    ) -> WalletStats:
        """Calculate wallet statistics from trade records."""
        stats = WalletStats(address=address)
        
        if not trades:
            return stats
        
        stats.total_trades = len(trades)
        stats.recent_trades = trades[:20]  # Keep last 20 trades
        
        # Track tokens
        tokens: Dict[str, Dict[str, Any]] = {}
        winning_trades = 0
        total_sol_spent = 0
        total_sol_received = 0
        
        for trade in trades:
            # Count buys and sells
            if trade.direction == "buy":
                stats.total_buys += 1
                total_sol_spent += trade.sol_value
            else:
                stats.total_sells += 1
                total_sol_received += trade.sol_value
            
            # Track per token
            if trade.token_mint not in tokens:
                tokens[trade.token_mint] = {
                    "symbol": trade.token_symbol,
                    "buys": 0,
                    "sells": 0,
                    "spent": 0,
                    "received": 0,
                    "pnl": 0,
                }
            
            token = tokens[trade.token_mint]
            if trade.direction == "buy":
                token["buys"] += 1
                token["spent"] += trade.sol_value
            else:
                token["sells"] += 1
                token["received"] += trade.sol_value
            
            token["pnl"] = token["received"] - token["spent"]
            
            if token["pnl"] > 0:
                winning_trades += 1
        
        # Calculate aggregate stats
        stats.tokens_traded = tokens
        stats.total_pnl_sol = total_sol_received - total_sol_spent
        
        if stats.total_trades > 0:
            stats.avg_trade_size_sol = (total_sol_spent + total_sol_received) / stats.total_trades / 2
        
        # Calculate win rate based on token PnLs
        if tokens:
            profitable_tokens = sum(1 for t in tokens.values() if t["pnl"] > 0)
            stats.win_rate = (profitable_tokens / len(tokens)) * 100
        
        # Find largest win/loss
        pnls = [t["pnl"] for t in tokens.values()]
        if pnls:
            stats.largest_win_sol = max(pnls) if max(pnls) > 0 else 0
            stats.largest_loss_sol = min(pnls) if min(pnls) < 0 else 0
        
        # Find most traded token
        if tokens:
            most_traded = max(tokens.items(), key=lambda x: x[1]["buys"] + x[1]["sells"])
            stats.most_traded_token = most_traded[1]["symbol"]
        
        # Time range
        if trades:
            sorted_trades = sorted(trades, key=lambda t: t.timestamp)
            stats.first_trade_time = sorted_trades[0].timestamp
            stats.last_trade_time = sorted_trades[-1].timestamp
        
        return stats
    
    def format_stats_message(self, stats: WalletStats) -> str:
        """Format wallet stats as a Telegram message."""
        if stats.total_trades == 0:
            return f"""
📊 **Wallet Analysis**

`{stats.address[:8]}...{stats.address[-4:]}`

❌ No trading history found.

This wallet may be:
• New or inactive
• Primarily holding, not trading
• Using unlisted DEXs
"""
        
        pnl_emoji = "🟢" if stats.is_profitable else "🔴"
        
        # Format time range
        time_range = "Unknown"
        if stats.first_trade_time and stats.last_trade_time:
            days = (stats.last_trade_time - stats.first_trade_time).days
            if days == 0:
                time_range = "Today"
            elif days == 1:
                time_range = "1 day"
            else:
                time_range = f"{days} days"
        
        message = f"""
📊 **Wallet Analysis**

`{stats.address[:8]}...{stats.address[-4:]}`

**Grade:** {stats.grade}

━━━━━━━━━━━━━━━━━━━━
**Performance:**
• Total Trades: {stats.total_trades}
• Win Rate: {stats.win_rate:.1f}%
• {pnl_emoji} Total PnL: {stats.total_pnl_sol:+.4f} SOL

**Trading Activity:**
• Buys: 🟢 {stats.total_buys}
• Sells: 🔴 {stats.total_sells}
• Avg Size: {stats.avg_trade_size_sol:.3f} SOL
• Period: {time_range}

**Best/Worst:**
• Largest Win: +{stats.largest_win_sol:.4f} SOL
• Largest Loss: {stats.largest_loss_sol:.4f} SOL

━━━━━━━━━━━━━━━━━━━━
🔗 [View on Solscan](https://solscan.io/account/{stats.address})
"""
        
        return message.strip()
