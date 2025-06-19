import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from binance.client import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SingleSymbolBacktester:
    def __init__(self, price_data_folder: str):
        self.price_data_folder = price_data_folder
        
        # Initialize Binance client for fetching data
        try:
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_API_SECRET')
            if api_key and api_secret:
                self.binance_client = Client(api_key, api_secret, tld='com')
                print("✅ Binance client initialized")
            else:
                self.binance_client = None
                print("⚠️ Binance API credentials not found - will only use local data")
        except Exception as e:
            self.binance_client = None
            print(f"⚠️ Failed to initialize Binance client: {e}")
        
        # Symbol extraction patterns (same as in telegram_listen.py)
        self.symbol_patterns = [
            r'\$([A-Z]{2,10})(?:\s*,|\s+listed)',  # $MYX, or $SPK listed
            r'\$([A-Z]{2,10})\b',                  # Any $SYMBOL format
            r'\b([A-Z]{2,10})\s+listed\s+on\s+binance\s+futures',  # SYMBOL listed on binance futures
            r'\b([A-Z]{2,10})\s+.*binance.*futures',               # SYMBOL ... binance ... futures
        ]
    
    def extract_symbol(self, text):
        """Extract the FIRST coin symbol from message using regex patterns"""
        try:
            for pattern in self.symbol_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    # Filter out common words that are not symbols
                    excluded_words = {'LISTED', 'ON', 'BINANCE', 'FUTURES', 'AND', 'THE', 'FOR', 'TO', 'IN', 'AT', 'IS', 'ARE'}
                    
                    for match in matches:
                        symbol = match.upper().strip()
                        # Validate symbol (2-10 characters, letters only, not excluded words)
                        if (2 <= len(symbol) <= 10 and 
                            symbol.isalpha() and 
                            symbol not in excluded_words):
                            print(f"✅ Symbol extracted: {symbol}")
                            return symbol
            return None
        except Exception as e:
            print(f"❌ Error extracting symbol from text: {e}")
            return None
    
    def fetch_binance_futures_data(self, symbol: str, hours: int = 24) -> Optional[Dict]:
        """Fetch historical data from Binance Futures API"""
        if not self.binance_client:
            print("❌ Binance client not available")
            return None
        
        try:
            # Try with USDT suffix first
            trading_symbol = symbol + "USDT" if not symbol.endswith("USDT") else symbol
            
            print(f"📡 Fetching {hours}h of data from Binance Futures for {trading_symbol}...")
            
            # Get klines (candlestick data) for the last 24 hours
            # Interval: 5m (5 minutes)
            end_time = int(time.time() * 1000)  # Current time in milliseconds
            start_time = end_time - (hours * 60 * 60 * 1000)  # hours ago
            
            klines = self.binance_client.futures_klines(
                symbol=trading_symbol,
                interval='5m',
                startTime=start_time,
                endTime=end_time,
                limit=1000
            )
            
            if not klines:
                print(f"❌ No data received for {trading_symbol}")
                return None
            
            # Convert klines to our price history format
            price_history = []
            for kline in klines:
                price_data = {
                    'timestamp': datetime.fromtimestamp(kline[0] / 1000).isoformat(),
                    'open_price': float(kline[1]),
                    'high_price': float(kline[2]),
                    'low_price': float(kline[3]),
                    'close_price': float(kline[4]),
                    'volume': float(kline[5])
                }
                price_history.append(price_data)
            
            print(f"✅ Fetched {len(price_history)} data points from Binance Futures")
            
            # Save to local file for future use
            coin_data = {
                'symbol': trading_symbol,
                'price_history': price_history,
                'data_source': 'binance_futures_api',
                'fetch_time': datetime.now().isoformat(),
                'hours_of_data': hours
            }
            
            # Save to local cache
            cache_filename = f"{trading_symbol}.json"
            cache_filepath = os.path.join(self.price_data_folder, cache_filename)
            
            # Create directory if it doesn't exist
            os.makedirs(self.price_data_folder, exist_ok=True)
            
            with open(cache_filepath, 'w') as f:
                json.dump(coin_data, f, indent=2)
            
            print(f"💾 Cached data to: {cache_filepath}")
            
            return coin_data
            
        except Exception as e:
            print(f"❌ Error fetching data from Binance for {symbol}: {e}")
            return None
    
    def load_coin_data(self, symbol: str) -> Optional[Dict]:
        """Load price data for a specific coin - try local first, then Binance API"""
        # First try with USDT suffix
        symbol_with_usdt = symbol + "USDT" if not symbol.endswith("USDT") else symbol
        filename = f"{symbol_with_usdt}.json"
        filepath = os.path.join(self.price_data_folder, filename)
        
        # Try to load from local file first
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    print(f"✅ Loaded price data from local file: {filepath}")
                    return data
            except Exception as e:
                print(f"⚠️ Error loading local data for {symbol}: {e}")
        
        # Try without USDT suffix
        filename_no_usdt = f"{symbol}.json"
        filepath_no_usdt = os.path.join(self.price_data_folder, filename_no_usdt)
        
        if os.path.exists(filepath_no_usdt):
            try:
                with open(filepath_no_usdt, 'r') as f:
                    data = json.load(f)
                    print(f"✅ Loaded price data from local file: {filepath_no_usdt}")
                    return data
            except Exception as e:
                print(f"⚠️ Error loading local data for {symbol}: {e}")
        
        # If local files not found, try to fetch from Binance
        print(f"📁 Local price data not found for {symbol}")
        print(f"🔄 Attempting to fetch from Binance Futures API...")
        
        return self.fetch_binance_futures_data(symbol)
    
    def calculate_target_and_stop_prices(self, entry_price: float, profit_target_pct: float = 15.0, 
                                       stop_loss_pct: float = 2.0) -> Tuple[float, float]:
        """Calculate target and stop loss prices for long trade"""
        target_price = entry_price * (1 + profit_target_pct / 100)
        stop_price = entry_price * (1 - stop_loss_pct / 100)
        return target_price, stop_price
    
    def analyze_symbol_from_message(self, message: str) -> Dict:
        """Main function to analyze a symbol extracted from a message"""
        print("="*80)
        print("🧪 SINGLE SYMBOL BACKTEST ANALYSIS")
        print("="*80)
        print(f"📨 Message: {message}")
        print("-"*80)
        
        # Extract symbol from message
        symbol = self.extract_symbol(message)
        if not symbol:
            return {
                'success': False,
                'error': 'No valid symbol found in message',
                'message': message
            }
        
        # Load coin data (local or from Binance)
        coin_data = self.load_coin_data(symbol)
        if not coin_data:
            return {
                'success': False,
                'error': f'Failed to load price data for {symbol} from both local files and Binance API',
                'symbol': symbol,
                'message': message
            }
        
        # Get price history
        price_history = coin_data.get('price_history', [])
        if not price_history:
            return {
                'success': False,
                'error': f'No price data available for {symbol}',
                'symbol': symbol,
                'message': message
            }
        
        # Entry conditions - use first price as buying price
        entry_price = price_history[0]['open_price']
        entry_time = price_history[0]['timestamp']
        
        # Calculate target and stop prices
        target_price, stop_price = self.calculate_target_and_stop_prices(entry_price)
        
        data_source = coin_data.get('data_source', 'local_file')
        hours_of_data = coin_data.get('hours_of_data', 'unknown')
        
        print(f"🎯 TRADE SETUP FOR {symbol}")
        print(f"   Data Source: {data_source}")
        if hours_of_data != 'unknown':
            print(f"   Data Coverage: {hours_of_data} hours")
        print(f"   Entry Price: ${entry_price:.6f}")
        print(f"   Entry Time: {entry_time}")
        print(f"   Target Price: ${target_price:.6f} (+15%)")
        print(f"   Stop Loss: ${stop_price:.6f} (-2%)")
        print(f"   Total Data Points: {len(price_history)}")
        print("-"*80)
        
        # Analyze price movements to find exit
        exit_reason = "end_of_data"
        exit_price = price_history[-1]['close_price']
        exit_time = price_history[-1]['timestamp']
        exit_index = len(price_history) - 1
        
        print("📊 PRICE ANALYSIS:")
        
        for i, data_point in enumerate(price_history):
            current_time = data_point['timestamp']
            high_price = data_point['high_price']
            low_price = data_point['low_price']
            close_price = data_point['close_price']
            
            # Check if target hit (high price >= target)
            if high_price >= target_price:
                exit_reason = "profit_target_hit"
                exit_price = target_price
                exit_time = current_time
                exit_index = i
                print(f"   🎉 PROFIT TARGET HIT at index {i}")
                print(f"      Time: {current_time}")
                print(f"      High: ${high_price:.6f} (>= ${target_price:.6f})")
                print(f"      Exit Price: ${exit_price:.6f}")
                break
            
            # Check if stop loss hit (low price <= stop)
            elif low_price <= stop_price:
                exit_reason = "stop_loss_hit"
                exit_price = stop_price
                exit_time = current_time
                exit_index = i
                print(f"   🛑 STOP LOSS HIT at index {i}")
                print(f"      Time: {current_time}")
                print(f"      Low: ${low_price:.6f} (<= ${stop_price:.6f})")
                print(f"      Exit Price: ${exit_price:.6f}")
                break
            
            # Print periodic updates for long datasets
            if i % max(1, len(price_history) // 10) == 0 or i < 5:
                print(f"   [{i:4d}] {current_time} | High: ${high_price:.6f} | Low: ${low_price:.6f} | Close: ${close_price:.6f}")
        
        # If no exit condition was met, use final price
        if exit_reason == "end_of_data":
            print(f"   📈 Reached end of data without hitting target or stop loss")
            print(f"      Final Close Price: ${exit_price:.6f}")
        
        # Calculate results
        pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        hold_time_intervals = exit_index + 1
        hold_time_hours = (hold_time_intervals * 5) / 60  # Assuming 5-minute intervals
        
        print("-"*80)
        print("📋 TRADE RESULTS:")
        print(f"   Symbol: {symbol}")
        print(f"   Data Source: {data_source}")
        print(f"   Entry: ${entry_price:.6f} at {entry_time}")
        print(f"   Exit: ${exit_price:.6f} at {exit_time}")
        print(f"   Exit Reason: {exit_reason}")
        print(f"   P&L: {pnl_percent:+.2f}%")
        print(f"   Hold Time: {hold_time_hours:.2f} hours ({hold_time_intervals} intervals)")
        print(f"   Data Points Used: {exit_index + 1} / {len(price_history)}")
        
        # Determine outcome
        if exit_reason == "profit_target_hit":
            outcome = "🎉 PROFIT TARGET ACHIEVED (+15%)"
        elif exit_reason == "stop_loss_hit":
            outcome = "🛑 STOP LOSS TRIGGERED (-2%)"
        else:
            if pnl_percent > 0:
                outcome = f"📈 POSITIVE P&L ({pnl_percent:+.2f}%)"
            else:
                outcome = f"📉 NEGATIVE P&L ({pnl_percent:+.2f}%)"
        
        print(f"   Outcome: {outcome}")
        print("="*80)
        
        return {
            'success': True,
            'symbol': symbol,
            'message': message,
            'data_source': data_source,
            'entry_price': entry_price,
            'entry_time': entry_time,
            'exit_price': exit_price,
            'exit_time': exit_time,
            'exit_reason': exit_reason,
            'target_price': target_price,
            'stop_price': stop_price,
            'pnl_percent': round(pnl_percent, 2),
            'hold_time_hours': round(hold_time_hours, 2),
            'hold_time_intervals': hold_time_intervals,
            'total_data_points': len(price_history),
            'outcome': outcome
        }

def main():
    """Main function to run the single symbol backtest"""
    
    # Configuration
    PRICE_DATA_FOLDER = '/Users/krishnayadav/Documents/test_projects/telegram_listing/coin_alpha_price'
    
    # Test message - you can modify this
    message = "$SPK listed on Binance futures"
    
    print("🚀 Starting Single Symbol Backtest Analysis...")
    print(f"📁 Price Data Folder: {PRICE_DATA_FOLDER}")
    
    # Initialize backtester
    backtester = SingleSymbolBacktester(PRICE_DATA_FOLDER)
    
    # Analyze the message
    result = backtester.analyze_symbol_from_message(message)
    
    if result['success']:
        print("\n✅ Analysis completed successfully!")
        print(f"🎯 Final Result: {result['outcome']}")
        print(f"📊 Data Source: {result.get('data_source', 'unknown')}")
    else:
        print(f"\n❌ Analysis failed: {result['error']}")
    
    return result

if __name__ == "__main__":
    # You can modify the message here
    message = "$SPK listed on Binance futures"
    
    # Or uncomment to test with different messages:
    # message = "$MYX, $F listed on Binance futures"
    # message = "$PUFFER, $PORT3 listed on Binance futures"
    # message = "BTCUSDT listed on binance futures"
    
    print(f"🧪 Testing with message: '{message}'")
    main() 