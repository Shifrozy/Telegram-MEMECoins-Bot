"""
Settings management for the Solana Trading Bot.
Combines environment variables with YAML configuration file.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ===========================================
# NESTED CONFIGURATION MODELS
# ===========================================

class TrackedWallet(BaseModel):
    """Configuration for a wallet to track or copy."""
    address: str
    name: str = "Unknown"
    copy_percentage: float = 100.0
    min_trade_sol: float = 0.0
    max_trade_sol: float = float("inf")
    alert_on_buy: bool = True
    alert_on_sell: bool = True


class CopyTradingFilters(BaseModel):
    """Filters for copy trading."""
    min_trade_sol: float = 0.5
    max_trade_sol: float = 50.0
    token_whitelist: List[str] = Field(default_factory=list)
    token_blacklist: List[str] = Field(default_factory=list)
    buys_only: bool = False
    sells_only: bool = False


class CopyTradingConfig(BaseModel):
    """Copy trading configuration."""
    enabled: bool = False
    tracked_wallets: List[TrackedWallet] = Field(default_factory=list)
    filters: CopyTradingFilters = Field(default_factory=CopyTradingFilters)
    sizing_mode: str = "percentage"  # 'fixed', 'percentage', 'proportional'
    fixed_size_sol: float = 0.1
    copy_percentage: float = 25.0
    copy_delay_seconds: float = 2.0


class WalletTrackingConfig(BaseModel):
    """Wallet tracking configuration."""
    enabled: bool = False
    monitored_wallets: List[TrackedWallet] = Field(default_factory=list)
    track_pnl: bool = True
    history_days: int = 30


class TradingConfig(BaseModel):
    """Trading configuration."""
    default_slippage_bps: int = 100
    max_slippage_bps: int = 500
    default_amount_sol: float = 0.1
    priority_fee_lamports: int = 0
    auto_approve_under_sol: float = 0.0
    base_token: str = "So11111111111111111111111111111111111111112"  # SOL
    quote_tokens: List[str] = Field(default_factory=lambda: [
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    ])


class TelegramAlerts(BaseModel):
    """Telegram alert configuration."""
    trade_execution: bool = True
    trade_failure: bool = True
    copy_trade: bool = True
    wallet_activity: bool = True
    balance_change: bool = True
    error_notifications: bool = True


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""
    polling_interval: float = 1.0
    rich_formatting: bool = True
    alerts: TelegramAlerts = Field(default_factory=TelegramAlerts)


class RiskConfig(BaseModel):
    """Risk management configuration."""
    max_position_percentage: float = 10.0
    daily_loss_limit_sol: float = 5.0
    stop_on_daily_limit: bool = True
    max_concurrent_positions: int = 5
    confirm_above_sol: float = 1.0


class AdvancedConfig(BaseModel):
    """Advanced configuration."""
    rpc_timeout: int = 30
    rpc_retries: int = 3
    ws_reconnect_attempts: int = 5
    ws_ping_interval: int = 30
    tx_confirm_timeout: int = 60
    commitment: str = "confirmed"
    cache_token_metadata: bool = True
    cache_ttl_seconds: int = 300


# ===========================================
# MAIN SETTINGS CLASS
# ===========================================

class Settings(BaseSettings):
    """
    Main settings class combining environment variables and YAML config.
    
    Environment variables take precedence over YAML config.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # -----------------
    # ENVIRONMENT VARIABLES (Required)
    # -----------------
    solana_private_key: SecretStr = Field(
        ...,
        description="Wallet private key (base58 encoded)"
    )
    solana_rpc_url: str = Field(
        default="https://api.mainnet-beta.solana.com",
        description="Solana RPC endpoint"
    )
    solana_ws_url: str = Field(
        default="wss://api.mainnet-beta.solana.com",
        description="Solana WebSocket endpoint"
    )
    jupiter_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Jupiter API key from portal.jup.ag (optional, for higher rate limits)"
    )
    telegram_bot_token: SecretStr = Field(
        ...,
        description="Telegram bot token from @BotFather"
    )
    telegram_admin_id: int = Field(
        ...,
        description="Telegram user ID for admin access"
    )
    
    # -----------------
    # OPTIONAL ENVIRONMENT VARIABLES
    # -----------------
    network: str = Field(
        default="mainnet",
        description="Network: mainnet, devnet, testnet"
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    dry_run: bool = Field(
        default=False,
        description="Dry run mode - simulate trades without executing"
    )
    config_path: str = Field(
        default="config/config.yaml",
        description="Path to YAML config file"
    )
    
    # -----------------
    # YAML CONFIGURATION (Loaded on init)
    # -----------------
    trading: TradingConfig = Field(default_factory=TradingConfig)
    copy_trading: CopyTradingConfig = Field(default_factory=CopyTradingConfig)
    wallet_tracking: WalletTrackingConfig = Field(default_factory=WalletTrackingConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    advanced: AdvancedConfig = Field(default_factory=AdvancedConfig)
    
    def model_post_init(self, __context) -> None:
        """Load YAML config after environment variables."""
        self._load_yaml_config()
    
    def _load_yaml_config(self) -> None:
        """Load and merge YAML configuration file."""
        config_file = Path(self.config_path)
        
        if not config_file.exists():
            # Try relative to project root
            config_file = Path(__file__).parent.parent.parent / self.config_path
        
        if not config_file.exists():
            return  # Use defaults if no config file
        
        try:
            with open(config_file, "r") as f:
                yaml_config = yaml.safe_load(f) or {}
            
            # Merge YAML config into settings
            if "trading" in yaml_config:
                self.trading = TradingConfig(**yaml_config["trading"])
            
            if "copy_trading" in yaml_config:
                self.copy_trading = CopyTradingConfig(**yaml_config["copy_trading"])
            
            if "wallet_tracking" in yaml_config:
                self.wallet_tracking = WalletTrackingConfig(**yaml_config["wallet_tracking"])
            
            if "telegram" in yaml_config:
                self.telegram = TelegramConfig(**yaml_config["telegram"])
            
            if "risk" in yaml_config:
                self.risk = RiskConfig(**yaml_config["risk"])
            
            if "advanced" in yaml_config:
                self.advanced = AdvancedConfig(**yaml_config["advanced"])
                
        except Exception as e:
            print(f"Warning: Failed to load YAML config: {e}")
    
    @field_validator("network")
    @classmethod
    def validate_network(cls, v: str) -> str:
        """Validate network value."""
        valid_networks = {"mainnet", "devnet", "testnet"}
        if v.lower() not in valid_networks:
            raise ValueError(f"Network must be one of: {valid_networks}")
        return v.lower()
    
    def get_rpc_url(self) -> str:
        """Get the RPC URL based on network setting."""
        if self.network == "mainnet":
            return self.solana_rpc_url
        elif self.network == "devnet":
            return "https://api.devnet.solana.com"
        elif self.network == "testnet":
            return "https://api.testnet.solana.com"
        return self.solana_rpc_url
    
    def get_ws_url(self) -> str:
        """Get the WebSocket URL based on network setting."""
        if self.network == "mainnet":
            return self.solana_ws_url
        elif self.network == "devnet":
            return "wss://api.devnet.solana.com"
        elif self.network == "testnet":
            return "wss://api.testnet.solana.com"
        return self.solana_ws_url


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
