"""
Inline keyboard builders for the Telegram bot.
Clean, advanced trading interface.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Optional


# ==========================================
# MAIN TRADING MENU - SIMPLIFIED & ADVANCED
# ==========================================

def build_main_menu() -> InlineKeyboardMarkup:
    """Build the main trading menu."""
    keyboard = [
        # Row 1: Quick Trade
        [
            InlineKeyboardButton("🟢 Buy", callback_data="trade_buy"),
            InlineKeyboardButton("🔴 Sell", callback_data="trade_sell"),
        ],
        # Row 2: Positions & Wallet
        [
            InlineKeyboardButton("📊 Positions", callback_data="menu_positions"),
            InlineKeyboardButton("💼 Wallet", callback_data="wallet_manage"),
        ],
        # Row 3: Copy Trade & Settings
        [
            InlineKeyboardButton("📋 Copy Trade", callback_data="menu_copy"),
            InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
        ],
        # Row 4: Status
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="menu_refresh"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_wallet_setup_menu() -> InlineKeyboardMarkup:
    """Initial wallet setup menu."""
    keyboard = [
        [InlineKeyboardButton("🆕 Generate New Wallet", callback_data="wallet_generate")],
        [InlineKeyboardButton("📥 Import Existing Wallet", callback_data="wallet_import")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_main_trading_menu() -> InlineKeyboardMarkup:
    """Main trading menu after wallet is set up."""
    return build_main_menu()


# ==========================================
# BUY MENU WITH AMOUNT SELECTION
# ==========================================

def build_buy_menu(token_address: str = "") -> InlineKeyboardMarkup:
    """Build buy confirmation menu with amount options."""
    prefix = token_address[:16] if token_address else ""
    keyboard = [
        # Quick amounts
        [
            InlineKeyboardButton("0.05 SOL", callback_data=f"buy_exec_0.05_{prefix}"),
            InlineKeyboardButton("0.1 SOL", callback_data=f"buy_exec_0.1_{prefix}"),
            InlineKeyboardButton("0.25 SOL", callback_data=f"buy_exec_0.25_{prefix}"),
        ],
        [
            InlineKeyboardButton("0.5 SOL", callback_data=f"buy_exec_0.5_{prefix}"),
            InlineKeyboardButton("1 SOL", callback_data=f"buy_exec_1_{prefix}"),
            InlineKeyboardButton("2 SOL", callback_data=f"buy_exec_2_{prefix}"),
        ],
        # Use default
        [
            InlineKeyboardButton("✅ Use Default Amount", callback_data=f"buy_exec_default_{prefix}"),
        ],
        # Cancel
        [InlineKeyboardButton("❌ Cancel", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_buy_confirm_menu(token_address: str, amount: float) -> InlineKeyboardMarkup:
    """Final buy confirmation."""
    prefix = token_address[:16]
    keyboard = [
        [
            InlineKeyboardButton(f"✅ BUY {amount} SOL", callback_data=f"buy_confirm_{amount}_{prefix}"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# SELL MENU WITH PERCENTAGE SELECTION
# ==========================================

def build_sell_menu(token_address: str = "") -> InlineKeyboardMarkup:
    """Build sell menu with percentage options."""
    prefix = token_address[:16] if token_address else ""
    keyboard = [
        [
            InlineKeyboardButton("25%", callback_data=f"sell_exec_25_{prefix}"),
            InlineKeyboardButton("50%", callback_data=f"sell_exec_50_{prefix}"),
            InlineKeyboardButton("100%", callback_data=f"sell_exec_100_{prefix}"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# POSITIONS MENU
# ==========================================

def build_positions_menu(positions: List[dict]) -> InlineKeyboardMarkup:
    """Build positions list menu."""
    keyboard = []
    
    for pos in positions[:5]:  # Max 5 positions shown
        symbol = pos.get("token_symbol", "???")[:6]
        pnl = pos.get("current_pnl_pct", 0)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        pos_id = pos.get("id", "")
        
        keyboard.append([
            InlineKeyboardButton(
                f"{pnl_emoji} {symbol} ({pnl:+.1f}%)",
                callback_data=f"pos_view_{pos_id}"
            )
        ])
    
    if not positions:
        keyboard.append([
            InlineKeyboardButton("📭 No Open Positions", callback_data="noop")
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def build_position_detail_menu(position_id: str) -> InlineKeyboardMarkup:
    """Build detail menu for a single position."""
    keyboard = [
        [
            InlineKeyboardButton("📈 Update TP", callback_data=f"pos_tp_{position_id}"),
            InlineKeyboardButton("📉 Update SL", callback_data=f"pos_sl_{position_id}"),
        ],
        [
            InlineKeyboardButton("🔴 Close Position", callback_data=f"pos_close_{position_id}"),
        ],
        [InlineKeyboardButton("◀️ Back to Positions", callback_data="menu_positions")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# WALLET MANAGEMENT
# ==========================================

def build_wallet_menu() -> InlineKeyboardMarkup:
    """Build wallet management menu."""
    keyboard = [
        [
            InlineKeyboardButton("💰 Balance", callback_data="wallet_balance"),
            InlineKeyboardButton("📥 Deposit", callback_data="wallet_deposit"),
        ],
        [
            InlineKeyboardButton("📤 Withdraw", callback_data="wallet_withdraw"),
            InlineKeyboardButton("🔑 Export Key", callback_data="wallet_export"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="wallet_balance"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_wallet_management_menu() -> InlineKeyboardMarkup:
    """Alias for wallet menu."""
    return build_wallet_menu()


def build_wallet_connection_menu() -> InlineKeyboardMarkup:
    """Build wallet connection menu (alias)."""
    return build_wallet_setup_menu()


# ==========================================
# SETTINGS MENU
# ==========================================

def build_settings_menu(settings: dict = None) -> InlineKeyboardMarkup:
    """Build settings menu with current values."""
    settings = settings or {}
    
    buy_amt = settings.get("default_buy_amount_sol", 0.1)
    tp_pct = settings.get("take_profit_pct", 50)
    sl_pct = settings.get("stop_loss_pct", 25)
    auto_confirm = settings.get("auto_buy_confirm", True)
    slip = settings.get("slippage_bps", 300)
    
    confirm_icon = "✅" if auto_confirm else "❌"
    
    keyboard = [
        # Buy Amount
        [
            InlineKeyboardButton(f"💰 Buy Amount: {buy_amt} SOL", callback_data="set_buy_amount"),
        ],
        # TP/SL
        [
            InlineKeyboardButton(f"📈 TP: {tp_pct}%", callback_data="set_tp"),
            InlineKeyboardButton(f"📉 SL: {sl_pct}%", callback_data="set_sl"),
        ],
        # Auto confirm
        [
            InlineKeyboardButton(f"{confirm_icon} Auto Confirm", callback_data="set_auto_confirm"),
        ],
        # Slippage
        [
            InlineKeyboardButton(f"📊 Slippage: {slip/100}%", callback_data="set_slippage"),
        ],
        # Back
        [InlineKeyboardButton("◀️ Back", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_buy_amount_options() -> InlineKeyboardMarkup:
    """Build buy amount selection."""
    keyboard = [
        [
            InlineKeyboardButton("0.05", callback_data="setamt_0.05"),
            InlineKeyboardButton("0.1", callback_data="setamt_0.1"),
            InlineKeyboardButton("0.25", callback_data="setamt_0.25"),
        ],
        [
            InlineKeyboardButton("0.5", callback_data="setamt_0.5"),
            InlineKeyboardButton("1", callback_data="setamt_1"),
            InlineKeyboardButton("2", callback_data="setamt_2"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_tp_options() -> InlineKeyboardMarkup:
    """Build Take Profit percentage options."""
    keyboard = [
        [
            InlineKeyboardButton("25%", callback_data="settp_25"),
            InlineKeyboardButton("50%", callback_data="settp_50"),
            InlineKeyboardButton("75%", callback_data="settp_75"),
        ],
        [
            InlineKeyboardButton("100%", callback_data="settp_100"),
            InlineKeyboardButton("150%", callback_data="settp_150"),
            InlineKeyboardButton("200%", callback_data="settp_200"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_sl_options() -> InlineKeyboardMarkup:
    """Build Stop Loss percentage options."""
    keyboard = [
        [
            InlineKeyboardButton("10%", callback_data="setsl_10"),
            InlineKeyboardButton("15%", callback_data="setsl_15"),
            InlineKeyboardButton("20%", callback_data="setsl_20"),
        ],
        [
            InlineKeyboardButton("25%", callback_data="setsl_25"),
            InlineKeyboardButton("30%", callback_data="setsl_30"),
            InlineKeyboardButton("50%", callback_data="setsl_50"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_slippage_options() -> InlineKeyboardMarkup:
    """Build slippage selection."""
    keyboard = [
        [
            InlineKeyboardButton("1%", callback_data="setslip_100"),
            InlineKeyboardButton("2%", callback_data="setslip_200"),
            InlineKeyboardButton("3%", callback_data="setslip_300"),
        ],
        [
            InlineKeyboardButton("5%", callback_data="setslip_500"),
            InlineKeyboardButton("10%", callback_data="setslip_1000"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# COPY TRADING MENU
# ==========================================

def build_copy_trade_menu(enabled: bool = False, tracked_count: int = 0) -> InlineKeyboardMarkup:
    """Build copy trading menu."""
    toggle_text = "🔴 Disable" if enabled else "🟢 Enable"
    toggle_data = "copy_disable" if enabled else "copy_enable"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Wallet", callback_data="copy_add_wallet")],
        [InlineKeyboardButton(f"📋 Tracked ({tracked_count})", callback_data="copy_view_wallets")],
        [InlineKeyboardButton(toggle_text, callback_data=toggle_data)],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_tracked_wallets_menu(wallets: List[dict]) -> InlineKeyboardMarkup:
    """Build tracked wallets list."""
    keyboard = []
    
    for w in wallets[:5]:
        name = w.get("name", "Unknown")[:12]
        addr = w.get("address", "")[:8]
        keyboard.append([
            InlineKeyboardButton(
                f"👛 {name} ({addr}...)",
                callback_data=f"copy_wallet_{w.get('address', '')[:20]}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Add Wallet", callback_data="copy_add_wallet")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="menu_copy")])
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# TOKEN INFO & QUICK TRADE
# ==========================================

def build_token_action_menu(token_address: str, token_symbol: str = "") -> InlineKeyboardMarkup:
    """Build quick action menu for a token."""
    prefix = token_address[:16]
    keyboard = [
        # Quick buy amounts
        [
            InlineKeyboardButton("🟢 0.1 SOL", callback_data=f"qbuy_0.1_{prefix}"),
            InlineKeyboardButton("🟢 0.5 SOL", callback_data=f"qbuy_0.5_{prefix}"),
            InlineKeyboardButton("🟢 1 SOL", callback_data=f"qbuy_1_{prefix}"),
        ],
        # Sell options
        [
            InlineKeyboardButton("🔴 Sell 50%", callback_data=f"qsell_50_{prefix}"),
            InlineKeyboardButton("🔴 Sell 100%", callback_data=f"qsell_100_{prefix}"),
        ],
        # Info
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"token_refresh_{prefix}"),
            InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{token_address}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# UTILITY BUTTONS
# ==========================================

def build_back_button(callback: str = "menu_main") -> InlineKeyboardMarkup:
    """Simple back button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back", callback_data=callback)]
    ])


def build_confirm_cancel(confirm_data: str, cancel_data: str = "menu_main") -> InlineKeyboardMarkup:
    """Confirm/Cancel buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=confirm_data),
            InlineKeyboardButton("❌ Cancel", callback_data=cancel_data),
        ]
    ])


# ==========================================
# LEGACY SUPPORT (for backwards compatibility)
# ==========================================

def build_buy_amount_menu(token_prefix: str = "") -> InlineKeyboardMarkup:
    """Legacy buy amount menu."""
    return build_buy_menu(token_prefix)


def build_sell_percent_menu(token_prefix: str = "") -> InlineKeyboardMarkup:
    """Legacy sell percent menu."""
    return build_sell_menu(token_prefix)


def build_wallet_actions(address: str, name: str) -> InlineKeyboardMarkup:
    """Build wallet action buttons."""
    short_addr = address[:16]
    keyboard = [
        [
            InlineKeyboardButton("📋 Activity", callback_data=f"wact_{short_addr}"),
            InlineKeyboardButton("📊 Stats", callback_data=f"wstats_{short_addr}"),
        ],
        [
            InlineKeyboardButton("🗑️ Remove", callback_data=f"copy_remove_{short_addr}"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="copy_view_wallets")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_quick_buy_amounts() -> InlineKeyboardMarkup:
    """Quick buy amounts."""
    return build_buy_menu()


def build_quick_sell_percentages() -> InlineKeyboardMarkup:
    """Quick sell percentages."""
    return build_sell_menu()


def build_wallet_menu(wallets: List[dict]) -> InlineKeyboardMarkup:
    """Legacy wallet menu - now uses tracked wallets menu."""
    return build_tracked_wallets_menu(wallets)
