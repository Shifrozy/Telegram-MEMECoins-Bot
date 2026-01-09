---
description: How to run and use the Solana Trading Bot
---

# Solana Trading Bot - Quick Start

## Running the Bot

// turbo-all

```bash
cd "d:\PROJECTS\New Projects\Solana Trading Bot"
python src/main.py
```

## Telegram Commands

### Trading
- `/buy <token>` - Buy token with default amount
- `/buy <token> <amount>` - Buy with specific SOL amount
- `/sell <token>` - Sell token (100%)
- `/sell <token> 50` - Sell 50%

### Position Management
- `/positions` - View all open positions with TP/SL
- Use inline buttons to update TP/SL or close positions

### Settings
- `/tp <percent>` - Set Take Profit (e.g., `/tp 75`)
- `/sl <percent>` - Set Stop Loss (e.g., `/sl 20`)
- `/amount <sol>` - Set default buy amount (e.g., `/amount 0.5`)
- `/settings` - View and update all settings via buttons
- `/slippage <bps>` - Set slippage (e.g., `/slippage 300` for 3%)

### Copy Trading
- `/copy` - View copy trading status
- `/copy enable` - Enable copy trading
- `/copy disable` - Disable copy trading
- `/track <address> <name>` - Track a wallet
- `/untrack <address>` - Stop tracking
- `/wallets` - List tracked wallets

### Other
- `/start` - Main menu
- `/help` - Command list
- `/balance` - Wallet balance
- `/status` - Bot status
- `/token <address>` - Get token info
- `/pnl` - View PnL summary

## Quick Trading

1. Just paste a token address in chat
2. Bot shows token info + buy options
3. Click amount button to buy
4. Position auto-tracked with TP/SL

## Configuration

Edit `.env` file:
```
SOLANA_RPC_URL=https://your-rpc-url
SOLANA_PRIVATE_KEY=your-private-key
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_ID=your-telegram-id
JUPITER_API_KEY=your-jupiter-api-key
```

Edit `config/config.yaml` for advanced settings.
