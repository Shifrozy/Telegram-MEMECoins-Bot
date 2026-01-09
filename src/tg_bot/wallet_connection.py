"""
Wallet Connection Manager for Telegram Bot

Manages user wallet connections, stores user state, and handles 
the wallet connection flow (selection, verification, confirmation).
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Optional, Any
from pathlib import Path

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Wallet types with their info
SUPPORTED_WALLETS = {
    "phantom": {
        "name": "Phantom",
        "emoji": "👻",
        "website": "https://phantom.app",
        "deeplink": "https://phantom.app/ul/browse/{url}",
    },
    "solflare": {
        "name": "Solflare", 
        "emoji": "🌊",
        "website": "https://solflare.com",
        "deeplink": "solflare://",
    },
    "backpack": {
        "name": "Backpack",
        "emoji": "🎒",
        "website": "https://backpack.app",
        "deeplink": None,
    },
    "glow": {
        "name": "Glow",
        "emoji": "🔮",
        "website": "https://glow.app",
        "deeplink": None,
    },
    "exodus": {
        "name": "Exodus",
        "emoji": "📱",
        "website": "https://exodus.com",
        "deeplink": None,
    },
    "trust": {
        "name": "Trust Wallet",
        "emoji": "🔐",
        "website": "https://trustwallet.com",
        "deeplink": None,
    },
    "manual": {
        "name": "Manual Entry",
        "emoji": "✏️",
        "website": None,
        "deeplink": None,
    },
}


@dataclass
class UserWalletState:
    """Represents a user's wallet connection state."""
    user_id: int
    wallet_type: Optional[str] = None
    wallet_address: Optional[str] = None
    is_connected: bool = False
    pending_action: Optional[str] = None  # 'awaiting_address', 'awaiting_token', etc.
    pending_data: Dict[str, Any] = field(default_factory=dict)
    connected_at: Optional[str] = None
    selected_platform: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'UserWalletState':
        """Create from dictionary."""
        return cls(**data)


class WalletConnectionManager:
    """
    Manages user wallet connections and state.
    
    Features:
    - Stores user wallet connection state
    - Handles wallet address validation
    - Persists state to disk
    - Manages pending user actions
    """
    
    def __init__(self, data_dir: str = "data"):
        """Initialize wallet connection manager."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "user_wallets.json"
        
        # In-memory state cache
        self._user_states: Dict[int, UserWalletState] = {}
        
        # Load persisted state
        self._load_state()
    
    def _load_state(self) -> None:
        """Load persisted state from disk."""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    for user_id_str, state_data in data.items():
                        user_id = int(user_id_str)
                        self._user_states[user_id] = UserWalletState.from_dict(state_data)
                logger.info("wallet_state_loaded", count=len(self._user_states))
        except Exception as e:
            logger.error("wallet_state_load_error", error=str(e))
    
    def _save_state(self) -> None:
        """Save state to disk."""
        try:
            data = {
                str(user_id): state.to_dict() 
                for user_id, state in self._user_states.items()
            }
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("wallet_state_save_error", error=str(e))
    
    def get_user_state(self, user_id: int) -> UserWalletState:
        """Get or create user state."""
        if user_id not in self._user_states:
            self._user_states[user_id] = UserWalletState(user_id=user_id)
        return self._user_states[user_id]
    
    def is_connected(self, user_id: int) -> bool:
        """Check if user has connected wallet."""
        state = self.get_user_state(user_id)
        return state.is_connected and state.wallet_address is not None
    
    def set_wallet_type(self, user_id: int, wallet_type: str) -> None:
        """Set the selected wallet type and mark as awaiting address."""
        state = self.get_user_state(user_id)
        state.wallet_type = wallet_type
        state.pending_action = "awaiting_address"
        self._save_state()
    
    def validate_solana_address(self, address: str) -> bool:
        """Validate a Solana wallet address."""
        # Solana addresses are base58 encoded, 32-44 characters
        # They typically start with letters 1-9, A-H, J-N, P-Z (no 0, I, O, l)
        if not address:
            return False
        
        # Length check: Solana addresses are typically 32-44 chars
        if len(address) < 32 or len(address) > 50:
            return False
        
        # Base58 character set (no 0, O, I, l)
        base58_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]+$')
        return bool(base58_pattern.match(address))
    
    def connect_wallet(self, user_id: int, address: str) -> bool:
        """
        Connect a wallet address for a user.
        
        Args:
            user_id: Telegram user ID
            address: Solana wallet address
            
        Returns:
            True if connected successfully
        """
        if not self.validate_solana_address(address):
            return False
        
        state = self.get_user_state(user_id)
        state.wallet_address = address
        state.is_connected = True
        state.pending_action = None
        state.connected_at = datetime.now().isoformat()
        
        self._save_state()
        logger.info("wallet_connected", user_id=user_id, address=address[:8])
        return True
    
    def disconnect_wallet(self, user_id: int) -> None:
        """Disconnect user's wallet."""
        state = self.get_user_state(user_id)
        state.wallet_address = None
        state.wallet_type = None
        state.is_connected = False
        state.pending_action = None
        state.pending_data = {}
        state.connected_at = None
        state.selected_platform = None
        
        self._save_state()
        logger.info("wallet_disconnected", user_id=user_id)
    
    def set_pending_action(
        self, 
        user_id: int, 
        action: str, 
        data: Optional[Dict] = None
    ) -> None:
        """Set pending action for user."""
        state = self.get_user_state(user_id)
        state.pending_action = action
        state.pending_data = data or {}
        self._save_state()
    
    def clear_pending_action(self, user_id: int) -> None:
        """Clear pending action for user."""
        state = self.get_user_state(user_id)
        state.pending_action = None
        state.pending_data = {}
        self._save_state()
    
    def set_platform(self, user_id: int, platform: str) -> None:
        """Set selected trading platform."""
        state = self.get_user_state(user_id)
        state.selected_platform = platform
        self._save_state()
    
    def get_wallet_info(self, wallet_type: str) -> Optional[Dict]:
        """Get wallet type information."""
        return SUPPORTED_WALLETS.get(wallet_type)
    
    def format_wallet_status(self, user_id: int) -> str:
        """Format wallet status for display."""
        state = self.get_user_state(user_id)
        
        if not state.is_connected:
            return "🔴 Not Connected"
        
        wallet_info = self.get_wallet_info(state.wallet_type)
        wallet_name = wallet_info["name"] if wallet_info else "Unknown"
        wallet_emoji = wallet_info["emoji"] if wallet_info else "🔐"
        
        short_addr = f"{state.wallet_address[:6]}...{state.wallet_address[-4:]}"
        
        return f"🟢 {wallet_emoji} {wallet_name} | `{short_addr}`"


# Token address extraction utilities
class TokenExtractor:
    """
    Extracts token addresses from various platform URLs and formats.
    
    Supports:
    - DEX Screener URLs
    - Pump.fun URLs
    - Birdeye URLs
    - Jupiter URLs
    - Raydium URLs
    - Gecko Terminal URLs
    - Raw token addresses
    """
    
    # URL patterns for different platforms
    PATTERNS = {
        "dexscreener": [
            r"dexscreener\.com/solana/([a-zA-Z0-9]+)",
            r"dexscreener\.io/solana/([a-zA-Z0-9]+)",
        ],
        "pumpfun": [
            r"pump\.fun/([a-zA-Z0-9]+)",
            r"pump\.fun/coin/([a-zA-Z0-9]+)",
        ],
        "birdeye": [
            r"birdeye\.so/token/([a-zA-Z0-9]+)",
        ],
        "jupiter": [
            r"jup\.ag/swap/.*-([a-zA-Z0-9]+)",
            r"jup\.ag/tokens/([a-zA-Z0-9]+)",
        ],
        "raydium": [
            r"raydium\.io/swap/\?.*inputMint=([a-zA-Z0-9]+)",
            r"raydium\.io/swap/\?.*outputMint=([a-zA-Z0-9]+)",
        ],
        "gecko": [
            r"geckoterminal\.com/solana/pools/([a-zA-Z0-9]+)",
        ],
        "solscan": [
            r"solscan\.io/token/([a-zA-Z0-9]+)",
        ],
    }
    
    @classmethod
    def extract_token_address(cls, text: str) -> Optional[str]:
        """
        Extract token address from text (URL or raw address).
        
        Args:
            text: URL or token address
            
        Returns:
            Token address or None if not found
        """
        text = text.strip()
        
        # First check if it's already a valid address
        if cls._is_valid_address(text):
            return text
        
        # Try to extract from URL patterns
        for platform, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    address = match.group(1)
                    if cls._is_valid_address(address):
                        return address
        
        # Try generic extraction - look for base58 addresses in the text
        # Solana addresses are typically 32-44 chars of base58
        base58_pattern = r'[1-9A-HJ-NP-Za-km-z]{32,44}'
        matches = re.findall(base58_pattern, text)
        
        for match in matches:
            if cls._is_valid_address(match):
                return match
        
        return None
    
    @classmethod
    def _is_valid_address(cls, address: str) -> bool:
        """Check if string is a valid Solana address."""
        if not address:
            return False
        if len(address) < 32 or len(address) > 50:
            return False
        base58_pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]+$')
        return bool(base58_pattern.match(address))
    
    @classmethod
    def detect_platform(cls, text: str) -> Optional[str]:
        """
        Detect which platform a URL is from.
        
        Args:
            text: URL or text
            
        Returns:
            Platform name or None
        """
        text_lower = text.lower()
        
        if "dexscreener" in text_lower:
            return "dexscreener"
        elif "pump.fun" in text_lower:
            return "pumpfun"
        elif "birdeye" in text_lower:
            return "birdeye"
        elif "jup.ag" in text_lower or "jupiter" in text_lower:
            return "jupiter"
        elif "raydium" in text_lower:
            return "raydium"
        elif "geckoterminal" in text_lower:
            return "gecko"
        elif "solscan" in text_lower:
            return "solscan"
        
        return None
