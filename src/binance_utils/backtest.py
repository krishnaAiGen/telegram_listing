import json
import os
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class CryptoBacktester:
    def __init__(self, price_data_folder: str, initial_capital: float = 10000.0):
        self.price_data_folder = price_data_folder
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.results = []
        self.capital_history = []
    
    def load_coin_data(self, symbol: str) -> Optional[Dict]:
        """Load price data for a specific coin"""
        symbol = symbol + "USDT"
        filename = f"{symbol}.json"
        filepath = os.path.join(self.price_data_folder, filename)
        
        if not os.path.exists(filepath):
            print(f"Warning: Price data file not found for {symbol}")
            return None
        
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading data for {symbol}: {e}")
            return None
    
    def calculate_target_and_stop_prices(self, entry_price: float, is_long: bool, 
                                       profit_target_pct: float, stop_loss_pct: float) -> Tuple[float, float]:
        """Calculate target and stop loss prices based on trade direction"""
        if is_long:
            # Long trade: profit when price goes up, loss when price goes down
            target_price = entry_price * (1 + profit_target_pct / 100)
            stop_price = entry_price * (1 - stop_loss_pct / 100)
        else:
            # Short trade: profit when price goes down, loss when price goes up
            target_price = entry_price * (1 - profit_target_pct / 100)
            stop_price = entry_price * (1 + stop_loss_pct / 100)
        
        return target_price, stop_price
    
    def check_trade_exit(self, current_price: float, target_price: float, stop_price: float, 
                        is_long: bool) -> Optional[str]:
        """Check if trade should exit based on current price"""
        if is_long:
            if current_price >= target_price:
                return "target_hit"
            elif current_price <= stop_price:
                return "stop_loss_hit"
        else:  # Short trade
            if current_price <= target_price:
                return "target_hit"
            elif current_price >= stop_price:
                return "stop_loss_hit"
        
        return None
    
    def calculate_trade_amounts(self, entry_price: float, is_long: bool) -> Tuple[float, float]:
        """Calculate position size and trade amount based on current capital"""
        # Use all available capital for each trade
        trade_amount = self.current_capital
        
        if is_long:
            # For long trades, buy coins with available capital
            position_size = trade_amount / entry_price
        else:
            # For short trades, we're selling coins we don't own (margin trading)
            # Position size represents the dollar amount we're shorting
            position_size = trade_amount / entry_price
        
        return trade_amount, position_size
    
    def update_capital(self, pnl_percent: float, trade_amount: float) -> float:
        """Update capital based on trade P&L"""
        pnl_amount = trade_amount * (pnl_percent / 100)
        self.current_capital = trade_amount + pnl_amount
        
        # Record capital history
        self.capital_history.append({
            'capital': self.current_capital,
            'pnl_amount': pnl_amount,
            'pnl_percent': pnl_percent
        })
        
        return pnl_amount
    
    def calculate_pnl(self, entry_price: float, exit_price: float, is_long: bool) -> float:
        """Calculate profit/loss percentage"""
        if is_long:
            return ((exit_price - entry_price) / entry_price) * 100
        else:  # Short trade
            return ((entry_price - exit_price) / entry_price) * 100
    
    def backtest_coin(self, symbol: str, is_long: bool, profit_target_pct: float, 
                     stop_loss_pct: float, max_hold_hours: int, first_message_timestamp: str = None) -> Dict:
        """Backtest a single coin with given parameters"""
        
        # Load coin data
        coin_data = self.load_coin_data(symbol)
        if not coin_data:
            return {
                'symbol': symbol,
                'error': 'failed_to_load_data',
                'first_message_timestamp': first_message_timestamp
            }
        
        price_history = coin_data['price_history']
        if not price_history:
            return {
                'symbol': symbol,
                'error': 'no_price_data',
                'first_message_timestamp': first_message_timestamp
            }
        
        # Entry conditions
        entry_price = price_history[0]['open_price']  # Enter at opening price
        entry_time = price_history[0]['timestamp']
        entry_index = 0
        
        # Calculate trade amounts based on current capital
        trade_amount, position_size = self.calculate_trade_amounts(entry_price, is_long)
        
        # Calculate target and stop prices
        target_price, stop_price = self.calculate_target_and_stop_prices(
            entry_price, is_long, profit_target_pct, stop_loss_pct
        )
        
        # Calculate maximum hold time in 5-minute intervals
        max_intervals = (max_hold_hours * 60) // 5
        max_exit_index = min(len(price_history) - 1, max_intervals)
        
        print(f"\n{symbol} - {'LONG' if is_long else 'SHORT'} Trade:")
        if first_message_timestamp:
            print(f"  First mentioned: {first_message_timestamp}")
        print(f"  Capital Available: ${self.current_capital:.2f}")
        print(f"  Trade Amount: ${trade_amount:.2f}")
        print(f"  Position Size: {position_size:.6f} coins")
        print(f"  Entry: ${entry_price:.6f} at {entry_time}")
        print(f"  Target: ${target_price:.6f} ({profit_target_pct:+.2f}%)")
        print(f"  Stop: ${stop_price:.6f} ({-stop_loss_pct if is_long else stop_loss_pct:+.2f}%)")
        print(f"  Max hold: {max_hold_hours} hours ({max_intervals} intervals)")
        
        # Iterate through price data to find exit
        exit_reason = "time_limit"
        exit_price = price_history[max_exit_index]['close_price']
        exit_time = price_history[max_exit_index]['timestamp']
        exit_index = max_exit_index
        
        for i in range(1, max_exit_index + 1):
            current_data = price_history[i]
            high_price = current_data['high_price']
            low_price = current_data['low_price']
            close_price = current_data['close_price']
            
            # Check if target or stop was hit during this interval
            if is_long:
                # For long trades, check high for target, low for stop
                if high_price >= target_price:
                    exit_reason = "target_hit"
                    exit_price = target_price
                    exit_time = current_data['timestamp']
                    exit_index = i
                    break
                elif low_price <= stop_price:
                    exit_reason = "stop_loss_hit"
                    exit_price = stop_price
                    exit_time = current_data['timestamp']
                    exit_index = i
                    break
            else:
                # For short trades, check low for target, high for stop
                if low_price <= target_price:
                    exit_reason = "target_hit"
                    exit_price = target_price
                    exit_time = current_data['timestamp']
                    exit_index = i
                    break
                elif high_price >= stop_price:
                    exit_reason = "stop_loss_hit"
                    exit_price = stop_price
                    exit_time = current_data['timestamp']
                    exit_index = i
                    break
        
        # Calculate results
        pnl_percent = self.calculate_pnl(entry_price, exit_price, is_long)
        hold_time_minutes = exit_index * 5
        hold_time_hours = hold_time_minutes / 60
        pnl_amount = self.update_capital(pnl_percent, trade_amount)
        
        print(f"  Exit: ${exit_price:.6f} at {exit_time}")
        print(f"  Reason: {exit_reason}")
        print(f"  Hold time: {hold_time_hours:.2f} hours")
        print(f"  P&L: {pnl_percent:+.2f}% (${pnl_amount:+.2f})")
        print(f"  New Capital: ${self.current_capital:.2f}")
        
        return {
            'symbol': symbol,
            'trade_type': 'LONG' if is_long else 'SHORT',
            'first_message_timestamp': first_message_timestamp,
            'capital_before': trade_amount,
            'capital_after': self.current_capital,
            'trade_amount': trade_amount,
            'position_size': position_size,
            'entry_price': entry_price,
            'entry_time': entry_time,
            'exit_price': exit_price,
            'exit_time': exit_time,
            # Add more descriptive aliases for CSV clarity
            'trade_open_price': entry_price,
            'trade_close_price': exit_price,
            'trade_open_time': entry_time,
            'trade_close_time': exit_time,
            'exit_reason': exit_reason,
            'target_price': target_price,
            'stop_price': stop_price,
            'hold_time_hours': round(hold_time_hours, 2),
            'hold_time_minutes': hold_time_minutes,
            'pnl_percent': round(pnl_percent, 2),
            'pnl_amount': round(pnl_amount, 2),
            'profit_target_pct': profit_target_pct,
            'stop_loss_pct': stop_loss_pct,
            'max_hold_hours': max_hold_hours,
            'data_points_used': exit_index + 1,
            'total_data_points': len(price_history)
        }
    
    def run_backtest(self, symbols: List[str], is_long: bool, profit_target_pct: float,
                    stop_loss_pct: float, max_hold_hours: int, symbol_first_timestamp: Dict[str, str] = None) -> pd.DataFrame:
        """Run backtest for multiple symbols"""
        
        # Reset capital for new backtest
        self.current_capital = self.initial_capital
        self.capital_history = []
        
        print(f"\n{'='*60}")
        print(f"BACKTESTING CONFIGURATION")
        print(f"{'='*60}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Trade Type: {'LONG' if is_long else 'SHORT'}")
        print(f"Profit Target: {profit_target_pct}%")
        print(f"Stop Loss: {stop_loss_pct}%")
        print(f"Max Hold Time: {max_hold_hours} hours")
        print(f"Symbols to test: {len(symbols)}")
        if symbol_first_timestamp:
            print(f"Testing in chronological order (by first message timestamp)")
        print(f"{'='*60}")
        
        results = []
        successful_trades = 0
        
        for i, symbol in enumerate(symbols, 1):
            first_timestamp = symbol_first_timestamp.get(symbol) if symbol_first_timestamp else None
            print(f"\nProcessing {i}/{len(symbols)}: {symbol}")
            
            result = self.backtest_coin(symbol, is_long, profit_target_pct, 
                                      stop_loss_pct, max_hold_hours, first_timestamp)
            
            if 'error' not in result:
                successful_trades += 1
            
            results.append(result)
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame(results)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"BACKTEST SUMMARY")
        print(f"{'='*60}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${self.current_capital:,.2f}")
        print(f"Total Return: ${self.current_capital - self.initial_capital:+,.2f}")
        print(f"Total Return %: {((self.current_capital - self.initial_capital) / self.initial_capital * 100):+.2f}%")
        print(f"Total symbols tested: {len(symbols)}")
        print(f"Successful trades: {successful_trades}")
        print(f"Failed to load: {len(symbols) - successful_trades}")
        
        if successful_trades > 0:
            valid_results = df[df['pnl_percent'].notna()] if 'pnl_percent' in df.columns else pd.DataFrame()
            if len(valid_results) > 0:
                target_hits = len(valid_results[valid_results['exit_reason'] == 'target_hit'])
                stop_hits = len(valid_results[valid_results['exit_reason'] == 'stop_loss_hit'])
                time_exits = len(valid_results[valid_results['exit_reason'] == 'time_limit'])
                
                print(f"\nExit Reasons:")
                print(f"  Target Hit: {target_hits} ({target_hits/successful_trades*100:.1f}%)")
                print(f"  Stop Loss Hit: {stop_hits} ({stop_hits/successful_trades*100:.1f}%)")
                print(f"  Time Limit: {time_exits} ({time_exits/successful_trades*100:.1f}%)")
                
                print(f"\nPerformance Metrics:")
                print(f"  Average P&L %: {valid_results['pnl_percent'].mean():.2f}%")
                print(f"  Median P&L %: {valid_results['pnl_percent'].median():.2f}%")
                print(f"  Best Trade %: {valid_results['pnl_percent'].max():.2f}%")
                print(f"  Worst Trade %: {valid_results['pnl_percent'].min():.2f}%")
                print(f"  Best Trade $: ${valid_results['pnl_amount'].max():,.2f}")
                print(f"  Worst Trade $: ${valid_results['pnl_amount'].min():,.2f}")
                print(f"  Win Rate: {len(valid_results[valid_results['pnl_percent'] > 0])/successful_trades*100:.1f}%")
                print(f"  Average Hold Time: {valid_results['hold_time_hours'].mean():.2f} hours")
                
                # Calculate compound growth
                if len(self.capital_history) > 0:
                    growth_rate = ((self.current_capital / self.initial_capital) ** (1/successful_trades) - 1) * 100
                    print(f"  Compound Growth Rate per Trade: {growth_rate:.3f}%")
        
        return df

def get_symbols_from_sorted_messages(start_date: str = None) -> Tuple[List[str], Dict[str, str]]:
    """Get list of symbols from coin_symbols_from_message_sorted.json in chronological order
    Args:
        start_date: Only include symbols first mentioned on or after this date (format: 'YYYY-MM-DD')
    Returns: (symbols_list, symbol_to_first_timestamp_dict)
    """
    sorted_messages_file = '/Users/krishnayadav/Documents/test_projects/telegram_listing/coin_symbols_from_message.json'
    
    try:
        with open(sorted_messages_file, 'r') as f:
            messages = json.load(f)
        
        print(f"Loaded {len(messages)} messages from sorted file")
        
        # Parse start_date if provided
        start_datetime = None
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                print(f"Filtering symbols from {start_date} onwards")
            except ValueError:
                print(f"Warning: Invalid start_date format '{start_date}'. Expected format: YYYY-MM-DD")
                print("Proceeding without date filter...")
        
        # Extract unique symbols in chronological order (first appearance)
        seen_symbols = set()
        symbols_in_order = []
        symbol_first_timestamp = {}
        
        for message in messages:
            coin_name = message.get('coin_name', '')
            timestamp = message.get('timestamp', '')
            
            if coin_name and coin_name not in seen_symbols:
                # Check if we should filter by start_date
                if start_datetime and timestamp:
                    try:
                        # Parse the message timestamp
                        message_datetime = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        # Convert to naive datetime for comparison
                        message_datetime = message_datetime.replace(tzinfo=None)
                        
                        # Skip if message is before start_date
                        if message_datetime < start_datetime:
                            continue
                    except (ValueError, AttributeError):
                        # If timestamp parsing fails, include the symbol
                        pass
                
                seen_symbols.add(coin_name)
                symbols_in_order.append(coin_name)
                symbol_first_timestamp[coin_name] = timestamp
        
        print(f"Found {len(symbols_in_order)} unique symbols in chronological order")
        if symbols_in_order:
            print(f"Date range: {symbol_first_timestamp[symbols_in_order[0]]} to {symbol_first_timestamp[symbols_in_order[-1]]}")
        
        return symbols_in_order, symbol_first_timestamp
        
    except FileNotFoundError:
        print(f"Error: Sorted messages file not found: {sorted_messages_file}")
        print("Please run the sort_messages.py script first")
        return [], {}
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in sorted messages file: {e}")
        return [], {}
    except Exception as e:
        print(f"Error loading sorted messages: {e}")
        return [], {}

def get_available_symbols(price_data_folder: str) -> List[str]:
    """Get list of available symbols from JSON files (fallback method)"""
    if not os.path.exists(price_data_folder):
        print(f"Error: Price data folder not found: {price_data_folder}")
        return []
    
    symbols = []
    for filename in os.listdir(price_data_folder):
        if filename.endswith('.json'):
            symbol = filename.replace('.json', '')
            symbols.append(symbol)
    
    return sorted(symbols)

def main():
    # =================
    # CONFIGURATION
    # =================
    
    # File paths
    # PRICE_DATA_FOLDER = '/Users/krishnayadav/Documents/test_projects/telegram_trade/coin_price'
    PRICE_DATA_FOLDER = '/Users/krishnayadav/Documents/test_projects/telegram_listing/coin_alpha_price'
    OUTPUT_CSV = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/backtest_results.csv'
    
    # Capital management
    INITIAL_CAPITAL = 2000.0  # Starting capital in USD
    
    # Trading parameters
    IS_LONG = True  # Set to True for long trades, False for short trades
    PROFIT_TARGET_PCT = 15.0  # Profit target percentage
    STOP_LOSS_PCT = 2.0  # Stop loss percentage
    MAX_HOLD_HOURS = 2  # Maximum hold time in hours
    
    # Date filtering
    START_DATE = "2024-06-10"  # Only backtest symbols first mentioned on or after this date (format: YYYY-MM-DD)
    # Set to None to disable date filtering: START_DATE = None


    # # Backtest all coins (no date filter)
    # START_DATE = None

    # # Only backtest very recent coins
    # START_DATE = "2024-12-01"
    
    # Optional: Specify symbols to test (leave empty to test all available)
    SPECIFIC_SYMBOLS = []  # e.g., ['BTCUSDT', 'ETHUSDT'] or [] for all (recommended: [] to test all coins)
    
    # =================
    # EXECUTION
    # =================
    
    # Initialize backtester with initial capital
    backtester = CryptoBacktester(PRICE_DATA_FOLDER, INITIAL_CAPITAL)
    
    # Get symbols to test
    if SPECIFIC_SYMBOLS:
        symbols_to_test = SPECIFIC_SYMBOLS
        symbol_first_timestamp = {}  # No timestamp info for specific symbols
        print(f"Testing specific symbols: {symbols_to_test}")
    else:
        symbols_to_test, symbol_first_timestamp = get_symbols_from_sorted_messages(START_DATE)
        print(f"Found {len(symbols_to_test)} symbols in sorted messages")
    
    if not symbols_to_test:
        print("No symbols found to test. Please check your sorted messages file.")
        return
    
    # Run backtest
    results_df = backtester.run_backtest(
        symbols=symbols_to_test,
        is_long=IS_LONG,
        profit_target_pct=PROFIT_TARGET_PCT,
        stop_loss_pct=STOP_LOSS_PCT,
        max_hold_hours=MAX_HOLD_HOURS,
        symbol_first_timestamp=symbol_first_timestamp
    )
    
    # Save results
    results_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nResults saved to: {OUTPUT_CSV}")
    
    # Display top performers by dollar amount
    valid_results = results_df[results_df['pnl_percent'].notna()] if 'pnl_percent' in results_df.columns else pd.DataFrame()
    if len(valid_results) > 0:
        print(f"\nTop 5 Performers (by $ P&L):")
        top_5 = valid_results.nlargest(5, 'pnl_amount')[['symbol', 'pnl_amount', 'pnl_percent', 'exit_reason', 'capital_after']]
        print(top_5.to_string(index=False))
        
        print(f"\nWorst 5 Performers (by $ P&L):")
        worst_5 = valid_results.nsmallest(5, 'pnl_amount')[['symbol', 'pnl_amount', 'pnl_percent', 'exit_reason', 'capital_after']]
        print(worst_5.to_string(index=False))
        
        print(f"\nCapital Growth Over Time:")
        print(f"Trade 1: ${backtester.initial_capital:,.2f} → ${valid_results.iloc[0]['capital_after']:,.2f}")
        if len(valid_results) > 1:
            mid_point = len(valid_results) // 2
            print(f"Trade {mid_point}: ${valid_results.iloc[mid_point-1]['capital_after']:,.2f}")
        print(f"Final Trade: ${valid_results.iloc[-1]['capital_after']:,.2f}")
        
        # Save capital history as well
        capital_history_df = pd.DataFrame(backtester.capital_history)
        capital_history_df['trade_number'] = range(1, len(capital_history_df) + 1)
        capital_history_file = OUTPUT_CSV.replace('.csv', '_capital_history.csv')
        capital_history_df.to_csv(capital_history_file, index=False)
        print(f"\nCapital history saved to: {capital_history_file}")
    else:
        print(f"\nNo successful trades to analyze.")
        print(f"This could be because:")
        print(f"  - Price data files are missing for the symbols")
        print(f"  - Symbol names don't match the price data file names")
        print(f"  - Price data files are in a different format")
        print(f"\nPlease check:")
        print(f"  1. Price data folder: {PRICE_DATA_FOLDER}")
        print(f"  2. Expected file format: SYMBOL.json (e.g., BTCUSDT.json)")
        print(f"  3. Symbol names in your sorted messages file match the price data files")

if __name__ == '__main__':
    main()