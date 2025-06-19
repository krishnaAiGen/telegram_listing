import os
import asyncio
import logging
import json
from datetime import datetime, timedelta
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET
from dotenv import load_dotenv
from slack_notifier import SlackNotifier

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('binance_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BinanceTest:
    def __init__(self):
        # Binance credentials
        self.binance_api_key = os.getenv('BINANCE_API_KEY')
        self.binance_api_secret = os.getenv('BINANCE_API_SECRET')
        
        # Trading parameters
        self.trade_amount = float(os.getenv('TRADE_AMOUNT', '100'))  # Default $1000
        self.profit_target_pct = float(os.getenv('PROFIT_TARGET_PCT', '15'))  # 15%
        self.stop_loss_pct = float(os.getenv('STOP_LOSS_PCT', '2'))  # 2%
        self.leverage = int(os.getenv('LEVERAGE', '3'))  # 3x leverage
        self.max_hold_hours = 2  # Maximum hold time: 2 hours
        
        # Initialize Binance client
        self.binance_client = Client(self.binance_api_key, self.binance_api_secret, tld='com')
        
        # Initialize Slack notifier
        self.slack_notifier = SlackNotifier()
        
        # Test trade logging file
        self.test_log_file = 'test_trades.json'
        
        logger.info("BinanceTest initialized")
        logger.info(f"Trade amount: ${self.trade_amount}")
        logger.info(f"Profit target: {self.profit_target_pct}%")
        logger.info(f"Stop loss: {self.stop_loss_pct}%")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info(f"Max hold time: {self.max_hold_hours} hours")
    
    def load_test_trades_log(self):
        """Load existing test trades from JSON file"""
        try:
            if os.path.exists(self.test_log_file):
                with open(self.test_log_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading test trades log: {e}")
            return []
    
    def save_test_trade_to_log(self, trade_data):
        """Save test trade data to JSON file"""
        try:
            trades = self.load_test_trades_log()
            trades.append(trade_data)
            
            with open(self.test_log_file, 'w') as f:
                json.dump(trades, f, indent=2, default=str)
            
            logger.info(f"Test trade logged to {self.test_log_file}")
            
        except Exception as e:
            error_msg = f"Error saving test trade to log: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(error_msg)
    
    async def test_connection(self):
        """Test Binance connection"""
        try:
            account_info = self.binance_client.get_account()
            balance_info = self.binance_client.futures_account_balance()
            
            usdt_balance = 0
            for asset in balance_info:
                if asset['asset'] == 'USDT':
                    usdt_balance = float(asset['balance'])
                    break
            
            logger.info("✅ Binance connection successful")
            logger.info(f"💰 Available USDT balance: ${usdt_balance}")
            
            # Send connection test to Slack
            connection_message = {
                "🔧 BINANCE TEST": "✅ CONNECTION OK",
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Status": "Connected successfully",
                "USDT Balance": f"${usdt_balance}",
                "Ready": "Ready for test trading"
            }
            self.slack_notifier.post_to_slack(connection_message)
            
            return True
        except Exception as e:
            error_msg = f"❌ Binance connection failed: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(error_msg)
            return False
    
    def get_symbol_info(self, symbol):
        """Get symbol information and current price"""
        try:
            # Check if symbol exists and is tradeable
            ticker = self.binance_client.get_symbol_ticker(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Get symbol info for precision
            symbol_info = self.binance_client.futures_exchange_info()
            quantity_precision = 0
            price_precision = 0
            min_qty = 0
            step_size = 0
            
            for s in symbol_info['symbols']:
                if s['symbol'] == symbol:
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            step_size = float(f['stepSize'])
                            min_qty = float(f['minQty'])
                            quantity_precision = len(str(step_size).split('.')[-1].rstrip('0'))
                        elif f['filterType'] == 'PRICE_FILTER':
                            price_precision = len(str(f['tickSize']).split('.')[-1].rstrip('0'))
                    break
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'quantity_precision': quantity_precision,
                'price_precision': price_precision,
                'min_qty': min_qty,
                'step_size': step_size
            }
            
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None
    
    def calculate_quantity(self, symbol, price):
        """Calculate the quantity to trade based on available balance"""
        try:
            # Get futures account balance
            balance_info = self.binance_client.futures_account_balance()
            usdt_balance = 0
            
            for asset in balance_info:
                if asset['asset'] == 'USDT':
                    usdt_balance = float(asset['balance'])
                    break
            
            logger.info(f"Available USDT balance: ${usdt_balance}")
            
            # Use specified trade amount or 95% of available balance, whichever is smaller
            trade_amount = min(self.trade_amount, usdt_balance * 0.95)
            
            # Calculate quantity (considering leverage)
            quantity = (trade_amount * self.leverage) / price
            
            # Get symbol info for precision
            symbol_info = self.binance_client.futures_exchange_info()
            quantity_precision = 0
            min_qty = 0
            step_size = 0
            
            for s in symbol_info['symbols']:
                if s['symbol'] == symbol:
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            step_size = float(f['stepSize'])
                            min_qty = float(f['minQty'])
                            quantity_precision = len(str(step_size).split('.')[-1].rstrip('0'))
                            break
                    break
            
            # For larger capital amounts (5000+), round to integer to avoid decimal quantity issues
            if trade_amount >= 5000:
                quantity = int(quantity)
                logger.info(f"Large capital detected (${trade_amount}), rounding quantity to integer: {quantity}")
            else:
                # Round quantity to proper precision based on step size
                if step_size >= 1:
                    # If step size is 1 or more, round to integer
                    quantity = int(quantity)
                else:
                    # Use the precision from step size
                    quantity = round(quantity, quantity_precision)
            
            # Ensure quantity meets minimum requirements
            if quantity < min_qty:
                logger.warning(f"Calculated quantity {quantity} is below minimum {min_qty} for {symbol}")
                quantity = min_qty
            
            # Ensure quantity is a multiple of step size
            if step_size > 0:
                quantity = round(quantity / step_size) * step_size
                if trade_amount >= 5000:
                    quantity = int(quantity)  # Ensure it stays integer for large amounts
            
            logger.info(f"Final calculated quantity: {quantity} {symbol}")
            return quantity
            
        except Exception as e:
            error_msg = f"Error calculating quantity: {e}"
            logger.error(error_msg)
            return None
    
    def get_price_precision(self, price):
        """Get appropriate price precision based on price level"""
        if price <= 10:
            return 4
        elif price <= 100:
            return 3
        elif price <= 1000:
            return 2
        else:
            return 1
    
    async def execute_test_trade(self, symbol):
        """Execute a test long trade for the given symbol"""
        try:
            logger.info(f"🎯 Starting test trade for {symbol}")
            
            # Get symbol information
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                error_msg = f"❌ Symbol {symbol} not found or not tradeable"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            current_price = symbol_info['current_price']
            logger.info(f"📊 Current price for {symbol}: ${current_price}")
            
            # Calculate quantity
            quantity = self.calculate_quantity(symbol, current_price)
            if not quantity:
                error_msg = f"❌ Could not calculate quantity for {symbol}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            # Calculate stop loss and take profit prices
            stop_loss_price = current_price * (1 - self.stop_loss_pct / 100)
            take_profit_price = current_price * (1 + self.profit_target_pct / 100)
            
            # Round prices based on symbol precision
            precision = self.get_price_precision(current_price)
            stop_loss_price = round(stop_loss_price, precision)
            take_profit_price = round(take_profit_price, precision)
            
            # Display trade preview
            trade_preview = f"""
            🎯 TRADE PREVIEW FOR {symbol}
            ═══════════════════════════════════
            Current Price: ${current_price}
            Quantity: {quantity}
            Trade Amount: ${self.trade_amount}
            Leverage: {self.leverage}x
            
            📈 Take Profit: ${take_profit_price} (+{self.profit_target_pct}%)
            📉 Stop Loss: ${stop_loss_price} (-{self.stop_loss_pct}%)
            ⏰ Max Hold Time: {self.max_hold_hours} hours
            ═══════════════════════════════════
            """
            
            print(trade_preview)
            logger.info(trade_preview)
            
            # Ask for confirmation
            confirmation = input("Do you want to execute this trade? (yes/no): ").lower().strip()
            
            if confirmation not in ['yes', 'y']:
                logger.info("❌ Trade cancelled by user")
                return {'success': False, 'error': 'Trade cancelled by user'}
            
            # Set leverage
            try:
                self.binance_client.futures_change_leverage(symbol=symbol, leverage=self.leverage)
                logger.info(f"✅ Leverage set to {self.leverage}x for {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ Could not set leverage for {symbol}: {e}")
            
            # Place market buy order
            logger.info(f"📈 Placing market BUY order for {symbol}...")
            market_order = self.binance_client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )
            
            logger.info(f"✅ Market order placed: {market_order}")
            
            # Get actual fill price
            fill_price = float(self.binance_client.get_symbol_ticker(symbol=symbol)['price'])
            
            # Recalculate stop loss and take profit based on actual fill price
            stop_loss_price = fill_price * (1 - self.stop_loss_pct / 100)
            take_profit_price = fill_price * (1 + self.profit_target_pct / 100)
            stop_loss_price = round(stop_loss_price, precision)
            take_profit_price = round(take_profit_price, precision)
            
            # Place stop loss order
            logger.info(f"📉 Placing stop loss order at ${stop_loss_price}...")
            stop_loss_order = self.binance_client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type='STOP_MARKET',
                stopPrice=stop_loss_price,
                closePosition='true'
            )
            
            logger.info(f"✅ Stop loss order placed")
            
            # Place take profit order
            logger.info(f"📈 Placing take profit order at ${take_profit_price}...")
            take_profit_order = self.binance_client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type='LIMIT',
                price=take_profit_price,
                quantity=quantity,
                timeInForce='GTC'
            )
            
            logger.info(f"✅ Take profit order placed")
            
            # Log test trade
            trade_log_entry = {
                'trade_id': f"TEST_{symbol}_{int(datetime.now().timestamp())}",
                'symbol': symbol,
                'action': 'BUY',
                'entry_time': datetime.now().isoformat(),
                'entry_price': fill_price,
                'quantity': quantity,
                'stop_loss_price': stop_loss_price,
                'take_profit_price': take_profit_price,
                'leverage': self.leverage,
                'trade_amount': self.trade_amount,
                'status': 'ACTIVE',
                'trade_type': 'TEST',
                'max_hold_until': (datetime.now() + timedelta(hours=self.max_hold_hours)).isoformat(),
                'stop_loss_order_id': stop_loss_order.get('orderId'),
                'take_profit_order_id': take_profit_order.get('orderId')
            }
            self.save_test_trade_to_log(trade_log_entry)
            
            # Send success notification to Slack
            success_message = {
                "🧪 TEST TRADE EXECUTED": "✅ SUCCESS",
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Symbol": symbol,
                "Entry Price": f"${fill_price}",
                "Quantity": quantity,
                "Stop Loss": f"${stop_loss_price} (-{self.stop_loss_pct}%)",
                "Take Profit": f"${take_profit_price} (+{self.profit_target_pct}%)",
                "Leverage": f"{self.leverage}x",
                "Trade Amount": f"${self.trade_amount}",
                "Max Hold Time": f"{self.max_hold_hours} hours",
                "Type": "TEST TRADE"
            }
            self.slack_notifier.post_to_slack(success_message)
            
            # Final summary
            success_summary = f"""
            ✅ TEST TRADE EXECUTED SUCCESSFULLY!
            ═══════════════════════════════════
            Symbol: {symbol}
            Entry Price: ${fill_price}
            Quantity: {quantity}
            Stop Loss: ${stop_loss_price} (-{self.stop_loss_pct}%)
            Take Profit: ${take_profit_price} (+{self.profit_target_pct}%)
            Leverage: {self.leverage}x
            Trade Amount: ${self.trade_amount}
            Max Hold Time: {self.max_hold_hours} hours
            ═══════════════════════════════════
            """
            
            print(success_summary)
            logger.info(success_summary)
            
            return {
                'success': True,
                'entry_price': fill_price,
                'quantity': quantity,
                'stop_loss_price': stop_loss_price,
                'take_profit_price': take_profit_price,
                'stop_loss_order_id': stop_loss_order.get('orderId'),
                'take_profit_order_id': take_profit_order.get('orderId')
            }
            
        except Exception as e:
            error_msg = f"❌ Error executing test trade for {symbol}: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(f"Test trade error for {symbol}: {e}")
            return {'success': False, 'error': error_msg}

async def main():
    """Main function to run the Binance test"""
    print("🧪 BINANCE TRADING TEST")
    print("=" * 50)
    
    # Initialize test client
    test_client = BinanceTest()
    
    # Test connection
    if not await test_client.test_connection():
        print("❌ Connection failed. Please check your credentials.")
        return
    
    while True:
        try:
            print("\n" + "=" * 50)
            symbol = input("Enter symbol to test (e.g., BTCUSDT) or 'quit' to exit: ").upper().strip()
            
            if symbol.lower() == 'quit':
                print("👋 Goodbye!")
                break
            
            if not symbol:
                print("❌ Please enter a valid symbol")
                continue
            
            # Add USDT if not present
            if not symbol.endswith('USDT'):
                symbol = symbol + 'USDT'
                print(f"📝 Using symbol: {symbol}")
            
            # Execute test trade
            result = await test_client.execute_test_trade(symbol)
            
            if result['success']:
                print(f"✅ Test trade completed successfully for {symbol}")
            else:
                print(f"❌ Test trade failed for {symbol}: {result.get('error')}")
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            logger.error(f"Main loop error: {e}")

if __name__ == "__main__":
    print("🚀 Starting Binance Test...")
    asyncio.run(main()) 