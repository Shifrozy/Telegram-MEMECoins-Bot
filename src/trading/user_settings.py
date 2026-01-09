"""
User Trading Settings Manager

Manages per-user trading preferences:
- Default buy amount
- Take Profit percentage
- Stop Loss percentage
- Auto buy confirmation toggle
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict

from src.config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class UserSettings:
    """
    User's trading preferences.
    """
    user_id: int
    
    # Trading defaults
    default_buy_amount_sol: float = 0.1  # Default SOL to spend
    take_profit_pct: float = 50.0        # Default TP (50% gain)
    stop_loss_pct: float = 25.0          # Default SL (25% loss)
    
    # Auto trading
    auto_buy_confirm: bool = True        # Require confirmation before buy
    auto_tp_sl: bool = True              # Auto-enable TP/SL on new positions
    
    # Slippage
    slippage_bps: int = 300              # 3% slippage default for memecoins
    
    # Quick amounts (for button presets)
    quick_amounts: list = None
    
    def __post_init__(self):
        if self.quick_amounts is None:
            self.quick_amounts = [0.05, 0.1, 0.25, 0.5, 1.0]
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "UserSettings":
        """Create from dictionary."""
        return cls(**data)


class UserSettingsManager:
    """
    Manages user trading settings.
    Stores settings persistently in JSON file.
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.settings_file = self.data_dir / "user_settings.json"
        
        # Cache: user_id -> UserSettings
        self._settings: Dict[int, UserSettings] = {}
        
        # Load existing settings
        self._load_settings()
    
    def _load_settings(self) -> None:
        """Load settings from file."""
        if not self.settings_file.exists():
            return
        
        try:
            with open(self.settings_file, "r") as f:
                data = json.load(f)
            
            for user_data in data.get("users", []):
                try:
                    settings = UserSettings.from_dict(user_data)
                    self._settings[settings.user_id] = settings
                except Exception as e:
                    logger.error("load_user_settings_error", error=str(e))
            
            logger.info("user_settings_loaded", count=len(self._settings))
        except Exception as e:
            logger.error("load_settings_file_error", error=str(e))
    
    def _save_settings(self) -> None:
        """Save settings to file."""
        try:
            data = {
                "users": [s.to_dict() for s in self._settings.values()]
            }
            with open(self.settings_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("save_settings_error", error=str(e))
    
    def get_settings(self, user_id: int) -> UserSettings:
        """
        Get or create settings for a user.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            UserSettings for the user
        """
        if user_id not in self._settings:
            self._settings[user_id] = UserSettings(user_id=user_id)
            self._save_settings()
        
        return self._settings[user_id]
    
    def update_settings(
        self,
        user_id: int,
        default_buy_amount_sol: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        auto_buy_confirm: Optional[bool] = None,
        auto_tp_sl: Optional[bool] = None,
        slippage_bps: Optional[int] = None,
    ) -> UserSettings:
        """
        Update user settings.
        
        Args:
            user_id: Telegram user ID
            Other args: Settings to update (None = don't change)
        
        Returns:
            Updated UserSettings
        """
        settings = self.get_settings(user_id)
        
        if default_buy_amount_sol is not None:
            settings.default_buy_amount_sol = default_buy_amount_sol
        
        if take_profit_pct is not None:
            settings.take_profit_pct = take_profit_pct
        
        if stop_loss_pct is not None:
            settings.stop_loss_pct = stop_loss_pct
        
        if auto_buy_confirm is not None:
            settings.auto_buy_confirm = auto_buy_confirm
        
        if auto_tp_sl is not None:
            settings.auto_tp_sl = auto_tp_sl
        
        if slippage_bps is not None:
            settings.slippage_bps = slippage_bps
        
        self._save_settings()
        return settings
    
    def set_buy_amount(self, user_id: int, amount: float) -> UserSettings:
        """Quick setter for buy amount."""
        return self.update_settings(user_id, default_buy_amount_sol=amount)
    
    def set_tp(self, user_id: int, tp_pct: float) -> UserSettings:
        """Quick setter for Take Profit."""
        return self.update_settings(user_id, take_profit_pct=tp_pct)
    
    def set_sl(self, user_id: int, sl_pct: float) -> UserSettings:
        """Quick setter for Stop Loss."""
        return self.update_settings(user_id, stop_loss_pct=sl_pct)
    
    def toggle_auto_confirm(self, user_id: int) -> UserSettings:
        """Toggle auto buy confirmation."""
        settings = self.get_settings(user_id)
        return self.update_settings(
            user_id, 
            auto_buy_confirm=not settings.auto_buy_confirm
        )
    
    def get_quick_amounts(self, user_id: int) -> list:
        """Get quick buy amount buttons for user."""
        settings = self.get_settings(user_id)
        return settings.quick_amounts
    
    def format_settings_message(self, user_id: int) -> str:
        """Format settings for display."""
        s = self.get_settings(user_id)
        
        confirm_status = "✅ ON" if s.auto_buy_confirm else "❌ OFF"
        tp_sl_status = "✅ ON" if s.auto_tp_sl else "❌ OFF"
        
        return f"""
⚙️ **Your Trading Settings**

💰 **Default Buy Amount:** {s.default_buy_amount_sol} SOL

📈 **Take Profit:** {s.take_profit_pct}%
📉 **Stop Loss:** {s.stop_loss_pct}%

🔔 **Auto Buy Confirm:** {confirm_status}
🎯 **Auto TP/SL:** {tp_sl_status}

📊 **Slippage:** {s.slippage_bps / 100}%

━━━━━━━━━━━━━━━━━━━━

_Use the buttons below to change settings_
"""
