# Solana Trading Bot

A production-ready Solana trading bot with Telegram integration, copy trading, and smart wallet tracking.

## Features

### Core Trading
- **DEX Trading via Jupiter**: Execute swaps through Jupiter aggregator for optimal routing
- **MEV Protection**: Jupiter Ultra API provides built-in MEV protection
- **Slippage Control**: Configurable slippage with real-time estimation
- **Fast Execution**: Sub-second transaction landing

### Telegram Interface
- **Trade Commands**: Buy/sell tokens directly from Telegram
- **Real-time Alerts**: Notifications for trades, errors, and wallet activity
- **Balance Checking**: View wallet balances and portfolio
- **Status Dashboard**: Monitor bot health and statistics

### Copy Trading
- **Wallet Tracking**: Monitor any Solana wallet in real-time
- **Automatic Copying**: Mirror trades from tracked wallets
- **Configurable Filters**: Token whitelist/blacklist, size limits, direction filters
- **Adjustable Sizing**: Fixed amount, percentage, or proportional copying

### Wallet Tracking
- **Real-time Monitoring**: Detect DEX swaps as they happen
- **Multi-wallet Support**: Track multiple wallets simultaneously
- **PnL Tracking**: Calculate realized/unrealized gains for monitored wallets
- **Activity History**: Review recent trading activity

## Architecture

```
src/
├── main.py                    # Application entry point
├── config/
│   ├── settings.py           # Configuration management
│   └── logging_config.py     # Logging setup
├── blockchain/
│   ├── client.py             # Solana RPC client
│   ├── wallet.py             # Wallet/keypair management
│   └── transaction.py        # Transaction parsing
├── trading/
│   ├── jupiter.py            # Jupiter Ultra API client
│   ├── executor.py           # Trade execution engine
│   └── models.py             # Trade data models
├── tracking/
│   ├── wallet_tracker.py     # Wallet monitoring
│   ├── copy_trader.py        # Copy trading logic
│   └── pnl_tracker.py        # PnL calculation
└── telegram/
    ├── bot.py                # Telegram bot handler
    ├── commands.py           # Command handlers
    └── notifications.py      # Alert system
```

## Prerequisites

- Python 3.10+
- Solana wallet with SOL for trading and fees
- Telegram Bot token from [@BotFather](https://t.me/BotFather)
- Jupiter API key from [portal.jup.ag](https://portal.jup.ag)

## Installation

1. **Clone the repository**
   ```bash
   cd "Solana Trading Bot"
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

5. **Configure bot settings**
   ```bash
   cp config/config.example.yaml config/config.yaml
   # Edit config/config.yaml as needed
   ```

## Configuration

### Environment Variables (.env)

| Variable | Description | Required |
|----------|-------------|----------|
| `SOLANA_PRIVATE_KEY` | Base58 encoded private key | Yes |
| `SOLANA_RPC_URL` | Solana RPC endpoint | Yes |
| `SOLANA_WS_URL` | Solana WebSocket endpoint | Yes |
| `JUPITER_API_KEY` | Jupiter API key | Yes |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Yes |
| `TELEGRAM_ADMIN_ID` | Your Telegram user ID | Yes |
| `NETWORK` | Network: mainnet/devnet/testnet | No |
| `DEBUG` | Enable debug logging | No |

### Configuration File (config/config.yaml)

See `config/config.example.yaml` for all available options including:
- Trading settings (slippage, default amounts)
- Copy trading configuration
- Wallet tracking settings
- Risk management rules
- Telegram notification preferences

## Usage

### Start the Bot

```bash
python src/main.py
```

### Telegram Commands

**Trading:**
- `/balance` - Show wallet balance
- `/buy <token> <sol_amount>` - Buy token with SOL
- `/sell <token> <amount>` - Sell token for SOL

**Tracking:**
- `/wallets` - List tracked wallets
- `/track <address> [name]` - Add wallet to track
- `/untrack <address>` - Remove tracked wallet

**Copy Trading:**
- `/copy status` - View copy trading status
- `/copy enable` - Enable copy trading
- `/copy disable` - Disable copy trading

**Reports:**
- `/pnl [address]` - Show PnL report
- `/status` - Show bot status
- `/settings` - View current settings

## RPC Recommendations

For production use, we recommend premium RPC providers:
- [Helius](https://helius.dev) - Fast, reliable, Solana-focused
- [QuickNode](https://quicknode.com) - Multi-chain, good uptime
- [Chainstack](https://chainstack.com) - Enterprise-grade

The free public RPC (`https://api.mainnet-beta.solana.com`) has rate limits and may be slow during high-traffic periods.

## Security Considerations

1. **Private Keys**: Never commit your `.env` file. The private key gives full access to your wallet.

2. **API Keys**: Keep your Jupiter API key private.

3. **Telegram Admin**: Only the configured admin ID can execute commands.

4. **Risk Management**: Configure appropriate limits in `config.yaml`:
   - Daily loss limits
   - Maximum position sizes
   - Trade confirmation thresholds

## Disclaimer

This software is provided "as is" without warranty. Trading cryptocurrencies involves substantial risk of loss. The authors are not responsible for any financial losses. Always:
- Test on devnet first
- Start with small amounts
- Monitor the bot regularly
- Understand the risks involved

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Support

For issues and questions:
- Open a GitHub issue
- Check existing issues for solutions
