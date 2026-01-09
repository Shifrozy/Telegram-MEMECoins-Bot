"""
User Wallet Manager - Trojan/BonkBot Style

Each user gets their own auto-generated wallet when they first start the bot.
Users can also import their own private key or export their wallet.

This is the core of the custodial wallet system.
"""

import json
import os
import base58
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Optional, Tuple
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from src.config.logging_config import get_logger

logger = get_logger(__name__)


def generate_encryption_key(password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
    """Generate encryption key from password."""
    if salt is None:
        salt = os.urandom(16)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt


@dataclass
class UserWallet:
    """Represents a user's trading wallet."""
    user_id: int
    public_key: str
    encrypted_private_key: str  # Encrypted with user-specific key
    salt: str  # Base64 encoded salt for encryption
    wallet_name: str = "Main Wallet"
    created_at: str = ""
    is_imported: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'UserWallet':
        return cls(**data)


class UserWalletManager:
    """
    Manages user wallets - Trojan/BonkBot style.
    
    Features:
    - Auto-generates wallet on first start
    - Allows importing existing private keys
    - Securely stores encrypted private keys
    - Allows exporting (backup) private keys
    - Per-user wallet isolation
    """
    
    # Master encryption password - in production, use environment variable
    MASTER_PASSWORD = "solana_trading_bot_2024_secure_key"
    
    def __init__(self, data_dir: str = "data"):
        """Initialize wallet manager."""
        self.data_dir = Path(data_dir)
        self.wallets_dir = self.data_dir / "wallets"
        self.wallets_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache loaded wallets
        self._wallets: Dict[int, UserWallet] = {}
        self._keypairs: Dict[int, Keypair] = {}
    
    def _get_wallet_file(self, user_id: int) -> Path:
        """Get wallet file path for user."""
        return self.wallets_dir / f"wallet_{user_id}.json"
    
    def _encrypt_private_key(self, private_key: str, user_id: int) -> Tuple[str, str]:
        """Encrypt private key for storage."""
        password = f"{self.MASTER_PASSWORD}_{user_id}"
        key, salt = generate_encryption_key(password)
        fernet = Fernet(key)
        encrypted = fernet.encrypt(private_key.encode())
        return encrypted.decode(), base64.b64encode(salt).decode()
    
    def _decrypt_private_key(self, encrypted_key: str, salt_b64: str, user_id: int) -> str:
        """Decrypt stored private key."""
        password = f"{self.MASTER_PASSWORD}_{user_id}"
        salt = base64.b64decode(salt_b64)
        key, _ = generate_encryption_key(password, salt)
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_key.encode())
        return decrypted.decode()
    
    def has_wallet(self, user_id: int) -> bool:
        """Check if user has a wallet."""
        if user_id in self._wallets:
            return True
        wallet_file = self._get_wallet_file(user_id)
        return wallet_file.exists()
    
    def generate_wallet(self, user_id: int, wallet_name: str = "Main Wallet") -> UserWallet:
        """
        Generate a new wallet for user.
        
        Args:
            user_id: Telegram user ID
            wallet_name: Optional wallet name
            
        Returns:
            UserWallet object
        """
        # Generate new keypair
        keypair = Keypair()
        public_key = str(keypair.pubkey())
        private_key = base58.b58encode(bytes(keypair)).decode()
        
        # Encrypt private key
        encrypted_key, salt = self._encrypt_private_key(private_key, user_id)
        
        # Create wallet object
        wallet = UserWallet(
            user_id=user_id,
            public_key=public_key,
            encrypted_private_key=encrypted_key,
            salt=salt,
            wallet_name=wallet_name,
            created_at=datetime.now().isoformat(),
            is_imported=False,
        )
        
        # Save to file
        self._save_wallet(wallet)
        
        # Cache
        self._wallets[user_id] = wallet
        self._keypairs[user_id] = keypair
        
        logger.info("wallet_generated", user_id=user_id, address=public_key[:8])
        return wallet
    
    def import_wallet(
        self, 
        user_id: int, 
        private_key: str,
        wallet_name: str = "Imported Wallet"
    ) -> Optional[UserWallet]:
        """
        Import existing wallet from private key.
        
        Args:
            user_id: Telegram user ID
            private_key: Base58 or JSON array private key
            wallet_name: Optional wallet name
            
        Returns:
            UserWallet object or None if invalid key
        """
        try:
            # Validate and load keypair
            keypair = self._load_keypair(private_key)
            public_key = str(keypair.pubkey())
            
            # Normalize to base58
            private_key_b58 = base58.b58encode(bytes(keypair)).decode()
            
            # Encrypt private key
            encrypted_key, salt = self._encrypt_private_key(private_key_b58, user_id)
            
            # Create wallet object
            wallet = UserWallet(
                user_id=user_id,
                public_key=public_key,
                encrypted_private_key=encrypted_key,
                salt=salt,
                wallet_name=wallet_name,
                created_at=datetime.now().isoformat(),
                is_imported=True,
            )
            
            # Save
            self._save_wallet(wallet)
            
            # Cache
            self._wallets[user_id] = wallet
            self._keypairs[user_id] = keypair
            
            logger.info("wallet_imported", user_id=user_id, address=public_key[:8])
            return wallet
            
        except Exception as e:
            logger.error("wallet_import_failed", user_id=user_id, error=str(e))
            return None
    
    def get_wallet(self, user_id: int) -> Optional[UserWallet]:
        """Get user's wallet."""
        if user_id in self._wallets:
            return self._wallets[user_id]
        
        wallet_file = self._get_wallet_file(user_id)
        if not wallet_file.exists():
            return None
        
        try:
            with open(wallet_file, "r") as f:
                data = json.load(f)
            wallet = UserWallet.from_dict(data)
            self._wallets[user_id] = wallet
            return wallet
        except Exception as e:
            logger.error("wallet_load_error", user_id=user_id, error=str(e))
            return None
    
    def get_keypair(self, user_id: int) -> Optional[Keypair]:
        """Get user's keypair for signing transactions."""
        if user_id in self._keypairs:
            return self._keypairs[user_id]
        
        wallet = self.get_wallet(user_id)
        if not wallet:
            return None
        
        try:
            # Decrypt private key
            private_key = self._decrypt_private_key(
                wallet.encrypted_private_key,
                wallet.salt,
                user_id
            )
            
            # Load keypair
            keypair = self._load_keypair(private_key)
            self._keypairs[user_id] = keypair
            return keypair
            
        except Exception as e:
            logger.error("keypair_decrypt_error", user_id=user_id, error=str(e))
            return None
    
    def get_address(self, user_id: int) -> Optional[str]:
        """Get user's wallet address."""
        wallet = self.get_wallet(user_id)
        return wallet.public_key if wallet else None
    
    def export_private_key(self, user_id: int) -> Optional[str]:
        """
        Export user's private key (for backup).
        
        ⚠️ SECURITY: Only show this once, warn user to keep it safe!
        
        Returns:
            Base58 encoded private key or None
        """
        wallet = self.get_wallet(user_id)
        if not wallet:
            return None
        
        try:
            private_key = self._decrypt_private_key(
                wallet.encrypted_private_key,
                wallet.salt,
                user_id
            )
            logger.info("private_key_exported", user_id=user_id)
            return private_key
        except Exception as e:
            logger.error("export_key_error", user_id=user_id, error=str(e))
            return None
    
    def delete_wallet(self, user_id: int) -> bool:
        """Delete user's wallet."""
        wallet_file = self._get_wallet_file(user_id)
        
        try:
            if wallet_file.exists():
                wallet_file.unlink()
            
            # Clear cache
            self._wallets.pop(user_id, None)
            self._keypairs.pop(user_id, None)
            
            logger.info("wallet_deleted", user_id=user_id)
            return True
        except Exception as e:
            logger.error("wallet_delete_error", user_id=user_id, error=str(e))
            return False
    
    def _save_wallet(self, wallet: UserWallet) -> None:
        """Save wallet to file."""
        wallet_file = self._get_wallet_file(wallet.user_id)
        with open(wallet_file, "w") as f:
            json.dump(wallet.to_dict(), f, indent=2)
    
    @staticmethod
    def _load_keypair(private_key: str) -> Keypair:
        """Load keypair from various formats."""
        private_key = private_key.strip()
        
        # Try JSON array format [1,2,3,...] (64 bytes)
        if private_key.startswith("["):
            try:
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
    
    @staticmethod
    def validate_private_key(private_key: str) -> bool:
        """Check if a private key is valid."""
        try:
            UserWalletManager._load_keypair(private_key)
            return True
        except:
            return False
    
    @staticmethod
    def validate_address(address: str) -> bool:
        """Check if an address is valid."""
        try:
            Pubkey.from_string(address)
            return True
        except:
            return False
