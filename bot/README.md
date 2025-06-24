# 🤖 Telegram Trading Bot

An automated cryptocurrency trading bot that monitors Telegram channels for Binance futures listing announcements and executes trades automatically.

## 📋 Table of Contents

- [Features](#-features)
- [How It Works](#-how-it-works)
- [Setup](#-setup)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [File Structure](#-file-structure)
- [Trading Strategy](#-trading-strategy)
- [Monitoring & Notifications](#-monitoring--notifications)
- [Risk Management](#-risk-management)
- [Troubleshooting](#-troubleshooting)

## ✨ Features

### 🎯 **Smart Symbol Extraction**
- Monitors Telegram channels for Binance futures listing messages
- Extracts coin symbols using advanced regex patterns
- Handles multiple coins in one message (uses first coin only)
- Validates symbols before trading

### 🔄 **Single Trade Management**
- Only one active trade at a time
- Ignores new trades when one is already active
- No retry attempts for ignored trades

### ⏰ **Intelligent Trade Monitoring**
- **10-minute status checks**: Monitors if target/stop loss was hit
- **2-hour maximum hold time**: Automatically closes positions
- **Real-time position tracking**: Updates trade status automatically

### 📊 **Comprehensive Logging**
- All trades logged to `trades.json`
- Entry and exit details with timestamps
- P&L calculations and performance metrics
- Trade status tracking (ACTIVE → CLOSED)

### 🔔 **Slack Notifications**
- Real-time trade notifications
- Error alerts and system status
- Trade completion updates
- Retry attempt notifications

## 🔧 How It Works

### 1. **Message Detection**
```
Telegram Message: "$TAIKO, $SQD listed on Binance futures"
↓
Bot detects: "binance" + "futures" keywords
↓
Extracts: "TAIKO" (first symbol only)
↓
Creates trading pair: "TAIKOUSDT"
```

### 2. **Active Trade Check**
```
Before executing new trade:
↓
Check trades.json for status: "ACTIVE"
↓
If ACTIVE trade exists: Ignore new trade
If NO active trade: Proceed with execution
```

### 3. **Trade Execution**
```
Place Market Buy Order
↓
Set Stop Loss (-2%)
↓
Set Take Profit (+15%)
↓
Log trade with status: "ACTIVE"
↓
Start monitoring
```

### 4. **Trade Monitoring**
```
Every 10 minutes:
↓
Check Binance position
↓
If position = 0: Update status to "CLOSED"
If position > 0: Continue monitoring
↓
After 2 hours: Force close at market price
```

## 🚀 Setup

### Prerequisites
- Python 3.8+
- Telegram API credentials
- Binance Futures API keys
- Slack webhook URL (optional)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd telegram_listing/bot
```

2. **Install dependencies**
```bash
pip install -r requirements_telegram.txt
```

3. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials
```

## ⚙️ Configuration

### Environment Variables (`.env`)

```bash
# Telegram API (get from https://my.telegram.org)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE_NUMBER=+1234567890
TELEGRAM_CHANNEL_USERNAME=@your_channel

# Binance API (get from Binance Futures)
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_secret_key

# Trading Parameters
TRADE_AMOUNT=100.0          # Amount per trade ($)
PROFIT_TARGET_PCT=15.0      # Profit target (%)
STOP_LOSS_PCT=2.0          # Stop loss (%)
LEVERAGE=1                 # Leverage multiplier
MAX_RETRY_MINUTES=1440     # Retry limit (minutes)

# Slack Notifications
SLACK_WEBHOOK_URL=your_webhook_url

# New TIMING_MODE variable
TIMING_MODE=1              # Trade execution timing (1 or 10)
```

### Trading Parameters Explained

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `TRADE_AMOUNT` | USD amount per trade | 100.0 | $100 per trade |
| `PROFIT_TARGET_PCT` | Take profit percentage | 15.0 | +15% target |
| `STOP_LOSS_PCT` | Stop loss percentage | 2.0 | -2% stop loss |
| `LEVERAGE` | Futures leverage | 1 | 1x leverage |
| `MAX_RETRY_MINUTES` | Retry failed trades for X minutes | 1440 | 24 hours |
| `TIMING_MODE` | Trade execution timing (1 or 10) | 1 | 1=every minute, 10=every 10 minutes |

## 🎮 Usage

### Start the Bot
```bash
python telegram_listen.py
```

### Expected Output
```
📱 Telegram Listener Starting...
Press Ctrl+C to stop
2024-01-15 10:30:00 - INFO - TelegramListener initialized
2024-01-15 10:30:00 - INFO - Monitoring channel: @test_binance_list
2024-01-15 10:30:01 - INFO - Telegram client started successfully
2024-01-15 10:30:01 - INFO - Binance connection successful
2024-01-15 10:30:01 - INFO - Message handler registered. Listening for messages...
```

### Stop the Bot
```bash
Ctrl+C
```

## 📁 File Structure

```
bot/
├── README.md              # This file
├── telegram_listen.py     # Main bot script
├── bot.py                # Trading logic
├── slack_notifier.py     # Slack notifications
├── .env                  # Environment variables
├── trades.json           # Trade log (auto-created)
├── telegram_trading.log  # Application logs
└── trading_session.session # Telegram session (auto-created)
```

## 📈 Trading Strategy

### Entry Conditions
- Message contains "binance" AND "futures"
- Valid symbol extracted from message
- No active trades currently running
- Symbol exists on Binance Futures

### Trade Execution Flow
1. **Message Received** → Symbol extracted → **Wait 2 seconds** → Attempt trade execution
2. **If trade succeeds** → Stop loss & take profit placed → Trade complete
3. **If trade fails** → Queue for next timing window retry

### Timing Windows (for failed trades only)
- **TIMING_MODE=1**: Retries failed trades every minute at :02 seconds
- **TIMING_MODE=10**: Retries failed trades every 10 minutes at :02 seconds (00:02, 10:02, 20:02, etc.)
- Only failed trades use the timing queue system

### Position Management
- **Entry**: Market buy order (executed at timed intervals)
- **Stop Loss**: -2% from entry price (placed immediately after entry)
- **Take Profit**: +15% from entry price (placed immediately after entry)
- **Max Hold**: 2 hours maximum

### Exit Conditions
1. **Take Profit Hit**: +15% target reached
2. **Stop Loss Hit**: -2% loss limit reached
3. **Max Hold Time**: 2 hours elapsed → Market close
4. **Manual Stop**: Bot shutdown

## 🔔 Monitoring & Notifications

### Slack Notifications

The bot now sends **minimal notifications** to reduce noise:

#### 1. Symbol Extraction (when message received)
```
🎯 SYMBOL EXTRACTED: ✅ EXECUTING IN 2 SECONDS
Time: 2024-01-15 10:35:00
Symbol: TAIKO
Trading Pair: TAIKOUSDT
Original Message: $TAIKO listed on Binance futures
Status: Will attempt execution in 2 seconds, queue if failed
```

#### 2. Trade Execution (when trade is actually placed)
```
🎯 TRADE EXECUTED: ✅ SUCCESS
Time: 2024-01-15 10:35:02
Symbol: TAIKOUSDT
Entry Price: $0.1234
Quantity: 1215.0
Stop Loss: $0.1209 (-2%)
Take Profit: $0.1419 (+15%)
Leverage: 1x
Trade Amount: $100.0
Max Hold Time: 2 hours
Original Message: $TAIKO listed on Binance futures
```

#### Trade Ignored
```
⚠️ TRADE IGNORED: 🔄 ACTIVE TRADE EXISTS
Time: 2024-01-15 10:40:00
Symbol: SQD
Trading Pair: SQDUSTDT
Reason: Another trade is currently active
Action: Message ignored - no retry
Original Message: $SQD listed on Binance futures
```

#### Status Update
```
📊 TRADE STATUS UPDATE: ✅ CLOSED
Time: 2024-01-15 11:15:00
Symbol: TAIKOUSDT
Previous Status: ACTIVE
New Status: CLOSED
Reason: TARGET_OR_STOPLOSS_HIT
```

### Log Files

#### `trades.json` Structure
```json
[
  {
    "trade_id": "TAIKOUSDT_1705312500",
    "symbol": "TAIKOUSDT",
    "action": "BUY",
    "entry_time": "2024-01-15T10:35:00",
    "entry_price": 0.1234,
    "quantity": 1215.0,
    "stop_loss_price": 0.1209,
    "take_profit_price": 0.1419,
    "leverage": 1,
    "trade_amount": 100.0,
    "original_message": "$TAIKO listed on Binance futures",
    "status": "ACTIVE",
    "max_hold_until": "2024-01-15T12:35:00"
  }
]
```

## ⚠️ Risk Management

### Built-in Safety Features

1. **Single Trade Limit**: Only one active trade at a time
2. **Stop Loss Protection**: Automatic -2% stop loss
3. **Time Limit**: Maximum 2-hour hold time
4. **Balance Check**: Uses only available balance
5. **Symbol Validation**: Verifies symbol exists before trading

### Risk Considerations

- **Market Risk**: Crypto markets are highly volatile
- **Execution Risk**: Orders may not fill at expected prices
- **Technical Risk**: Bot may miss signals due to connectivity issues
- **Leverage Risk**: Even 1x leverage amplifies losses

### Recommended Settings

| Risk Level | Trade Amount | Stop Loss | Leverage |
|------------|--------------|-----------|----------|
| **Conservative** | $50-100 | 1-2% | 1x |
| **Moderate** | $100-500 | 2-3% | 1-2x |
| **Aggressive** | $500+ | 3-5% | 2-3x |

## 🔧 Troubleshooting

### Common Issues

#### Bot Not Starting
```bash
# Check Python version
python --version  # Should be 3.8+

# Install dependencies
pip install -r requirements_telegram.txt

# Check .env file
cat .env  # Verify all variables are set
```

#### No Trades Executing
1. **Check Telegram Connection**
   - Verify API credentials
   - Confirm channel username is correct
   - Check if bot has access to channel

2. **Check Binance Connection**
   - Verify API keys are correct
   - Ensure Futures trading is enabled
   - Check account balance

3. **Check Message Format**
   - Message must contain "binance" AND "futures"
   - Symbol must match regex patterns
   - No active trades should exist

#### Trades Not Closing
1. **Check Position Status**
   - Verify position exists on Binance
   - Check if orders were filled
   - Review error logs

2. **Check Monitoring**
   - Ensure bot is running continuously
   - Check 10-minute status updates
   - Verify 2-hour max hold logic

### Debug Mode

Enable detailed logging:
```python
# In telegram_listen.py, change:
logging.basicConfig(level=logging.DEBUG)
```

### Support

For issues and questions:
1. Check the logs: `telegram_trading.log`
2. Review trade history: `trades.json`
3. Check Slack notifications for errors
4. Verify Binance account status

## 📊 Performance Tracking

The bot automatically tracks:
- **Win Rate**: Percentage of profitable trades
- **Average Hold Time**: Time from entry to exit
- **P&L**: Profit and loss per trade
- **Success Rate**: Percentage of successful executions

All data is stored in `trades.json` for analysis.

---

## ⚡ Quick Start Checklist

- [ ] Python 3.8+ installed
- [ ] Dependencies installed (`pip install -r requirements_telegram.txt`)
- [ ] `.env` file configured with all credentials
- [ ] Telegram API access granted
- [ ] Binance Futures API enabled
- [ ] Slack webhook configured (optional)
- [ ] Test with small trade amount first
- [ ] Monitor logs and notifications

**Ready to trade!** 🚀

```bash
python telegram_listen.py
``` 