"""
Wallet management for the Solana Trading Bot.
Handles keypair loading, signing, and address derivation.
"""

from typing import Optional, Tuple
import base58

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0

from src.config.logging_config import get_logger

logger = get_logger(__name__)


class WalletManager:
    """
    Manages wallet operations including key loading, signing,
    and address utilities.
    """
    
    def __init__(self, private_key: str):
        """
        Initialize with a private key.
        
        Args:
            private_key: Base58 encoded private key or JSON array string
        """
        self._keypair = self._load_keypair(private_key)
        self._pubkey = self._keypair.pubkey()
        
        logger.info(
            "wallet_initialized",
            address=str(self._pubkey),
        )
    
    @staticmethod
    def _load_keypair(private_key: str) -> Keypair:
        """
        Load keypair from various formats.
        
        Supports:
        - Base58 encoded private key
        - JSON array of bytes
        
        Args:
            private_key: Private key in supported format
            
        Returns:
            Keypair instance
            
        Raises:
            ValueError: If key format is invalid
        """
        private_key = private_key.strip()
        
        # Try JSON array format [1,2,3,...] (64 bytes)
        if private_key.startswith("["):
            try:
                import json
                key_bytes = bytes(json.loads(private_key))
                return Keypair.from_bytes(key_bytes)
            except Exception as e:
                raise ValueError(f"Invalid JSON key format: {e}")
        
        # Try base58 format
        try:
            key_bytes = base58.b58decode(private_key)
            
            # Handle 64-byte key (full keypair)
            if len(key_bytes) == 64:
                return Keypair.from_bytes(key_bytes)
            
            # Handle 32-byte key (seed/secret only)
            elif len(key_bytes) == 32:
                return Keypair.from_seed(key_bytes)
            
            else:
                raise ValueError(f"Invalid key length: {len(key_bytes)} bytes")
                
        except Exception as e:
            raise ValueError(f"Invalid private key format: {e}")
    
    @property
    def pubkey(self) -> Pubkey:
        """Get the wallet public key."""
        return self._pubkey
    
    @property
    def address(self) -> str:
        """Get the wallet address as string."""
        return str(self._pubkey)
    
    @property
    def keypair(self) -> Keypair:
        """Get the keypair (use with caution)."""
        return self._keypair
    
    def sign_transaction(self, transaction: VersionedTransaction) -> VersionedTransaction:
        """
        Sign a versioned transaction.
        
        Args:
            transaction: Transaction to sign
            
        Returns:
            Signed transaction
        """
        transaction.sign([self._keypair])
        return transaction
    
    def sign_message(self, message: bytes) -> bytes:
        """
        Sign an arbitrary message.
        
        Args:
            message: Message bytes to sign
            
        Returns:
            Signature bytes
        """
        return self._keypair.sign_message(message)
    
    @staticmethod
    def is_valid_address(address: str) -> bool:
        """
        Check if a string is a valid Solana address.
        
        Args:
            address: Address to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            Pubkey.from_string(address)
            return True
        except Exception:
            return False
    
    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """
        Generate a new keypair.
        
        Returns:
            Tuple of (public_key, private_key_base58)
        """
        keypair = Keypair()
        private_key_b58 = base58.b58encode(bytes(keypair)).decode()
        return str(keypair.pubkey()), private_key_b58


class TokenAccount:
    """Represents a Solana token account."""
    
    # SPL Token Program ID
    TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    
    # Token-2022 Program ID
    TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
    
    def __init__(
        self,
        address: str,
        mint: str,
        owner: str,
        amount: int,
        decimals: int,
    ):
        """
        Initialize token account.
        
        Args:
            address: Token account address
            mint: Token mint address
            owner: Owner wallet address
            amount: Raw token amount
            decimals: Token decimals
        """
        self.address = address
        self.mint = mint
        self.owner = owner
        self.amount = amount
        self.decimals = decimals
    
    @property
    def ui_amount(self) -> float:
        """Get human-readable token amount."""
        return self.amount / (10 ** self.decimals)
    
    @classmethod
    def from_account_data(cls, address: str, data: dict) -> "TokenAccount":
        """
        Create from parsed account data.
        
        Args:
            address: Account address
            data: Parsed account data from RPC
            
        Returns:
            TokenAccount instance
        """
        info = data["parsed"]["info"]
        return cls(
            address=address,
            mint=info["mint"],
            owner=info["owner"],
            amount=int(info["tokenAmount"]["amount"]),
            decimals=info["tokenAmount"]["decimals"],
        )
    
    def __repr__(self) -> str:
        return f"TokenAccount(mint={self.mint[:8]}..., amount={self.ui_amount})"


class WalletPortfolio:
    """Manages a wallet's token portfolio."""
    
    def __init__(self, owner: str):
        """
        Initialize portfolio.
        
        Args:
            owner: Wallet address
        """
        self.owner = owner
        self.sol_balance: float = 0.0
        self.token_accounts: dict[str, TokenAccount] = {}
    
    def update_sol_balance(self, balance: float) -> None:
        """Update SOL balance."""
        self.sol_balance = balance
    
    def add_token_account(self, account: TokenAccount) -> None:
        """Add or update a token account."""
        self.token_accounts[account.mint] = account
    
    def get_token_balance(self, mint: str) -> float:
        """Get balance for a specific token."""
        if mint in self.token_accounts:
            return self.token_accounts[mint].ui_amount
        return 0.0
    
    def total_value_sol(self, token_prices: dict[str, float]) -> float:
        """
        Calculate total portfolio value in SOL.
        
        Args:
            token_prices: Dict of mint -> SOL price
            
        Returns:
            Total value in SOL
        """
        total = self.sol_balance
        
        for mint, account in self.token_accounts.items():
            if mint in token_prices:
                total += account.ui_amount * token_prices[mint]
        
        return total
    
    def __repr__(self) -> str:
        return (
            f"WalletPortfolio(owner={self.owner[:8]}..., "
            f"sol={self.sol_balance:.4f}, "
            f"tokens={len(self.token_accounts)})"
        )
