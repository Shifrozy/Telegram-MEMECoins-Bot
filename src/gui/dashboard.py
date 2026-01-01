"""
Trading Dashboard GUI

A professional, modern trading dashboard using CustomTkinter.
Features: Portfolio view, trading interface, wallet tracking, limit orders.
"""

import asyncio
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List
import customtkinter as ctk
from PIL import Image
import os

# Set appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TradingDashboard(ctk.CTk):
    """
    Main trading dashboard window.
    
    Provides a professional GUI for:
    - Portfolio overview
    - Buy/Sell trading
    - Wallet tracking
    - Limit orders management
    - Settings configuration
    """
    
    def __init__(
        self,
        settings=None,
        solana=None,
        wallet=None,
        executor=None,
        tracker=None,
        token_service=None,
        limit_service=None,
    ):
        super().__init__()
        
        # Services
        self.settings = settings
        self.solana = solana
        self.wallet = wallet
        self.executor = executor
        self.tracker = tracker
        self.token_service = token_service
        self.limit_service = limit_service
        
        # Window setup
        self.title("Solana Trading Bot")
        self.geometry("1400x850")
        self.minsize(1200, 700)
        
        # Colors
        self.colors = {
            "bg_dark": "#0f0f0f",
            "bg_card": "#1a1a1a",
            "bg_hover": "#252525",
            "accent": "#9945FF",  # Solana purple
            "accent_green": "#14F195",  # Solana green
            "green": "#00D26A",
            "red": "#FF4757",
            "text": "#FFFFFF",
            "text_secondary": "#888888",
            "border": "#333333",
        }
        
        # Configure colors
        self.configure(fg_color=self.colors["bg_dark"])
        
        # State
        self.current_page = "dashboard"
        self.sol_balance = 0.0
        self.sol_price = 0.0
        
        # Persistent storage path for GUI data
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.gui_wallets_file = self.data_dir / "gui_tracked_wallets.json"
        
        # Initialize tracked wallets list (will be loaded in _build_wallets_page)
        self.tracked_wallets: List[str] = []
        
        # Build UI
        self._build_ui()
        
        # Load saved wallets after UI is built
        self._load_tracked_wallets()
        
        # Start refresh loop
        self._start_refresh()
    
    def _build_ui(self):
        """Build the main UI layout."""
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Sidebar
        self._build_sidebar()
        
        # Main content area
        self.main_frame = ctk.CTkFrame(self, fg_color=self.colors["bg_dark"])
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        # Header
        self._build_header()
        
        # Pages container
        self.pages_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.pages_frame.grid(row=1, column=0, sticky="nsew", pady=(20, 0))
        self.pages_frame.grid_columnconfigure(0, weight=1)
        self.pages_frame.grid_rowconfigure(0, weight=1)
        
        # Build all pages
        self.pages = {}
        self._build_dashboard_page()
        self._build_trading_page()
        self._build_wallets_page()
        self._build_orders_page()
        self._build_settings_page()
        
        # Show dashboard by default
        self._show_page("dashboard")
    
    def _build_sidebar(self):
        """Build the sidebar navigation."""
        sidebar = ctk.CTkFrame(
            self,
            width=220,
            corner_radius=0,
            fg_color=self.colors["bg_card"],
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(6, weight=1)
        
        # Logo
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=(30, 40))
        
        logo_label = ctk.CTkLabel(
            logo_frame,
            text="◎ Solana Bot",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.colors["accent"],
        )
        logo_label.pack()
        
        # Navigation buttons
        nav_items = [
            ("📊", "Dashboard", "dashboard"),
            ("📈", "Trading", "trading"),
            ("👛", "Wallets", "wallets"),
            ("📋", "Orders", "orders"),
            ("⚙️", "Settings", "settings"),
        ]
        
        self.nav_buttons = {}
        for i, (icon, text, page) in enumerate(nav_items):
            btn = ctk.CTkButton(
                sidebar,
                text=f"  {icon}  {text}",
                font=ctk.CTkFont(size=15),
                anchor="w",
                height=45,
                corner_radius=10,
                fg_color="transparent",
                text_color=self.colors["text"],
                hover_color=self.colors["bg_hover"],
                command=lambda p=page: self._show_page(p),
            )
            btn.grid(row=i+1, column=0, padx=15, pady=5, sticky="ew")
            self.nav_buttons[page] = btn
        
        # Network indicator at bottom
        self.network_label = ctk.CTkLabel(
            sidebar,
            text="🟢 Mainnet",
            font=ctk.CTkFont(size=13),
            text_color=self.colors["text_secondary"],
        )
        self.network_label.grid(row=7, column=0, padx=20, pady=20)
    
    def _build_header(self):
        """Build the header bar with wallet connection."""
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        
        # Page title
        self.page_title = ctk.CTkLabel(
            header,
            text="Dashboard",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self.colors["text"],
        )
        self.page_title.grid(row=0, column=0, sticky="w")
        
        # ═══════════════════════════════════════════════════════════════
        # WALLET CONNECTION PANEL (Right side of header)
        # ═══════════════════════════════════════════════════════════════
        wallet_panel = ctk.CTkFrame(header, fg_color=self.colors["bg_card"], corner_radius=15)
        wallet_panel.grid(row=0, column=2, sticky="e")
        
        # Wallet type selector
        wallets = [
            "👻 Phantom",
            "🌟 Solflare", 
            "🎒 Backpack",
            "💼 Ledger",
            "🔐 Trust",
            "🦊 MetaMask",
            "🔑 Key",
        ]
        
        self.wallet_type_var = ctk.StringVar(value="👻 Phantom")
        self.wallet_type_menu = ctk.CTkOptionMenu(
            wallet_panel,
            values=wallets,
            variable=self.wallet_type_var,
            width=120,
            height=35,
            font=ctk.CTkFont(size=12),
            corner_radius=8,
            command=self._on_wallet_type_change,
        )
        self.wallet_type_menu.pack(side="left", padx=(10, 5), pady=8)
        
        # Private key input (compact)
        self.private_key_entry = ctk.CTkEntry(
            wallet_panel,
            placeholder_text="Private key...",
            width=180,
            height=35,
            font=ctk.CTkFont(size=11),
            show="•",
        )
        self.private_key_entry.pack(side="left", padx=5, pady=8)
        
        # Connect button
        self.connect_btn = ctk.CTkButton(
            wallet_panel,
            text="Connect",
            width=80,
            height=35,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.colors["accent"],
            corner_radius=8,
            command=self._connect_wallet,
        )
        self.connect_btn.pack(side="left", padx=5, pady=8)
        
        # Separator
        sep = ctk.CTkFrame(wallet_panel, width=2, height=30, fg_color=self.colors["border"])
        sep.pack(side="left", padx=10, pady=8)
        
        # Balance display
        balance_frame = ctk.CTkFrame(wallet_panel, fg_color="transparent")
        balance_frame.pack(side="left", padx=5, pady=8)
        
        self.balance_label = ctk.CTkLabel(
            balance_frame,
            text="0.0000 SOL",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self.colors["accent_green"],
        )
        self.balance_label.pack(side="top")
        
        self.wallet_label = ctk.CTkLabel(
            balance_frame,
            text="Not connected",
            font=ctk.CTkFont(size=10),
            text_color=self.colors["text_secondary"],
        )
        self.wallet_label.pack(side="top")
        
        # Connection status indicator
        self.status_frame = ctk.CTkFrame(wallet_panel, fg_color="transparent")
        self.status_frame.pack(side="left", padx=(5, 15), pady=8)
        
        self.status_dot = ctk.CTkLabel(
            self.status_frame,
            text="●",
            font=ctk.CTkFont(size=20),
            text_color=self.colors["red"],
        )
        self.status_dot.pack(side="left")
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Disconnected",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"],
        )
        self.status_label.pack(side="left", padx=(3, 0))
    
    def _on_wallet_type_change(self, choice):
        """Handle wallet type selection change."""
        if "Key" in choice:
            self.private_key_entry.configure(state="normal", placeholder_text="Enter private key...")
        else:
            self.private_key_entry.configure(state="normal", placeholder_text=f"Export key from {choice.split(' ')[1]}...")
    
    def _toggle_key_visibility(self):
        """Toggle private key visibility."""
        current = self.private_key_entry.cget("show")
        if current == "•":
            self.private_key_entry.configure(show="")
        else:
            self.private_key_entry.configure(show="•")
    
    def _connect_wallet(self):
        """Connect wallet with private key."""
        key = self.private_key_entry.get()
        wallet_type = self.wallet_type_var.get()
        
        if not key or len(key) < 32:
            self._show_message("Error", "Please enter a valid private key (Base58 format)")
            return
        
        # Update UI to connected state
        self.status_dot.configure(text_color=self.colors["green"])
        self.status_label.configure(text="Connected", text_color=self.colors["green"])
        self.wallet_label.configure(text=f"{key[:4]}...{key[-4:]}")
        self.connect_btn.configure(text="✓", fg_color=self.colors["green"])
        
        self._show_message(
            "✅ Wallet Connected",
            f"Successfully connected!\n\n"
            f"Wallet: {wallet_type}\n"
            f"Address: {key[:8]}...{key[-4:]}"
        )
    
    def _disconnect_wallet(self):
        """Disconnect current wallet."""
        self.status_dot.configure(text_color=self.colors["red"])
        self.status_label.configure(text="Disconnected", text_color=self.colors["text_secondary"])
        self.wallet_label.configure(text="Not connected")
        self.connect_btn.configure(text="Connect", fg_color=self.colors["accent"])
        self.private_key_entry.delete(0, "end")
    
    def _build_dashboard_page(self):
        """Build the dashboard page."""
        page = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
        page.grid_columnconfigure((0, 1, 2, 3), weight=1)
        page.grid_rowconfigure(2, weight=1)
        self.pages["dashboard"] = page
        
        # Stats cards
        stats = [
            ("💰", "Portfolio Value", "$0.00", "portfolio_value"),
            ("📊", "Total Trades", "0", "total_trades"),
            ("👛", "Tracked Wallets", "0", "tracked_wallets"),
            ("📋", "Pending Orders", "0", "pending_orders"),
        ]
        
        self.stat_labels = {}
        for i, (icon, title, value, key) in enumerate(stats):
            card = self._create_stat_card(page, icon, title, value)
            card.grid(row=0, column=i, padx=10, pady=10, sticky="ew")
            self.stat_labels[key] = card.winfo_children()[1].winfo_children()[1]
        
        # Quick actions section
        actions_frame = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        actions_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(
            actions_frame,
            text="Quick Actions",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(15, 10))
        
        btn_frame = ctk.CTkFrame(actions_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        ctk.CTkButton(
            btn_frame,
            text="🟢 Quick Buy",
            font=ctk.CTkFont(size=14),
            fg_color=self.colors["green"],
            hover_color="#00B85C",
            height=40,
            command=lambda: self._show_page("trading"),
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame,
            text="🔴 Quick Sell",
            font=ctk.CTkFont(size=14),
            fg_color=self.colors["red"],
            hover_color="#E63E4D",
            height=40,
            command=lambda: self._show_page("trading"),
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame,
            text="📋 Limit Order",
            font=ctk.CTkFont(size=14),
            fg_color=self.colors["accent"],
            height=40,
            command=lambda: self._show_page("orders"),
        ).pack(side="left", padx=5)
        
        # Token lookup
        lookup_frame = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        lookup_frame.grid(row=1, column=2, columnspan=2, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(
            lookup_frame,
            text="Token Lookup",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(15, 10))
        
        input_frame = ctk.CTkFrame(lookup_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        self.token_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Enter token address...",
            height=40,
            width=250,
        )
        self.token_entry.pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(
            input_frame,
            text="Search",
            height=40,
            command=self._lookup_token,
        ).pack(side="left")
        
        # Activity log
        activity_frame = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        activity_frame.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(
            activity_frame,
            text="Recent Activity",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=20, pady=15)
        
        self.activity_text = ctk.CTkTextbox(
            activity_frame,
            font=ctk.CTkFont(size=13),
            fg_color=self.colors["bg_dark"],
            corner_radius=10,
        )
        self.activity_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.activity_text.insert("1.0", "No recent activity\n")
        self.activity_text.configure(state="disabled")
    
    def _build_trading_page(self):
        """Build the trading page with unified Buy/Sell panel."""
        page = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        self.pages["trading"] = page
        
        # Trade mode state
        self.trade_mode = "buy"  # "buy" or "sell"
        
        # Main trading card - centered
        trade_frame = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=20)
        trade_frame.grid(row=0, column=0, padx=100, pady=20, sticky="nsew")
        trade_frame.grid_columnconfigure(0, weight=1)
        
        # Header with title
        header_frame = ctk.CTkFrame(trade_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 15))
        
        self.trade_title = ctk.CTkLabel(
            header_frame,
            text="🟢 Buy Token",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.colors["green"],
        )
        self.trade_title.pack(side="left")
        
        # Buy/Sell toggle buttons
        toggle_frame = ctk.CTkFrame(trade_frame, fg_color=self.colors["bg_dark"], corner_radius=10)
        toggle_frame.pack(fill="x", padx=30, pady=(0, 20))
        
        self.buy_toggle_btn = ctk.CTkButton(
            toggle_frame,
            text="🟢 BUY",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=self.colors["green"],
            hover_color="#00B85C",
            height=45,
            corner_radius=8,
            command=lambda: self._set_trade_mode("buy"),
        )
        self.buy_toggle_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        self.sell_toggle_btn = ctk.CTkButton(
            toggle_frame,
            text="🔴 SELL",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=self.colors["bg_hover"],
            hover_color="#E63E4D",
            height=45,
            corner_radius=8,
            command=lambda: self._set_trade_mode("sell"),
        )
        self.sell_toggle_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        # Token input
        ctk.CTkLabel(
            trade_frame, 
            text="Token Address", 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w", padx=30)
        
        self.trade_token_entry = ctk.CTkEntry(
            trade_frame, 
            placeholder_text="Enter token address or paste from clipboard...", 
            height=50,
            font=ctk.CTkFont(size=14),
            corner_radius=10,
        )
        self.trade_token_entry.pack(fill="x", padx=30, pady=(8, 20))
        
        # Amount section
        self.amount_label = ctk.CTkLabel(
            trade_frame, 
            text="Amount (SOL)", 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_secondary"],
        )
        self.amount_label.pack(anchor="w", padx=30)
        
        # Quick amount buttons
        amount_btn_frame = ctk.CTkFrame(trade_frame, fg_color="transparent")
        amount_btn_frame.pack(fill="x", padx=30, pady=(8, 10))
        
        self.amount_buttons = []
        for amt in ["0.05", "0.1", "0.25", "0.5", "1.0"]:
            btn = ctk.CTkButton(
                amount_btn_frame,
                text=amt,
                width=80,
                height=40,
                font=ctk.CTkFont(size=14),
                fg_color=self.colors["bg_hover"],
                hover_color=self.colors["accent"],
                corner_radius=8,
                command=lambda a=amt: self._set_trade_amount(a),
            )
            btn.pack(side="left", padx=3, expand=True)
            self.amount_buttons.append(btn)
        
        # Amount entry
        self.trade_amount_entry = ctk.CTkEntry(
            trade_frame, 
            placeholder_text="0.0", 
            height=50,
            font=ctk.CTkFont(size=16),
            corner_radius=10,
        )
        self.trade_amount_entry.pack(fill="x", padx=30, pady=(5, 20))
        
        # Sell percentage buttons (hidden by default)
        self.sell_pct_frame = ctk.CTkFrame(trade_frame, fg_color="transparent")
        
        for pct in ["25%", "50%", "75%", "100%"]:
            ctk.CTkButton(
                self.sell_pct_frame,
                text=pct,
                width=90,
                height=40,
                font=ctk.CTkFont(size=14),
                fg_color=self.colors["bg_hover"],
                hover_color=self.colors["red"],
                corner_radius=8,
                command=lambda p=pct: self._set_sell_percent(p),
            ).pack(side="left", padx=3, expand=True)
        
        # Execute button
        self.execute_btn = ctk.CTkButton(
            trade_frame,
            text="BUY NOW",
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=self.colors["green"],
            hover_color="#00B85C",
            height=60,
            corner_radius=12,
            command=self._execute_trade,
        )
        self.execute_btn.pack(fill="x", padx=30, pady=(10, 30))
        
        # Info section
        info_frame = ctk.CTkFrame(trade_frame, fg_color=self.colors["bg_dark"], corner_radius=10)
        info_frame.pack(fill="x", padx=30, pady=(0, 25))
        
        self.trade_info_label = ctk.CTkLabel(
            info_frame,
            text="💡 Enter token address and amount to trade",
            font=ctk.CTkFont(size=13),
            text_color=self.colors["text_secondary"],
        )
        self.trade_info_label.pack(pady=15)
    
    def _set_trade_mode(self, mode: str):
        """Switch between buy and sell mode."""
        self.trade_mode = mode
        
        if mode == "buy":
            # Update UI for buy mode
            self.trade_title.configure(text="🟢 Buy Token", text_color=self.colors["green"])
            self.buy_toggle_btn.configure(fg_color=self.colors["green"])
            self.sell_toggle_btn.configure(fg_color=self.colors["bg_hover"])
            self.amount_label.configure(text="Amount (SOL)")
            self.execute_btn.configure(
                text="BUY NOW",
                fg_color=self.colors["green"],
                hover_color="#00B85C",
            )
            self.sell_pct_frame.pack_forget()
            self.trade_info_label.configure(text="💡 Enter token address and SOL amount to buy")
        else:
            # Update UI for sell mode
            self.trade_title.configure(text="🔴 Sell Token", text_color=self.colors["red"])
            self.buy_toggle_btn.configure(fg_color=self.colors["bg_hover"])
            self.sell_toggle_btn.configure(fg_color=self.colors["red"])
            self.amount_label.configure(text="Sell Percentage")
            self.execute_btn.configure(
                text="SELL NOW",
                fg_color=self.colors["red"],
                hover_color="#E63E4D",
            )
            self.sell_pct_frame.pack(fill="x", padx=30, pady=(0, 10))
            self.trade_info_label.configure(text="💡 Enter token address and select percentage to sell")
    
    def _set_trade_amount(self, amount: str):
        """Set trade amount from quick button."""
        self.trade_amount_entry.delete(0, "end")
        self.trade_amount_entry.insert(0, amount)
    
    def _execute_trade(self):
        """Execute the current trade."""
        token = self.trade_token_entry.get()
        amount = self.trade_amount_entry.get()
        
        if not token:
            self._show_message("Error", "Please enter token address")
            return
        
        if self.trade_mode == "buy":
            if not amount:
                self._show_message("Error", "Please enter amount")
                return
            self._show_message("Buy Order", f"Buying {amount} SOL of\n{token[:20]}...")
        else:
            self._show_message("Sell Order", f"Selling {token[:20]}...")
    
    def _build_wallets_page(self):
        """Build the wallets page."""
        page = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.pages["wallets"] = page
        
        # Header with add button
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        ctk.CTkLabel(
            header,
            text="Tracked Wallets",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")
        
        ctk.CTkButton(
            header,
            text="+ Add Wallet",
            fg_color=self.colors["accent"],
            height=35,
            command=self._add_wallet_dialog,
        ).pack(side="right")
        
        ctk.CTkButton(
            header,
            text="Refresh",
            fg_color=self.colors["bg_hover"],
            height=35,
            width=80,
            command=self._refresh_wallets_list,
        ).pack(side="right", padx=10)
        
        # Wallets list
        wallets_frame = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        wallets_frame.grid(row=1, column=0, sticky="nsew")
        
        self.wallets_scroll = ctk.CTkScrollableFrame(
            wallets_frame,
            fg_color="transparent",
        )
        self.wallets_scroll.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Initialize tracked wallets list
        self.tracked_wallets = []
        
        # Empty state label
        self.no_wallets_label = ctk.CTkLabel(
            self.wallets_scroll,
            text="No wallets being tracked\n\nClick '+ Add Wallet' to track a wallet",
            font=ctk.CTkFont(size=14),
            text_color=self.colors["text_secondary"],
        )
        self.no_wallets_label.pack(pady=50)
    
    def _build_orders_page(self):
        """Build the orders page."""
        page = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.pages["orders"] = page
        
        # Header
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        ctk.CTkLabel(
            header,
            text="Limit Orders",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")
        
        ctk.CTkButton(
            header,
            text="+ New Order",
            fg_color=self.colors["accent"],
            height=35,
            command=self._new_order_dialog,
        ).pack(side="right")
        
        ctk.CTkButton(
            header,
            text="Refresh",
            fg_color=self.colors["bg_hover"],
            height=35,
            width=80,
            command=self._refresh_orders_list,
        ).pack(side="right", padx=10)
        
        # Orders list
        orders_frame = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        orders_frame.grid(row=1, column=0, sticky="nsew")
        
        self.orders_scroll = ctk.CTkScrollableFrame(
            orders_frame,
            fg_color="transparent",
        )
        self.orders_scroll.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Initialize limit orders list
        self.gui_limit_orders = []
        self._load_gui_orders()
        
        # Will be populated by _refresh_orders_list
        self._refresh_orders_list()
    
    def _build_settings_page(self):
        """Build the settings page."""
        page = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
        page.grid_columnconfigure((0, 1), weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.pages["settings"] = page
        
        # ═══════════════════════════════════════════════════════════════
        # TRADING SETTINGS
        # ═══════════════════════════════════════════════════════════════
        trading_card = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        trading_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(
            trading_card,
            text="⚙️ Trading Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=25, pady=20)
        
        # Slippage
        ctk.CTkLabel(trading_card, text="Default Slippage", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=25)
        self.slippage_var = ctk.StringVar(value="1%")
        slippage_menu = ctk.CTkOptionMenu(
            trading_card,
            values=["0.5%", "1%", "1.5%", "2%", "3%", "5%"],
            variable=self.slippage_var,
            height=35,
        )
        slippage_menu.pack(fill="x", padx=25, pady=(5, 15))
        
        # Default amount
        ctk.CTkLabel(trading_card, text="Default Amount (SOL)", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=25)
        self.default_amount_entry = ctk.CTkEntry(trading_card, placeholder_text="0.1", height=35)
        self.default_amount_entry.pack(fill="x", padx=25, pady=(5, 15))
        self.default_amount_entry.insert(0, "0.1")
        
        # Copy trading toggle
        copy_frame = ctk.CTkFrame(trading_card, fg_color="transparent")
        copy_frame.pack(fill="x", padx=25, pady=(5, 20))
        
        ctk.CTkLabel(copy_frame, text="Copy Trading", font=ctk.CTkFont(size=13)).pack(side="left")
        self.copy_switch = ctk.CTkSwitch(copy_frame, text="")
        self.copy_switch.pack(side="right")
        
        # ═══════════════════════════════════════════════════════════════
        # NETWORK SETTINGS
        # ═══════════════════════════════════════════════════════════════
        network_card = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        network_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(
            network_card,
            text="🌐 Network",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=25, pady=20)
        
        # Network selector
        self.network_var = ctk.StringVar(value="mainnet")
        
        ctk.CTkRadioButton(
            network_card,
            text="🟢 Mainnet (Real Trading)",
            variable=self.network_var,
            value="mainnet",
        ).pack(anchor="w", padx=25, pady=5)
        
        ctk.CTkRadioButton(
            network_card,
            text="🟡 Devnet (Test Mode)",
            variable=self.network_var,
            value="devnet",
        ).pack(anchor="w", padx=25, pady=5)
        
        ctk.CTkLabel(
            network_card,
            text="⚠️ Restart bot after changing network",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w", padx=25, pady=15)
        
        # RPC URL
        ctk.CTkLabel(
            network_card, 
            text="Custom RPC URL (Optional)", 
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w", padx=25, pady=(10, 0))
        
        self.rpc_entry = ctk.CTkEntry(
            network_card, 
            placeholder_text="https://api.mainnet-beta.solana.com", 
            height=35,
        )
        self.rpc_entry.pack(fill="x", padx=25, pady=(5, 20))
        
        # ═══════════════════════════════════════════════════════════════
        # RISK SETTINGS (Row 1, Column 0)
        # ═══════════════════════════════════════════════════════════════
        risk_card = ctk.CTkFrame(page, fg_color=self.colors["bg_card"], corner_radius=15)
        risk_card.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(
            risk_card,
            text="⚠️ Risk Management",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=25, pady=20)
        
        risk_frame = ctk.CTkFrame(risk_card, fg_color="transparent")
        risk_frame.pack(fill="x", padx=25, pady=(0, 20))
        
        # Max position
        ctk.CTkLabel(risk_frame, text="Max Position Size (%)", font=ctk.CTkFont(size=13)).pack(side="left")
        self.max_position_entry = ctk.CTkEntry(risk_frame, width=80, height=35, placeholder_text="25")
        self.max_position_entry.pack(side="right")
        self.max_position_entry.insert(0, "25")
        
        risk_frame2 = ctk.CTkFrame(risk_card, fg_color="transparent")
        risk_frame2.pack(fill="x", padx=25, pady=(0, 20))
        
        # Daily loss limit
        ctk.CTkLabel(risk_frame2, text="Daily Loss Limit (SOL)", font=ctk.CTkFont(size=13)).pack(side="left")
        self.loss_limit_entry = ctk.CTkEntry(risk_frame2, width=80, height=35, placeholder_text="1.0")
        self.loss_limit_entry.pack(side="right")
        self.loss_limit_entry.insert(0, "1.0")
    
    def _create_stat_card(self, parent, icon: str, title: str, value: str) -> ctk.CTkFrame:
        """Create a statistics card."""
        card = ctk.CTkFrame(parent, fg_color=self.colors["bg_card"], corner_radius=15)
        
        icon_label = ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=30))
        icon_label.pack(anchor="w", padx=20, pady=(20, 5))
        
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(anchor="w", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(
            content,
            text=title,
            font=ctk.CTkFont(size=13),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            content,
            text=value,
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w")
        
        return card
    
    def _show_page(self, page_name: str):
        """Show a specific page."""
        # Hide all pages
        for name, page in self.pages.items():
            page.grid_forget()
        
        # Show selected page
        if page_name in self.pages:
            self.pages[page_name].grid(row=0, column=0, sticky="nsew")
            self.current_page = page_name
            
            # Update title
            titles = {
                "dashboard": "Dashboard",
                "trading": "Trading",
                "wallets": "Wallets",
                "orders": "Limit Orders",
                "settings": "Settings",
            }
            self.page_title.configure(text=titles.get(page_name, "Dashboard"))
            
            # Update nav buttons
            for name, btn in self.nav_buttons.items():
                if name == page_name:
                    btn.configure(fg_color=self.colors["accent"])
                else:
                    btn.configure(fg_color="transparent")
    
    def _lookup_token(self):
        """Look up token info."""
        address = self.token_entry.get()
        if not address:
            return
        
        # Show loading
        self.token_entry.configure(placeholder_text="Searching...")
        
        # In real app, would call token service here
        self._show_message("Token Lookup", f"Looking up: {address[:16]}...")
    
    def _set_sell_percent(self, percent: str):
        """Set sell percentage."""
        # Update the trade amount entry with percentage
        self.trade_amount_entry.delete(0, "end")
        self.trade_amount_entry.insert(0, percent)
    
    def _add_wallet_dialog(self):
        """Show add wallet dialog."""
        dialog = ctk.CTkInputDialog(
            text="Enter wallet address to track:",
            title="Add Wallet",
        )
        address = dialog.get_input()
        
        if address and len(address) >= 32:
            # Add to tracked wallets list
            if address not in self.tracked_wallets:
                self.tracked_wallets.append(address)
                self._save_tracked_wallets()  # Save to file
                self._refresh_wallets_list()
                self._show_message("✅ Wallet Added", f"Now tracking:\n{address[:20]}...{address[-8:]}")
            else:
                self._show_message("Already Tracking", "This wallet is already being tracked.")
        elif address:
            self._show_message("Invalid Address", "Please enter a valid Solana wallet address.")
    
    def _remove_wallet(self, address: str):
        """Remove a wallet from tracking."""
        if address in self.tracked_wallets:
            self.tracked_wallets.remove(address)
            self._save_tracked_wallets()  # Save to file
            self._refresh_wallets_list()
    
    def _refresh_wallets_list(self):
        """Refresh the displayed wallets list."""
        # Clear current list
        for widget in self.wallets_scroll.winfo_children():
            widget.destroy()
        
        if not self.tracked_wallets:
            # Show empty state
            self.no_wallets_label = ctk.CTkLabel(
                self.wallets_scroll,
                text="No wallets being tracked\n\nClick '+ Add Wallet' to track a wallet",
                font=ctk.CTkFont(size=14),
                text_color=self.colors["text_secondary"],
            )
            self.no_wallets_label.pack(pady=50)
        else:
            # Display each wallet
            for i, address in enumerate(self.tracked_wallets):
                wallet_row = ctk.CTkFrame(
                    self.wallets_scroll,
                    fg_color=self.colors["bg_dark"],
                    corner_radius=10,
                )
                wallet_row.pack(fill="x", pady=5)
                
                # Wallet icon
                ctk.CTkLabel(
                    wallet_row,
                    text="👛",
                    font=ctk.CTkFont(size=24),
                ).pack(side="left", padx=15, pady=12)
                
                # Wallet info
                info_frame = ctk.CTkFrame(wallet_row, fg_color="transparent")
                info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=10)
                
                ctk.CTkLabel(
                    info_frame,
                    text=f"Wallet {i + 1}",
                    font=ctk.CTkFont(size=14, weight="bold"),
                ).pack(anchor="w")
                
                ctk.CTkLabel(
                    info_frame,
                    text=f"{address[:12]}...{address[-8:]}",
                    font=ctk.CTkFont(size=12),
                    text_color=self.colors["text_secondary"],
                ).pack(anchor="w")
                
                # Copy button
                ctk.CTkButton(
                    wallet_row,
                    text="📋",
                    width=40,
                    height=35,
                    fg_color=self.colors["bg_hover"],
                    command=lambda a=address: self._copy_to_clipboard(a),
                ).pack(side="right", padx=5, pady=10)
                
                # Remove button
                ctk.CTkButton(
                    wallet_row,
                    text="✕",
                    width=40,
                    height=35,
                    fg_color=self.colors["red"],
                    hover_color="#E63E4D",
                    command=lambda a=address: self._remove_wallet(a),
                ).pack(side="right", padx=5, pady=10)
        
        # Update stat
        if "tracked_wallets" in self.stat_labels:
            self.stat_labels["tracked_wallets"].configure(text=str(len(self.tracked_wallets)))
    
    def _load_tracked_wallets(self):
        """Load tracked wallets from persistent storage."""
        try:
            if self.gui_wallets_file.exists():
                with open(self.gui_wallets_file, "r") as f:
                    data = json.load(f)
                    self.tracked_wallets = data.get("wallets", [])
                    # Refresh the display
                    self._refresh_wallets_list()
                    print(f"Loaded {len(self.tracked_wallets)} tracked wallets from storage")
        except Exception as e:
            print(f"Error loading tracked wallets: {e}")
            self.tracked_wallets = []
    
    def _save_tracked_wallets(self):
        """Save tracked wallets to persistent storage."""
        try:
            with open(self.gui_wallets_file, "w") as f:
                json.dump({
                    "wallets": self.tracked_wallets,
                    "updated_at": datetime.now().isoformat(),
                }, f, indent=2)
            print(f"Saved {len(self.tracked_wallets)} tracked wallets to storage")
        except Exception as e:
            print(f"Error saving tracked wallets: {e}")
    
    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self._show_message("Copied!", "Address copied to clipboard.")
    
    def _new_order_dialog(self):
        """Show new order dialog with full form."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Create Limit Order")
        dialog.geometry("450x500")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=self.colors["bg_dark"])
        
        # Title
        ctk.CTkLabel(
            dialog,
            text="📋 New Limit Order",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(20, 15))
        
        # Form frame
        form_frame = ctk.CTkFrame(dialog, fg_color=self.colors["bg_card"], corner_radius=15)
        form_frame.pack(fill="x", padx=20, pady=10)
        
        # Order type
        ctk.CTkLabel(form_frame, text="Order Type", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(15, 5))
        order_type_var = ctk.StringVar(value="🟢 Limit Buy")
        order_type_menu = ctk.CTkOptionMenu(
            form_frame,
            values=["🟢 Limit Buy", "🔴 Limit Sell", "🛑 Stop Loss", "🎯 Take Profit"],
            variable=order_type_var,
            height=40,
        )
        order_type_menu.pack(fill="x", padx=20, pady=(0, 10))
        
        # Token address
        ctk.CTkLabel(form_frame, text="Token Address", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(10, 5))
        token_entry = ctk.CTkEntry(form_frame, placeholder_text="Enter token address...", height=40)
        token_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # Target price
        ctk.CTkLabel(form_frame, text="Target Price (USD)", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(10, 5))
        price_entry = ctk.CTkEntry(form_frame, placeholder_text="0.0", height=40)
        price_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # Amount
        ctk.CTkLabel(form_frame, text="Amount (SOL)", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(10, 5))
        amount_entry = ctk.CTkEntry(form_frame, placeholder_text="0.1", height=40)
        amount_entry.pack(fill="x", padx=20, pady=(0, 20))
        
        def create_order():
            order_type = order_type_var.get()
            token = token_entry.get()
            price = price_entry.get()
            amount = amount_entry.get()
            
            if not token or not price or not amount:
                self._show_message("Error", "Please fill all fields")
                return
            
            try:
                price_float = float(price)
                amount_float = float(amount)
            except ValueError:
                self._show_message("Error", "Invalid price or amount")
                return
            
            # Create order
            order = {
                "id": len(self.gui_limit_orders) + 1,
                "type": order_type,
                "token": token,
                "price": price_float,
                "amount": amount_float,
                "status": "⏳ Pending",
                "created_at": datetime.now().isoformat(),
            }
            
            self.gui_limit_orders.append(order)
            self._save_gui_orders()
            self._refresh_orders_list()
            
            dialog.destroy()
            self._show_message("✅ Order Created", f"{order_type}\nToken: {token[:16]}...\nPrice: ${price}\nAmount: {amount} SOL")
        
        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkButton(
            btn_frame,
            text="Create Order",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=self.colors["accent"],
            height=45,
            command=create_order,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=ctk.CTkFont(size=15),
            fg_color=self.colors["bg_hover"],
            height=45,
            command=dialog.destroy,
        ).pack(side="left", fill="x", expand=True)
    
    def _refresh_orders_list(self):
        """Refresh the displayed orders list."""
        # Clear current list
        for widget in self.orders_scroll.winfo_children():
            widget.destroy()
        
        if not self.gui_limit_orders:
            # Show empty state
            ctk.CTkLabel(
                self.orders_scroll,
                text="No limit orders\n\nClick '+ New Order' to create one",
                font=ctk.CTkFont(size=14),
                text_color=self.colors["text_secondary"],
            ).pack(pady=50)
        else:
            # Display each order
            for order in self.gui_limit_orders:
                order_row = ctk.CTkFrame(
                    self.orders_scroll,
                    fg_color=self.colors["bg_dark"],
                    corner_radius=10,
                )
                order_row.pack(fill="x", pady=5)
                
                # Order type icon
                type_text = order.get("type", "📋 Order")
                type_icon = type_text.split(" ")[0] if type_text else "📋"
                
                ctk.CTkLabel(
                    order_row,
                    text=type_icon,
                    font=ctk.CTkFont(size=24),
                ).pack(side="left", padx=15, pady=12)
                
                # Order info
                info_frame = ctk.CTkFrame(order_row, fg_color="transparent")
                info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=10)
                
                order_type_clean = " ".join(type_text.split(" ")[1:]) if type_text else "Order"
                ctk.CTkLabel(
                    info_frame,
                    text=f"#{order.get('id', '?')} - {order_type_clean}",
                    font=ctk.CTkFont(size=14, weight="bold"),
                ).pack(anchor="w")
                
                token = order.get("token", "Unknown")
                price = order.get("price", 0)
                amount = order.get("amount", 0)
                ctk.CTkLabel(
                    info_frame,
                    text=f"Token: {token[:12]}... | Price: ${price} | Amount: {amount} SOL",
                    font=ctk.CTkFont(size=11),
                    text_color=self.colors["text_secondary"],
                ).pack(anchor="w")
                
                # Status
                status = order.get("status", "⏳ Pending")
                status_color = self.colors["green"] if "Filled" in status else self.colors["text_secondary"]
                ctk.CTkLabel(
                    order_row,
                    text=status,
                    font=ctk.CTkFont(size=12),
                    text_color=status_color,
                ).pack(side="right", padx=10, pady=10)
                
                # Cancel button
                if "Pending" in status:
                    ctk.CTkButton(
                        order_row,
                        text="✕",
                        width=40,
                        height=35,
                        fg_color=self.colors["red"],
                        hover_color="#E63E4D",
                        command=lambda o=order: self._cancel_order(o),
                    ).pack(side="right", padx=5, pady=10)
        
        # Update dashboard stat
        pending_count = len([o for o in self.gui_limit_orders if "Pending" in o.get("status", "")])
        if "pending_orders" in self.stat_labels:
            self.stat_labels["pending_orders"].configure(text=str(pending_count))
    
    def _cancel_order(self, order: dict):
        """Cancel a limit order."""
        order["status"] = "❌ Cancelled"
        self._save_gui_orders()
        self._refresh_orders_list()
    
    def _load_gui_orders(self):
        """Load GUI orders from persistent storage."""
        orders_file = self.data_dir / "gui_limit_orders.json"
        try:
            if orders_file.exists():
                with open(orders_file, "r") as f:
                    data = json.load(f)
                    self.gui_limit_orders = data.get("orders", [])
                    print(f"Loaded {len(self.gui_limit_orders)} limit orders from storage")
        except Exception as e:
            print(f"Error loading orders: {e}")
            self.gui_limit_orders = []
    
    def _save_gui_orders(self):
        """Save GUI orders to persistent storage."""
        orders_file = self.data_dir / "gui_limit_orders.json"
        try:
            with open(orders_file, "w") as f:
                json.dump({
                    "orders": self.gui_limit_orders,
                    "updated_at": datetime.now().isoformat(),
                }, f, indent=2)
            print(f"Saved {len(self.gui_limit_orders)} limit orders to storage")
        except Exception as e:
            print(f"Error saving orders: {e}")
    
    def _show_message(self, title: str, message: str):
        """Show a message dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("400x150")
        dialog.transient(self)
        dialog.grab_set()
        
        ctk.CTkLabel(
            dialog,
            text=message,
            font=ctk.CTkFont(size=14),
            wraplength=350,
        ).pack(expand=True, padx=20, pady=20)
        
        ctk.CTkButton(
            dialog,
            text="OK",
            command=dialog.destroy,
        ).pack(pady=(0, 20))
    
    def _start_refresh(self):
        """Start the refresh loop."""
        self._refresh_data()
        self.after(10000, self._start_refresh)  # Refresh every 10 seconds
    
    def _refresh_data(self):
        """Refresh dashboard data."""
        # Update wallet info
        if self.wallet:
            short_addr = f"{self.wallet.address[:4]}...{self.wallet.address[-4:]}"
            self.wallet_label.configure(text=short_addr)
        
        # Update balance
        self.balance_label.configure(text=f"{self.sol_balance:.4f} SOL")
        
        # Update portfolio value
        value = self.sol_balance * self.sol_price
        if "portfolio_value" in self.stat_labels:
            self.stat_labels["portfolio_value"].configure(text=f"${value:.2f}")
        
        # Update network
        if self.settings:
            network = self.settings.network
            emoji = "🟢" if network == "mainnet" else "🟡"
            self.network_label.configure(text=f"{emoji} {network.capitalize()}")
            self.network_var.set(network)
    
    def update_balance(self, balance: float):
        """Update SOL balance."""
        self.sol_balance = balance
        self._refresh_data()
    
    def update_sol_price(self, price: float):
        """Update SOL price."""
        self.sol_price = price
        self._refresh_data()


def run_dashboard(settings=None, **kwargs):
    """Run the trading dashboard."""
    app = TradingDashboard(settings=settings, **kwargs)
    app.mainloop()


if __name__ == "__main__":
    run_dashboard()
