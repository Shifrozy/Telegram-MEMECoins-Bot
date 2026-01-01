"""
Token Information Service

Fetches comprehensive token data from multiple sources:
- Jupiter API for price and token metadata
- DexScreener for charts and trading data
- Solscan for holder information
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx

from src.config.logging_config import get_logger

logger = get_logger(__name__)

# Known token addresses
KNOWN_TOKENS = {
    "So11111111111111111111111111111111111111112": {
        "symbol": "SOL",
        "name": "Solana",
        "decimals": 9,
    },
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {
        "symbol": "USDC",
        "name": "USD Coin",
        "decimals": 6,
    },
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": {
        "symbol": "USDT",
        "name": "Tether USD",
        "decimals": 6,
    },
}

SOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass
class TokenInfo:
    """Comprehensive token information."""
    # Basic info
    address: str
    symbol: str
    name: str
    decimals: int
    
    # Price data
    price_usd: float = 0.0
    price_sol: float = 0.0
    price_change_24h: float = 0.0
    
    # Market data
    market_cap: float = 0.0
    fdv: float = 0.0  # Fully diluted valuation
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    
    # Supply info
    total_supply: float = 0.0
    circulating_supply: float = 0.0
    
    # Holder info
    holder_count: int = 0
    top_holders_percentage: float = 0.0
    
    # Trading info
    buy_count_24h: int = 0
    sell_count_24h: int = 0
    unique_traders_24h: int = 0
    
    # Safety info
    is_verified: bool = False
    is_frozen: bool = False
    has_mint_authority: bool = True
    has_freeze_authority: bool = True
    
    # Timestamps
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    
    # Links
    website: Optional[str] = None
    twitter: Optional[str] = None
    telegram: Optional[str] = None
    
    @property
    def market_cap_formatted(self) -> str:
        """Format market cap for display."""
        if self.market_cap >= 1_000_000_000:
            return f"${self.market_cap / 1_000_000_000:.2f}B"
        elif self.market_cap >= 1_000_000:
            return f"${self.market_cap / 1_000_000:.2f}M"
        elif self.market_cap >= 1_000:
            return f"${self.market_cap / 1_000:.2f}K"
        else:
            return f"${self.market_cap:.2f}"
    
    @property
    def liquidity_formatted(self) -> str:
        """Format liquidity for display."""
        if self.liquidity_usd >= 1_000_000:
            return f"${self.liquidity_usd / 1_000_000:.2f}M"
        elif self.liquidity_usd >= 1_000:
            return f"${self.liquidity_usd / 1_000:.2f}K"
        else:
            return f"${self.liquidity_usd:.2f}"
    
    @property
    def volume_formatted(self) -> str:
        """Format 24h volume for display."""
        if self.volume_24h >= 1_000_000:
            return f"${self.volume_24h / 1_000_000:.2f}M"
        elif self.volume_24h >= 1_000:
            return f"${self.volume_24h / 1_000:.2f}K"
        else:
            return f"${self.volume_24h:.2f}"
    
    @property
    def safety_score(self) -> str:
        """Calculate safety score."""
        score = 0
        max_score = 5
        
        if self.is_verified:
            score += 1
        if not self.has_mint_authority:
            score += 1
        if not self.has_freeze_authority:
            score += 1
        if self.holder_count > 100:
            score += 1
        if self.liquidity_usd > 10000:
            score += 1
        
        if score >= 4:
            return "🟢 Safe"
        elif score >= 2:
            return "🟡 Caution"
        else:
            return "🔴 Risky"
    
    @property
    def price_formatted(self) -> str:
        """Format price for display."""
        if self.price_usd >= 1:
            return f"${self.price_usd:.4f}"
        elif self.price_usd >= 0.0001:
            return f"${self.price_usd:.6f}"
        else:
            return f"${self.price_usd:.10f}"


class TokenInfoService:
    """
    Service for fetching comprehensive token information.
    
    Uses multiple data sources for accuracy:
    - Jupiter API for price and token metadata
    - DexScreener for trading data
    - Birdeye for market data
    """
    
    def __init__(self, timeout: int = 15):
        """Initialize token info service."""
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, TokenInfo] = {}
        self._cache_ttl = 30  # 30 seconds cache
        self._cache_times: Dict[str, datetime] = {}
        
        # API endpoints
        self.jupiter_price_url = "https://api.jup.ag/price/v2"
        self.jupiter_token_url = "https://tokens.jup.ag/token"
        self.dexscreener_url = "https://api.dexscreener.com/latest/dex/tokens"
        self.birdeye_url = "https://public-api.birdeye.so/defi"
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def get_token_info(
        self,
        address: str,
        force_refresh: bool = False,
    ) -> Optional[TokenInfo]:
        """
        Get comprehensive token information.
        
        Args:
            address: Token mint address
            force_refresh: Bypass cache
            
        Returns:
            TokenInfo or None if not found
        """
        # Check cache
        if not force_refresh and address in self._cache:
            cache_time = self._cache_times.get(address)
            if cache_time and (datetime.now() - cache_time).seconds < self._cache_ttl:
                return self._cache[address]
        
        logger.info("fetching_token_info", address=address[:8])
        
        try:
            # Fetch from multiple sources in parallel
            jupiter_task = self._fetch_jupiter_data(address)
            dexscreener_task = self._fetch_dexscreener_data(address)
            
            jupiter_data, dexscreener_data = await asyncio.gather(
                jupiter_task,
                dexscreener_task,
                return_exceptions=True,
            )
            
            # Handle exceptions
            if isinstance(jupiter_data, Exception):
                logger.debug("jupiter_fetch_error", error=str(jupiter_data))
                jupiter_data = None
            if isinstance(dexscreener_data, Exception):
                logger.debug("dexscreener_fetch_error", error=str(dexscreener_data))
                dexscreener_data = None
            
            # Build token info from available data
            token_info = self._build_token_info(address, jupiter_data, dexscreener_data)
            
            if token_info:
                # Cache result
                self._cache[address] = token_info
                self._cache_times[address] = datetime.now()
                
                logger.info(
                    "token_info_fetched",
                    symbol=token_info.symbol,
                    price=token_info.price_usd,
                )
            
            return token_info
            
        except Exception as e:
            logger.error("token_info_error", address=address[:8], error=str(e))
            return None
    
    async def _fetch_jupiter_data(self, address: str) -> Optional[Dict]:
        """Fetch token data from Jupiter API."""
        client = await self._get_client()
        
        result = {}
        
        try:
            # Get price
            price_resp = await client.get(
                self.jupiter_price_url,
                params={"ids": address, "showExtraInfo": "true"},
            )
            if price_resp.status_code == 200:
                price_data = price_resp.json()
                if "data" in price_data and address in price_data["data"]:
                    result["price"] = price_data["data"][address]
        except Exception as e:
            logger.debug("jupiter_price_error", error=str(e))
        
        try:
            # Get token metadata
            token_resp = await client.get(f"{self.jupiter_token_url}/{address}")
            if token_resp.status_code == 200:
                result["token"] = token_resp.json()
        except Exception as e:
            logger.debug("jupiter_token_error", error=str(e))
        
        return result if result else None
    
    async def _fetch_dexscreener_data(self, address: str) -> Optional[Dict]:
        """Fetch token data from DexScreener API."""
        client = await self._get_client()
        
        try:
            resp = await client.get(f"{self.dexscreener_url}/{address}")
            if resp.status_code == 200:
                data = resp.json()
                if "pairs" in data and data["pairs"]:
                    # Return the pair with highest liquidity
                    pairs = sorted(
                        data["pairs"],
                        key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
                        reverse=True,
                    )
                    return pairs[0] if pairs else None
        except Exception as e:
            logger.debug("dexscreener_error", error=str(e))
        
        return None
    
    def _build_token_info(
        self,
        address: str,
        jupiter_data: Optional[Dict],
        dexscreener_data: Optional[Dict],
    ) -> Optional[TokenInfo]:
        """Build TokenInfo from fetched data."""
        
        # Check known tokens first
        if address in KNOWN_TOKENS:
            known = KNOWN_TOKENS[address]
            info = TokenInfo(
                address=address,
                symbol=known["symbol"],
                name=known["name"],
                decimals=known["decimals"],
            )
        else:
            # Default values
            info = TokenInfo(
                address=address,
                symbol="???",
                name="Unknown Token",
                decimals=9,
            )
        
        # Extract from Jupiter data
        if jupiter_data:
            token = jupiter_data.get("token", {})
            price = jupiter_data.get("price", {})
            
            if token:
                info.symbol = token.get("symbol", info.symbol)
                info.name = token.get("name", info.name)
                info.decimals = token.get("decimals", info.decimals)
            
            if price:
                info.price_usd = float(price.get("price", 0) or 0)
                
                extra = price.get("extraInfo", {})
                if extra:
                    info.volume_24h = float(extra.get("lastSwappedPrice", {}).get("lastJupiterSellPrice", 0) or 0)
        
        # Extract from DexScreener data
        if dexscreener_data:
            base_token = dexscreener_data.get("baseToken", {})
            
            if base_token:
                info.symbol = base_token.get("symbol", info.symbol)
                info.name = base_token.get("name", info.name)
            
            # Price
            info.price_usd = float(dexscreener_data.get("priceUsd", 0) or 0)
            info.price_sol = float(dexscreener_data.get("priceNative", 0) or 0)
            
            # Price change
            price_change = dexscreener_data.get("priceChange", {})
            info.price_change_24h = float(price_change.get("h24", 0) or 0)
            
            # Market data
            info.market_cap = float(dexscreener_data.get("marketCap", 0) or 0)
            info.fdv = float(dexscreener_data.get("fdv", 0) or 0)
            
            liquidity = dexscreener_data.get("liquidity", {})
            info.liquidity_usd = float(liquidity.get("usd", 0) or 0)
            
            volume = dexscreener_data.get("volume", {})
            info.volume_24h = float(volume.get("h24", 0) or 0)
            
            # Trading activity
            txns = dexscreener_data.get("txns", {}).get("h24", {})
            info.buy_count_24h = int(txns.get("buys", 0) or 0)
            info.sell_count_24h = int(txns.get("sells", 0) or 0)
            
            # Socials
            info_data = dexscreener_data.get("info", {})
            if info_data:
                socials = info_data.get("socials", [])
                for social in socials:
                    if social.get("type") == "twitter":
                        info.twitter = social.get("url")
                    elif social.get("type") == "telegram":
                        info.telegram = social.get("url")
                
                websites = info_data.get("websites", [])
                if websites:
                    info.website = websites[0].get("url")
        
        # Only return if we have at least basic info
        if info.symbol != "???" or info.price_usd > 0:
            info.last_updated = datetime.now()
            return info
        
        return None
    
    async def get_sol_price(self) -> float:
        """Get current SOL price in USD."""
        info = await self.get_token_info(SOL_MINT)
        return info.price_usd if info else 0.0
    
    async def search_token(self, query: str) -> List[TokenInfo]:
        """
        Search for tokens by symbol or name.
        
        Args:
            query: Search query (symbol or name)
            
        Returns:
            List of matching tokens
        """
        client = await self._get_client()
        
        try:
            # Search via Jupiter
            resp = await client.get(
                "https://tokens.jup.ag/tokens",
                params={"tags": "verified"},
            )
            
            if resp.status_code != 200:
                return []
            
            tokens = resp.json()
            query_lower = query.lower()
            
            matches = []
            for token in tokens:
                symbol = token.get("symbol", "").lower()
                name = token.get("name", "").lower()
                
                if query_lower in symbol or query_lower in name:
                    info = TokenInfo(
                        address=token.get("address", ""),
                        symbol=token.get("symbol", ""),
                        name=token.get("name", ""),
                        decimals=token.get("decimals", 9),
                    )
                    matches.append(info)
                    
                    if len(matches) >= 10:
                        break
            
            return matches
            
        except Exception as e:
            logger.error("token_search_error", error=str(e))
            return []
    
    def format_token_message(self, info: TokenInfo) -> str:
        """Format token info as a Telegram message."""
        
        # Price change emoji
        if info.price_change_24h > 0:
            change_emoji = "🟢"
            change_sign = "+"
        elif info.price_change_24h < 0:
            change_emoji = "🔴"
            change_sign = ""
        else:
            change_emoji = "⚪"
            change_sign = ""
        
        # Buy/sell ratio
        total_txns = info.buy_count_24h + info.sell_count_24h
        if total_txns > 0:
            buy_ratio = (info.buy_count_24h / total_txns) * 100
            if buy_ratio > 60:
                sentiment = "🟢 Bullish"
            elif buy_ratio < 40:
                sentiment = "🔴 Bearish"
            else:
                sentiment = "⚪ Neutral"
        else:
            sentiment = "N/A"
            buy_ratio = 50
        
        message = f"""
🪙 **{info.symbol}** - {info.name}

**Price:**
• USD: {info.price_formatted}
• SOL: {info.price_sol:.8f}
• {change_emoji} 24h: {change_sign}{info.price_change_24h:.2f}%

**Market:**
• Market Cap: {info.market_cap_formatted}
• Liquidity: {info.liquidity_formatted}
• 24h Volume: {info.volume_formatted}

**Trading (24h):**
• Buys: 🟢 {info.buy_count_24h:,}
• Sells: 🔴 {info.sell_count_24h:,}
• Sentiment: {sentiment}

**Safety:** {info.safety_score}

━━━━━━━━━━━━━━━━━━━━
📋 `{info.address}`

🔗 [DexScreener](https://dexscreener.com/solana/{info.address}) | [Birdeye](https://birdeye.so/token/{info.address}) | [Solscan](https://solscan.io/token/{info.address})
"""
        
        return message.strip()
