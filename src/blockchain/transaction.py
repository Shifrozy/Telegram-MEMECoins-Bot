"""
Transaction parsing utilities for detecting DEX swaps and token transfers.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from src.config.logging_config import get_logger

logger = get_logger(__name__)


class SwapDirection(Enum):
    """Swap direction."""
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


@dataclass
class TokenTransfer:
    """Represents a token transfer in a transaction."""
    mint: str
    from_address: str
    to_address: str
    amount: float
    decimals: int


@dataclass
class SwapInfo:
    """
    Parsed swap information from a transaction.
    
    Contains all relevant details about a DEX swap including
    tokens involved, amounts, and transaction metadata.
    """
    signature: str
    slot: int
    block_time: Optional[datetime]
    
    # Swap details
    input_mint: str
    output_mint: str
    input_amount: float
    output_amount: float
    
    # Direction relative to SOL
    direction: SwapDirection
    
    # Wallet that performed the swap
    signer: str
    
    # DEX program that executed the swap
    program: str
    
    # Fee paid
    fee_lamports: int
    
    # Success status
    success: bool
    error: Optional[str] = None
    
    @property
    def input_amount_human(self) -> str:
        """Human-readable input amount."""
        return f"{self.input_amount:.6f}"
    
    @property
    def output_amount_human(self) -> str:
        """Human-readable output amount."""
        return f"{self.output_amount:.6f}"
    
    @property
    def price(self) -> float:
        """Calculate the swap price (output per input)."""
        if self.input_amount > 0:
            return self.output_amount / self.input_amount
        return 0.0


# Known DEX program IDs for swap detection
DEX_PROGRAMS = {
    # Jupiter Aggregator
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter v4",
    
    # Raydium
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM",
    
    # Orca
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca v2",
    
    # Meteora
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora Pools",
    
    # Pump.fun
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
}

# Well-known token mints
KNOWN_TOKENS = {
    "So11111111111111111111111111111111111111112": {"symbol": "SOL", "decimals": 9},
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"symbol": "USDC", "decimals": 6},
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": {"symbol": "USDT", "decimals": 6},
}

# Wrapped SOL mint
WSOL_MINT = "So11111111111111111111111111111111111111112"


class TransactionParser:
    """
    Parses Solana transactions to extract swap information.
    
    Uses token balance changes (preTokenBalances vs postTokenBalances)
    as the primary method for detecting swaps, which works across
    all DEX protocols.
    """
    
    def __init__(self):
        """Initialize the transaction parser."""
        self._token_cache: Dict[str, Dict[str, Any]] = {}
    
    def parse_swap(
        self,
        tx_data: Dict[str, Any],
        wallet_address: Optional[str] = None,
    ) -> Optional[SwapInfo]:
        """
        Parse a transaction to extract swap information.
        
        Args:
            tx_data: Transaction data from RPC
            wallet_address: Optional wallet to focus on
            
        Returns:
            SwapInfo if a swap was detected, None otherwise
        """
        if not tx_data:
            return None
        
        try:
            # Extract basic transaction info
            meta = tx_data.get("meta", {})
            transaction = tx_data.get("transaction", {})
            
            # Check for transaction error
            if meta.get("err"):
                return None
            
            # Get signers
            message = transaction.get("message", {})
            account_keys = message.get("accountKeys", [])
            
            if not account_keys:
                return None
            
            # First signer is the fee payer / initiator
            signer = self._get_account_key(account_keys[0])
            
            # If wallet specified, only process if it's the signer
            if wallet_address and signer != wallet_address:
                return None
            
            # Detect DEX program used
            dex_program = self._detect_dex_program(message)
            if not dex_program:
                return None
            
            # Parse token balance changes
            balance_changes = self._parse_balance_changes(
                meta.get("preTokenBalances", []),
                meta.get("postTokenBalances", []),
                signer,
            )
            
            if len(balance_changes) < 2:
                return None  # Need at least 2 token changes for a swap
            
            # Identify input and output tokens
            input_token, output_token = self._identify_swap_tokens(balance_changes)
            
            if not input_token or not output_token:
                return None
            
            # Determine swap direction relative to SOL
            direction = self._determine_direction(input_token[0], output_token[0])
            
            # Build SwapInfo
            return SwapInfo(
                signature=str(tx_data.get("transaction", {}).get("signatures", [""])[0]),
                slot=tx_data.get("slot", 0),
                block_time=self._parse_block_time(tx_data.get("blockTime")),
                input_mint=input_token[0],
                output_mint=output_token[0],
                input_amount=abs(input_token[1]),
                output_amount=abs(output_token[1]),
                direction=direction,
                signer=signer,
                program=dex_program,
                fee_lamports=meta.get("fee", 0),
                success=True,
            )
            
        except Exception as e:
            logger.error("transaction_parse_error", error=str(e))
            return None
    
    def _get_account_key(self, key_data: Any) -> str:
        """Extract account key string from various formats."""
        if isinstance(key_data, str):
            return key_data
        if isinstance(key_data, dict):
            return key_data.get("pubkey", "")
        return str(key_data)
    
    def _detect_dex_program(self, message: Dict[str, Any]) -> Optional[str]:
        """
        Detect which DEX program was used in the transaction.
        
        Args:
            message: Transaction message
            
        Returns:
            DEX name or None if no DEX detected
        """
        # Check account keys for known DEX programs
        account_keys = message.get("accountKeys", [])
        
        for key_data in account_keys:
            key = self._get_account_key(key_data)
            if key in DEX_PROGRAMS:
                return DEX_PROGRAMS[key]
        
        # Check instructions for DEX program calls
        instructions = message.get("instructions", [])
        for ix in instructions:
            program_id = ix.get("programId", "")
            if program_id in DEX_PROGRAMS:
                return DEX_PROGRAMS[program_id]
        
        return None
    
    def _parse_balance_changes(
        self,
        pre_balances: List[Dict],
        post_balances: List[Dict],
        signer: str,
    ) -> Dict[str, float]:
        """
        Calculate token balance changes from pre/post balances.
        
        Args:
            pre_balances: Pre-transaction token balances
            post_balances: Post-transaction token balances
            signer: Signer address to focus on
            
        Returns:
            Dict of mint -> balance change
        """
        changes: Dict[str, float] = {}
        
        # Build pre-balance map
        pre_map: Dict[int, Dict] = {}
        for bal in pre_balances:
            account_index = bal.get("accountIndex")
            if account_index is not None:
                pre_map[account_index] = bal
        
        # Calculate changes from post balances
        for post_bal in post_balances:
            account_index = post_bal.get("accountIndex")
            owner = post_bal.get("owner", "")
            
            # Only consider balances for the signer
            if owner != signer:
                continue
            
            mint = post_bal.get("mint", "")
            post_amount = float(post_bal.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
            
            # Get pre-balance
            pre_bal = pre_map.get(account_index, {})
            pre_amount = float(pre_bal.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
            
            change = post_amount - pre_amount
            
            if change != 0:
                if mint in changes:
                    changes[mint] += change
                else:
                    changes[mint] = change
        
        # Also check for new accounts in post that weren't in pre
        post_indices = {b.get("accountIndex") for b in post_balances}
        for pre_bal in pre_balances:
            account_index = pre_bal.get("accountIndex")
            owner = pre_bal.get("owner", "")
            
            if owner != signer:
                continue
            
            if account_index not in post_indices:
                # Account closed - full balance was spent
                mint = pre_bal.get("mint", "")
                pre_amount = float(pre_bal.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                
                if pre_amount > 0:
                    if mint in changes:
                        changes[mint] -= pre_amount
                    else:
                        changes[mint] = -pre_amount
        
        return changes
    
    def _identify_swap_tokens(
        self,
        balance_changes: Dict[str, float],
    ) -> Tuple[Optional[Tuple[str, float]], Optional[Tuple[str, float]]]:
        """
        Identify input and output tokens from balance changes.
        
        Input: Token with negative balance change (spent)
        Output: Token with positive balance change (received)
        
        Args:
            balance_changes: Dict of mint -> balance change
            
        Returns:
            Tuple of (input_token, output_token) as (mint, amount) tuples
        """
        input_token = None
        output_token = None
        
        for mint, change in balance_changes.items():
            if change < 0:
                # This is the input token (spent)
                if input_token is None or abs(change) > abs(input_token[1]):
                    input_token = (mint, change)
            elif change > 0:
                # This is the output token (received)
                if output_token is None or change > output_token[1]:
                    output_token = (mint, change)
        
        return input_token, output_token
    
    def _determine_direction(
        self,
        input_mint: str,
        output_mint: str,
    ) -> SwapDirection:
        """
        Determine if the swap is a buy or sell relative to SOL.
        
        Buy: Spending SOL/stables to get tokens
        Sell: Spending tokens to get SOL/stables
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            
        Returns:
            SwapDirection
        """
        # Stablecoins and SOL are considered "base" assets
        base_mints = {
            WSOL_MINT,
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
        }
        
        input_is_base = input_mint in base_mints
        output_is_base = output_mint in base_mints
        
        if input_is_base and not output_is_base:
            return SwapDirection.BUY
        elif not input_is_base and output_is_base:
            return SwapDirection.SELL
        else:
            return SwapDirection.UNKNOWN
    
    def _parse_block_time(self, block_time: Optional[int]) -> Optional[datetime]:
        """Convert Unix timestamp to datetime."""
        if block_time:
            return datetime.fromtimestamp(block_time)
        return None
    
    def get_token_symbol(self, mint: str) -> str:
        """Get human-readable symbol for a token mint."""
        if mint in KNOWN_TOKENS:
            return KNOWN_TOKENS[mint]["symbol"]
        return f"{mint[:4]}...{mint[-4:]}"
    
    def is_dex_transaction(self, tx_data: Dict[str, Any]) -> bool:
        """
        Quick check if a transaction involves a DEX.
        
        Args:
            tx_data: Transaction data from RPC
            
        Returns:
            True if DEX transaction, False otherwise
        """
        message = tx_data.get("transaction", {}).get("message", {})
        return self._detect_dex_program(message) is not None


def format_swap_message(swap: SwapInfo, parser: TransactionParser) -> str:
    """
    Format a swap into a human-readable message.
    
    Args:
        swap: SwapInfo to format
        parser: TransactionParser for token symbols
        
    Returns:
        Formatted message string
    """
    direction_emoji = "🟢" if swap.direction == SwapDirection.BUY else "🔴"
    direction_text = swap.direction.value.upper()
    
    input_symbol = parser.get_token_symbol(swap.input_mint)
    output_symbol = parser.get_token_symbol(swap.output_mint)
    
    message = f"""
{direction_emoji} **{direction_text}** on {swap.program}

📤 Spent: {swap.input_amount:.6f} {input_symbol}
📥 Got: {swap.output_amount:.6f} {output_symbol}

💰 Price: {swap.price:.8f} {output_symbol}/{input_symbol}
👛 Wallet: `{swap.signer[:8]}...{swap.signer[-4:]}`

🔗 [View Transaction](https://solscan.io/tx/{swap.signature})
"""
    return message.strip()
