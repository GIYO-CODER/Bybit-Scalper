# Bybit Perpetual Scalping Bot

High-frequency EMA-cross + RSI + ATR scalping bot for Bybit USDT perpetual futures.

## File Structure

```
bybit_scalper/
├── main.py                  ← Run this
├── config.py                ← All settings (edit this first)
├── requirements.txt
├── core/
│   └── exchange.py          ← Bybit V5 API client
├── strategies/
│   └── scalper.py           ← Entry/exit logic
├── utils/
│   ├── indicators.py        ← EMA, RSI, ATR, Volume
│   ├── risk.py              ← Sizing, spread, loss guard
│   └── logger.py            ← Rotating log setup
└── logs/
    └── scalper.log          ← Auto-created on first run
```

## Setup

### 1. Install dependencies

```bash
pip install pybit colorama
```

### 2. Create Bybit API keys

- Go to Bybit → Account → API Management
- Create key with **Read + Trade** permissions (no Withdraw)
- Enable IP whitelist for your server IP

### 3. Set credentials

```bash
export BYBIT_API_KEY="your_key_here"
export BYBIT_API_SECRET="your_secret_here"
```

Or edit `config.py` directly (not recommended for production).

### 4. Start on testnet first

Ensure `TESTNET = True` in `config.py`, then:

```bash
cd bybit_scalper
python main.py
```

Watch for at least 1 hour on testnet before going live.

### 5. Go live

Set `TESTNET = False` in `config.py`. Start small.

---

## Strategy Logic

```
Every tick (every POLL_INTERVAL_S seconds) per symbol:

1. Fetch last 100 × 1m candles
2. Compute:
   - EMA(8) and EMA(21) → crossover direction
   - RSI(7) → momentum filter
   - ATR(7) → dynamic SL/TP distances
   - Volume vs 20-bar average → liquidity filter
3. Long signal  : EMA8 crosses above EMA21 + RSI not overbought + volume surge
   Short signal : EMA8 crosses below EMA21 + RSI not oversold  + volume surge
4. Risk:reward must be ≥ 1.3
5. Place Market order with exchange-native SL and TP
6. Once in profit → trailing stop activates
7. Daily loss limit → bot halts if breached
```

---

## Key Config Parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `LEVERAGE` | 5 | Higher = more size, more risk |
| `USDT_PER_TRADE` | 50 | Notional USDT per trade |
| `MAX_OPEN_TRADES` | 3 | Max concurrent positions |
| `DAILY_LOSS_LIMIT` | 100 | Hard stop in USDT |
| `ATR_SL_MULT` | 1.2 | Tighter = more trades, more whipsaws |
| `ATR_TP_MULT` | 1.8 | Higher = bigger wins, fewer closes |
| `VOLUME_FILTER_MULT` | 1.3 | Raise to 1.5+ in choppy markets |
| `POLL_INTERVAL_S` | 3 | Lower = more reactive, more API calls |

---

## Tuning Tips for High Turnover

- **Reduce `POLL_INTERVAL_S` to 1–2** for near real-time reaction
- **Add more symbols** (e.g. XRPUSDT, DOGEUSDT, LINKUSDT) to increase trade frequency
- **Lower `ATR_TP_MULT` to 1.2–1.4** for quicker profit-taking
- **Raise `VOLUME_FILTER_MULT` to 1.5** during ranging markets to reduce losses
- **Use `ORDER_TYPE = "Limit"`** to pay maker fees (significantly cheaper on Bybit)

---

## Risk Warnings

- **Leveraged futures can lose more than your margin** if SL slippage occurs
- This bot does NOT guarantee profit — it is a framework, not a money machine
- Backtest on historical data before using real capital
- Never trade more than you can afford to lose
- Monitor the bot actively, especially for the first 24 hours live

---

## Stopping the Bot

```
Ctrl+C
```

The bot prints a session summary on exit. All open positions are left open (not force-closed on shutdown — manage them manually or set exchange-level SLs).
