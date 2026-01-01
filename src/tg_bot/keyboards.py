"""
Inline keyboard builders for the Telegram bot.
Creates beautiful interactive menus with buttons.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Optional


def build_main_menu() -> InlineKeyboardMarkup:
    """Build the main menu keyboard."""
    keyboard = [
        # Row 1: Core actions
        [
            InlineKeyboardButton("💰 Balance", callback_data="menu_balance"),
            InlineKeyboardButton("📊 Portfolio", callback_data="menu_portfolio"),
        ],
        # Row 2: Trading
        [
            InlineKeyboardButton("🟢 Buy", callback_data="menu_buy"),
            InlineKeyboardButton("🔴 Sell", callback_data="menu_sell"),
        ],
        # Row 3: Tracking
        [
            InlineKeyboardButton("👛 Wallets", callback_data="menu_wallets"),
            InlineKeyboardButton("📋 Activity", callback_data="menu_activity"),
        ],
        # Row 4: Copy Trading & PnL
        [
            InlineKeyboardButton("📑 Copy Trade", callback_data="menu_copy"),
            InlineKeyboardButton("📈 PnL", callback_data="menu_pnl"),
        ],
        # Row 5: Settings & Status
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
            InlineKeyboardButton("🔄 Status", callback_data="menu_status"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_back_button(callback: str = "menu_main") -> InlineKeyboardMarkup:
    """Build a simple back button."""
    keyboard = [[InlineKeyboardButton("◀️ Back", callback_data=callback)]]
    return InlineKeyboardMarkup(keyboard)


def build_trading_menu() -> InlineKeyboardMarkup:
    """Build trading sub-menu."""
    keyboard = [
        [
            InlineKeyboardButton("🟢 Quick Buy", callback_data="trade_quick_buy"),
            InlineKeyboardButton("🔴 Quick Sell", callback_data="trade_quick_sell"),
        ],
        [
            InlineKeyboardButton("📊 Positions", callback_data="trade_positions"),
            InlineKeyboardButton("📜 History", callback_data="trade_history"),
        ],
        [InlineKeyboardButton("◀️ Back to Menu", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_quick_buy_amounts() -> InlineKeyboardMarkup:
    """Build quick buy amount selection."""
    keyboard = [
        [
            InlineKeyboardButton("0.05 SOL", callback_data="buy_0.05"),
            InlineKeyboardButton("0.1 SOL", callback_data="buy_0.1"),
            InlineKeyboardButton("0.25 SOL", callback_data="buy_0.25"),
        ],
        [
            InlineKeyboardButton("0.5 SOL", callback_data="buy_0.5"),
            InlineKeyboardButton("1 SOL", callback_data="buy_1"),
            InlineKeyboardButton("Custom", callback_data="buy_custom"),
        ],
        [InlineKeyboardButton("◀️ Cancel", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_quick_sell_percentages() -> InlineKeyboardMarkup:
    """Build quick sell percentage selection."""
    keyboard = [
        [
            InlineKeyboardButton("25%", callback_data="sell_25"),
            InlineKeyboardButton("50%", callback_data="sell_50"),
            InlineKeyboardButton("75%", callback_data="sell_75"),
        ],
        [
            InlineKeyboardButton("100% (All)", callback_data="sell_100"),
            InlineKeyboardButton("Custom", callback_data="sell_custom"),
        ],
        [InlineKeyboardButton("◀️ Cancel", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_wallet_menu(wallets: List[dict]) -> InlineKeyboardMarkup:
    """Build wallet tracking menu."""
    keyboard = []
    
    # Show tracked wallets (max 5)
    for wallet in wallets[:5]:
        name = wallet.get("name", "Unknown")[:15]
        address = wallet.get("address", "")[:8]
        keyboard.append([
            InlineKeyboardButton(
                f"👛 {name} ({address}...)", 
                callback_data=f"wallet_{wallet.get('address', '')[:20]}"
            )
        ])
    
    # Add new wallet button
    keyboard.append([
        InlineKeyboardButton("➕ Track New Wallet", callback_data="wallet_add"),
    ])
    
    keyboard.append([InlineKeyboardButton("◀️ Back to Menu", callback_data="menu_main")])
    
    return InlineKeyboardMarkup(keyboard)


def build_wallet_actions(address: str, name: str) -> InlineKeyboardMarkup:
    """Build actions for a specific wallet."""
    short_addr = address[:16]
    keyboard = [
        [
            InlineKeyboardButton("📋 Activity", callback_data=f"wact_{short_addr}"),
            InlineKeyboardButton("📈 PnL", callback_data=f"wpnl_{short_addr}"),
        ],
        [
            InlineKeyboardButton("📑 Copy Trades", callback_data=f"wcopy_{short_addr}"),
            InlineKeyboardButton("📊 Stats", callback_data=f"wstats_{short_addr}"),
        ],
        [
            InlineKeyboardButton("🗑️ Stop Tracking", callback_data=f"wremove_{short_addr}"),
        ],
        [InlineKeyboardButton("◀️ Back to Wallets", callback_data="menu_wallets")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_copy_trade_confirmation(
    wallet_name: str,
    token_symbol: str,
    direction: str,
    original_amount: float,
) -> InlineKeyboardMarkup:
    """Build copy trade confirmation buttons."""
    emoji = "🟢" if direction == "buy" else "🔴"
    keyboard = [
        [
            InlineKeyboardButton(f"📋 0.05 SOL", callback_data="copy_0.05"),
            InlineKeyboardButton(f"📋 0.1 SOL", callback_data="copy_0.1"),
        ],
        [
            InlineKeyboardButton(f"📋 0.25 SOL", callback_data="copy_0.25"),
            InlineKeyboardButton(f"📋 0.5 SOL", callback_data="copy_0.5"),
        ],
        [
            InlineKeyboardButton("❌ Skip", callback_data="copy_skip"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_follow_unfollow(address: str, is_following: bool) -> InlineKeyboardMarkup:
    """Build follow/unfollow button."""
    short_addr = address[:16]
    if is_following:
        keyboard = [
            [
                InlineKeyboardButton("❌ Unfollow", callback_data=f"unfollow_{short_addr}"),
                InlineKeyboardButton("📊 Stats", callback_data=f"wstats_{short_addr}"),
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("✅ Follow", callback_data=f"follow_{short_addr}"),
                InlineKeyboardButton("📊 Stats", callback_data=f"wstats_{short_addr}"),
            ]
        ]
    return InlineKeyboardMarkup(keyboard)


def build_settings_menu(current_network: str = "mainnet") -> InlineKeyboardMarkup:
    """Build settings menu."""
    network_emoji = "🟢" if current_network == "mainnet" else "🟡"
    network_label = "Mainnet" if current_network == "mainnet" else "Devnet"
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Slippage", callback_data="set_slippage"),
            InlineKeyboardButton("💵 Default Amount", callback_data="set_amount"),
        ],
        [
            InlineKeyboardButton("🔔 Alerts", callback_data="set_alerts"),
            InlineKeyboardButton("📋 Copy Settings", callback_data="set_copy"),
        ],
        [
            InlineKeyboardButton(f"{network_emoji} Network: {network_label}", callback_data="set_network"),
        ],
        [
            InlineKeyboardButton("⚠️ Risk", callback_data="set_risk"),
        ],
        [InlineKeyboardButton("◀️ Back to Menu", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_network_menu(current_network: str = "mainnet") -> InlineKeyboardMarkup:
    """Build network selection menu."""
    mainnet_check = "✅" if current_network == "mainnet" else ""
    devnet_check = "✅" if current_network == "devnet" else ""
    
    keyboard = [
        [
            InlineKeyboardButton(f"🟢 Mainnet (Real) {mainnet_check}", callback_data="network_mainnet"),
        ],
        [
            InlineKeyboardButton(f"🟡 Devnet (Test) {devnet_check}", callback_data="network_devnet"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_slippage_options() -> InlineKeyboardMarkup:
    """Build slippage selection."""
    keyboard = [
        [
            InlineKeyboardButton("0.5%", callback_data="slip_50"),
            InlineKeyboardButton("1%", callback_data="slip_100"),
            InlineKeyboardButton("1.5%", callback_data="slip_150"),
        ],
        [
            InlineKeyboardButton("2%", callback_data="slip_200"),
            InlineKeyboardButton("3%", callback_data="slip_300"),
            InlineKeyboardButton("5%", callback_data="slip_500"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_confirm_action(
    action: str, 
    confirm_data: str, 
    cancel_data: str = "menu_main"
) -> InlineKeyboardMarkup:
    """Build confirmation dialog."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=confirm_data),
            InlineKeyboardButton("❌ Cancel", callback_data=cancel_data),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_pagination(
    current_page: int, 
    total_pages: int, 
    prefix: str
) -> InlineKeyboardMarkup:
    """Build pagination buttons."""
    keyboard = []
    row = []
    
    if current_page > 1:
        row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{prefix}_page_{current_page-1}"))
    
    row.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
    
    if current_page < total_pages:
        row.append(InlineKeyboardButton("Next ▶️", callback_data=f"{prefix}_page_{current_page+1}"))
    
    keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="menu_main")])
    
    return InlineKeyboardMarkup(keyboard)
