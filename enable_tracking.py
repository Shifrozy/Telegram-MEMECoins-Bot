"""Helper script to update config.yaml settings."""

import yaml
from pathlib import Path

def enable_wallet_tracking():
    """Enable wallet tracking in config.yaml."""
    config_path = Path("config/config.yaml")
    
    if not config_path.exists():
        print("[ERROR] config/config.yaml not found!")
        print("Creating a new config file...")
        
        # Create default config with wallet tracking enabled
        config = {
            "trading": {
                "default_slippage_bps": 100,
                "max_slippage_bps": 500,
                "default_amount_sol": 0.1,
                "priority_fee_lamports": 0,
            },
            "wallet_tracking": {
                "enabled": True,  # ENABLED!
                "monitored_wallets": [],
                "track_pnl": True,
                "history_days": 30,
            },
            "copy_trading": {
                "enabled": False,
                "tracked_wallets": [],
                "sizing_mode": "percentage",
                "fixed_size_sol": 0.1,
                "copy_percentage": 25.0,
                "copy_delay_seconds": 2.0,
            },
            "telegram": {
                "polling_interval": 1.0,
                "rich_formatting": True,
                "alerts": {
                    "trade_execution": True,
                    "trade_failure": True,
                    "copy_trade": True,
                    "wallet_activity": True,
                    "balance_change": True,
                    "error_notifications": True,
                }
            },
            "risk": {
                "max_position_percentage": 10.0,
                "daily_loss_limit_sol": 5.0,
                "stop_on_daily_limit": True,
                "max_concurrent_positions": 5,
                "confirm_above_sol": 1.0,
            },
            "advanced": {
                "rpc_timeout": 30,
                "rpc_retries": 3,
                "ws_reconnect_attempts": 5,
                "ws_ping_interval": 30,
                "tx_confirm_timeout": 60,
                "commitment": "confirmed",
            }
        }
    else:
        # Load existing config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        # Enable wallet tracking
        if "wallet_tracking" not in config:
            config["wallet_tracking"] = {}
        
        config["wallet_tracking"]["enabled"] = True
        
        print("[OK] Wallet tracking enabled!")
    
    # Save config
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print()
    print("=" * 50)
    print("[SUCCESS] Config updated!")
    print("=" * 50)
    print()
    print("wallet_tracking.enabled = True")
    print()
    print("Restart the bot to apply changes:")
    print("  python run.py")
    print()


if __name__ == "__main__":
    enable_wallet_tracking()
