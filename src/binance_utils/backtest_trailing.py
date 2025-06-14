import json
import os
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class TrailingCryptoBacktester:
    def __init__(self, price_data_folder: str, initial_capital: float = 10000.0):
        self.price_data_folder = price_data_folder
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.results = []
        self.capital_history = []
    
    def load_coin_data(self, symbol: str) -> Optional[Dict]:
        """Load price data for a specific coin"""
        symbol = symbol + 'USDT'
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
    
    def calculate_trade_amounts(self, entry_price: float) -> Tuple[float, float]:
        """Calculate position size and trade amount based on current capital"""
        trade_amount = self.current_capital
        position_size = trade_amount / entry_price
        return trade_amount, position_size
    
    def update_capital(self, pnl_percent: float, trade_amount: float) -> float:
        """Update capital based on trade P&L"""
        old_capital = self.current_capital
        self.current_capital = self.current_capital * (1 + pnl_percent / 100)
        pnl_amount = self.current_capital - old_capital
        
        self.capital_history.append({
            'capital': self.current_capital,
            'pnl_amount': pnl_amount,
            'pnl_percent': pnl_percent
        })
        
        return pnl_amount
    
    def calculate_pnl(self, entry_price: float, exit_price: float) -> float:
        """Calculate profit/loss percentage for long trades"""
        return ((exit_price - entry_price) / entry_price) * 100
    
    def backtest_coin_trailing(self, symbol: str, initial_profit_target_pct: float, 
                              stop_loss_pct: float, max_hold_hours: int,
                              profit_extension_pct: float = 10.0,
                              trigger_threshold_pct: float = 80.0,
                              trailing_stop_pct: float = 5.0,
                              first_message_timestamp: str = None,
                              csv_row_index: int = None) -> Dict:
        """
        Backtest a single coin with trailing profit target strategy
        
        Args:
            symbol: Coin symbol
            initial_profit_target_pct: Initial profit target (e.g., 15%)
            stop_loss_pct: Fixed stop loss (e.g., 2%)
            max_hold_hours: Maximum hold time
            profit_extension_pct: How much to extend profit target when triggered (e.g., 10%)
            trigger_threshold_pct: When to extend target (e.g., 80% of current target)
            trailing_stop_pct: Trailing stop from highest point (e.g., 5%)
        """
        
        # Load coin data
        coin_data = self.load_coin_data(symbol)
        if not coin_data:
            return {
                'csv_row_index': csv_row_index,
                'symbol': symbol,
                'error': 'failed_to_load_data',
                'first_message_timestamp': first_message_timestamp
            }
        
        price_history = coin_data['price_history']
        if not price_history:
            return {
                'csv_row_index': csv_row_index,
                'symbol': symbol,
                'error': 'no_price_data',
                'first_message_timestamp': first_message_timestamp
            }
        
        # Entry conditions
        entry_price = price_history[0]['open_price']
        entry_time = price_history[0]['timestamp']
        trade_amount, position_size = self.calculate_trade_amounts(entry_price)
        
        # Initialize trading variables
        current_profit_target_pct = initial_profit_target_pct
        current_profit_target_price = entry_price * (1 + current_profit_target_pct / 100)
        stop_loss_price = entry_price * (1 - stop_loss_pct / 100)
        
        # Trailing variables
        highest_price = entry_price
        highest_profit_pct = 0.0
        trailing_stop_price = entry_price  # Will be updated as price rises
        target_extensions = 0
        
        # Calculate maximum hold time
        max_intervals = (max_hold_hours * 60) // 5
        max_exit_index = min(len(price_history) - 1, max_intervals)
        
        print(f"\n{symbol} - TRAILING Strategy (CSV Row {csv_row_index + 1 if csv_row_index is not None else 'N/A'}):")
        if first_message_timestamp:
            print(f"  First mentioned: {first_message_timestamp}")
        print(f"  Capital Available: ${self.current_capital:.2f}")
        print(f"  Entry: ${entry_price:.6f} at {entry_time}")
        print(f"  Initial Target: ${current_profit_target_price:.6f} ({current_profit_target_pct:.1f}%)")
        print(f"  Stop Loss: ${stop_loss_price:.6f} ({-stop_loss_pct:.1f}%)")
        print(f"  Extension: +{profit_extension_pct}% at {trigger_threshold_pct}% of target")
        print(f"  Trailing Stop: {trailing_stop_pct}% from peak")
        
        # Track trade progression
        trade_log = []
        
        # Iterate through price data
        exit_reason = "time_limit"
        exit_price = price_history[max_exit_index]['close_price']
        exit_time = price_history[max_exit_index]['timestamp']
        exit_index = max_exit_index
        
        for i in range(1, max_exit_index + 1):
            current_data = price_history[i]
            high_price = current_data['high_price']
            low_price = current_data['low_price']
            close_price = current_data['close_price']
            current_time = current_data['timestamp']
            
            # Update highest price seen
            if high_price > highest_price:
                highest_price = high_price
                highest_profit_pct = self.calculate_pnl(entry_price, highest_price)
                
                # Update trailing stop (only moves up)
                new_trailing_stop = highest_price * (1 - trailing_stop_pct / 100)
                if new_trailing_stop > trailing_stop_price:
                    trailing_stop_price = new_trailing_stop
            
            # Check if we should extend the profit target
            current_profit_from_entry = self.calculate_pnl(entry_price, high_price)
            target_trigger_level = current_profit_target_pct * (trigger_threshold_pct / 100)
            
            if current_profit_from_entry >= target_trigger_level and current_profit_from_entry < current_profit_target_pct:
                # Extend the profit target
                old_target = current_profit_target_pct
                current_profit_target_pct += profit_extension_pct
                current_profit_target_price = entry_price * (1 + current_profit_target_pct / 100)
                target_extensions += 1
                
                trade_log.append({
                    'time': current_time,
                    'price': high_price,
                    'action': 'target_extended',
                    'old_target': old_target,
                    'new_target': current_profit_target_pct,
                    'current_profit': current_profit_from_entry
                })
                
                print(f"    🎯 Target Extended: {old_target:.1f}% → {current_profit_target_pct:.1f}% at ${high_price:.6f} ({current_profit_from_entry:.2f}% profit)")
            
            # Check exit conditions (in order of priority)
            
            # 1. Check profit target hit
            if high_price >= current_profit_target_price:
                exit_reason = "profit_target"
                exit_price = current_profit_target_price
                exit_time = current_time
                exit_index = i
                break
            
            # 2. Check fixed stop loss hit
            if low_price <= stop_loss_price:
                exit_reason = "stop_loss"
                exit_price = stop_loss_price
                exit_time = current_time
                exit_index = i
                break
            
            # 3. Check trailing stop hit (only if we've made some profit)
            if highest_profit_pct > 0 and low_price <= trailing_stop_price:
                exit_reason = "trailing_stop"
                exit_price = trailing_stop_price
                exit_time = current_time
                exit_index = i
                break
        
        # Calculate final results
        pnl_percent = self.calculate_pnl(entry_price, exit_price)
        hold_time_minutes = exit_index * 5
        hold_time_hours = hold_time_minutes / 60
        pnl_amount = self.update_capital(pnl_percent, trade_amount)
        
        print(f"  Exit: ${exit_price:.6f} at {exit_time}")
        print(f"  Reason: {exit_reason}")
        print(f"  Highest Price: ${highest_price:.6f} ({highest_profit_pct:.2f}% peak)")
        print(f"  Target Extensions: {target_extensions}")
        print(f"  Final Target: {current_profit_target_pct:.1f}%")
        print(f"  Hold time: {hold_time_hours:.2f} hours")
        print(f"  P&L: {pnl_percent:+.2f}% (${pnl_amount:+.2f})")
        print(f"  New Capital: ${self.current_capital:.2f}")
        
        return {
            'csv_row_index': csv_row_index,
            'symbol': symbol,
            'trade_type': 'TRAILING_LONG',
            'first_message_timestamp': first_message_timestamp,
            'capital_before': trade_amount,
            'capital_after': self.current_capital,
            'trade_amount': trade_amount,
            'position_size': position_size,
            'entry_price': entry_price,
            'entry_time': entry_time,
            'exit_price': exit_price,
            'exit_time': exit_time,
            'exit_reason': exit_reason,
            'initial_profit_target_pct': initial_profit_target_pct,
            'final_profit_target_pct': current_profit_target_pct,
            'target_extensions': target_extensions,
            'stop_loss_pct': stop_loss_pct,
            'trailing_stop_pct': trailing_stop_pct,
            'highest_price': highest_price,
            'highest_profit_pct': round(highest_profit_pct, 2),
            'trailing_stop_price': trailing_stop_price,
            'hold_time_hours': round(hold_time_hours, 2),
            'hold_time_minutes': hold_time_minutes,
            'pnl_percent': round(pnl_percent, 2),
            'pnl_amount': round(pnl_amount, 2),
            'max_hold_hours': max_hold_hours,
            'data_points_used': exit_index + 1,
            'total_data_points': len(price_history),
            'trade_log': trade_log
        }
    
    def run_backtest_from_csv(self, coin_analysis_csv: str, 
                             initial_profit_target_pct: float,
                             stop_loss_pct: float, 
                             max_hold_hours: int,
                             profit_extension_pct: float = 10.0,
                             trigger_threshold_pct: float = 80.0,
                             trailing_stop_pct: float = 5.0,
                             start_date: str = None, 
                             end_date: str = None) -> pd.DataFrame:
        """Run trailing backtest using symbols from coin price analysis CSV"""
        
        # Load the coin analysis CSV
        try:
            coin_df = pd.read_csv(coin_analysis_csv)
            print(f"Loaded {len(coin_df)} rows from coin analysis CSV")
        except Exception as e:
            print(f"Error loading coin analysis CSV: {e}")
            return pd.DataFrame()
        
        # Filter by date if specified
        if start_date or end_date:
            if 'timestamp' in coin_df.columns:
                coin_df['timestamp'] = pd.to_datetime(coin_df['timestamp'])
                original_count = len(coin_df)
                
                if start_date:
                    start_dt = pd.to_datetime(start_date).tz_localize('UTC')
                    coin_df = coin_df[coin_df['timestamp'] >= start_dt]
                    print(f"Filtered by start_date {start_date}: {len(coin_df)} rows remaining")
                
                if end_date:
                    end_dt = pd.to_datetime(end_date).tz_localize('UTC')
                    coin_df = coin_df[coin_df['timestamp'] <= end_dt]
                    print(f"Filtered by end_date {end_date}: {len(coin_df)} rows remaining")
                
                print(f"Date filtering: {original_count} → {len(coin_df)} rows")
        
        # Reset capital for new backtest
        self.current_capital = self.initial_capital
        self.capital_history = []
        
        print(f"\n{'='*60}")
        print(f"TRAILING PROFIT TARGET BACKTESTING")
        print(f"{'='*60}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Initial Profit Target: {initial_profit_target_pct}%")
        print(f"Stop Loss: {stop_loss_pct}%")
        print(f"Max Hold Time: {max_hold_hours} hours")
        print(f"Profit Extension: +{profit_extension_pct}% when {trigger_threshold_pct}% of target reached")
        print(f"Trailing Stop: {trailing_stop_pct}% from peak")
        print(f"Symbols to test: {len(coin_df)}")
        print(f"{'='*60}")
        
        results = []
        successful_trades = 0
        
        # Process each row in CSV order
        for csv_index, row in coin_df.iterrows():
            symbol = row.get('coin_name', '')
            timestamp = row.get('timestamp', '')
            
            if not symbol and 'symbol' in row:
                symbol = row['symbol']
            if not symbol and 'coin_symbol' in row:
                symbol = row['coin_symbol']
            
            if not symbol:
                print(f"Warning: No symbol found in row {csv_index}")
                continue
            
            # Remove 'USDT' suffix if present
            if symbol.endswith('USDT'):
                symbol = symbol[:-4]
            
            print(f"\nProcessing CSV row {csv_index + 1}/{len(coin_df)}: {symbol}")
            
            result = self.backtest_coin_trailing(
                symbol=symbol,
                initial_profit_target_pct=initial_profit_target_pct,
                stop_loss_pct=stop_loss_pct,
                max_hold_hours=max_hold_hours,
                profit_extension_pct=profit_extension_pct,
                trigger_threshold_pct=trigger_threshold_pct,
                trailing_stop_pct=trailing_stop_pct,
                first_message_timestamp=str(timestamp),
                csv_row_index=csv_index
            )
            
            if 'error' not in result:
                successful_trades += 1
            
            results.append(result)
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame(results)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"TRAILING BACKTEST SUMMARY")
        print(f"{'='*60}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${self.current_capital:,.2f}")
        print(f"Total Return: ${self.current_capital - self.initial_capital:+,.2f}")
        print(f"Total Return %: {((self.current_capital - self.initial_capital) / self.initial_capital * 100):+.2f}%")
        print(f"Total symbols tested: {len(coin_df)}")
        print(f"Successful trades: {successful_trades}")
        print(f"Failed to load: {len(coin_df) - successful_trades}")
        
        if successful_trades > 0:
            valid_results = df[df['pnl_percent'].notna()]
            if len(valid_results) > 0:
                # Exit reason analysis
                target_hits = len(valid_results[valid_results['exit_reason'] == 'profit_target'])
                stop_hits = len(valid_results[valid_results['exit_reason'] == 'stop_loss'])
                trailing_hits = len(valid_results[valid_results['exit_reason'] == 'trailing_stop'])
                time_exits = len(valid_results[valid_results['exit_reason'] == 'time_limit'])
                
                print(f"\nExit Reasons:")
                print(f"  Profit Target Hit: {target_hits} ({target_hits/successful_trades*100:.1f}%)")
                print(f"  Stop Loss Hit: {stop_hits} ({stop_hits/successful_trades*100:.1f}%)")
                print(f"  Trailing Stop Hit: {trailing_hits} ({trailing_hits/successful_trades*100:.1f}%)")
                print(f"  Time Limit: {time_exits} ({time_exits/successful_trades*100:.1f}%)")
                
                # Target extension analysis
                total_extensions = valid_results['target_extensions'].sum()
                trades_with_extensions = len(valid_results[valid_results['target_extensions'] > 0])
                
                print(f"\nTarget Extension Analysis:")
                print(f"  Total Extensions: {total_extensions}")
                print(f"  Trades with Extensions: {trades_with_extensions} ({trades_with_extensions/successful_trades*100:.1f}%)")
                if trades_with_extensions > 0:
                    avg_extensions = total_extensions / trades_with_extensions
                    print(f"  Avg Extensions per Extended Trade: {avg_extensions:.1f}")
                
                print(f"\nPerformance Metrics:")
                print(f"  Average P&L %: {valid_results['pnl_percent'].mean():.2f}%")
                print(f"  Median P&L %: {valid_results['pnl_percent'].median():.2f}%")
                print(f"  Best Trade %: {valid_results['pnl_percent'].max():.2f}%")
                print(f"  Worst Trade %: {valid_results['pnl_percent'].min():.2f}%")
                print(f"  Average Peak Profit %: {valid_results['highest_profit_pct'].mean():.2f}%")
                print(f"  Win Rate: {len(valid_results[valid_results['pnl_percent'] > 0])/successful_trades*100:.1f}%")
                print(f"  Average Hold Time: {valid_results['hold_time_hours'].mean():.2f} hours")
                
                # Compare with fixed target strategy
                fixed_target_wins = len(valid_results[
                    (valid_results['pnl_percent'] >= initial_profit_target_pct) |
                    (valid_results['exit_reason'] == 'profit_target')
                ])
                print(f"\nStrategy Comparison:")
                print(f"  Fixed {initial_profit_target_pct}% Target Would Win: {fixed_target_wins} trades")
                print(f"  Trailing Strategy Advantage: {successful_trades - fixed_target_wins:+d} trades")
        
        return df

def main():
    # =================
    # CONFIGURATION
    # =================
    
    # File paths
    PRICE_DATA_FOLDER = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_coin_price'
    COIN_ANALYSIS_CSV = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_coin_price_analysis.csv'
    OUTPUT_CSV = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_trailing_backtest_results.csv'
    
    # Capital management
    INITIAL_CAPITAL = 2000.0
    
    # Trading parameters
    INITIAL_PROFIT_TARGET_PCT = 15.0  # Starting profit target
    STOP_LOSS_PCT = 2.0              # Fixed stop loss (never changes)
    MAX_HOLD_HOURS = 1               # Maximum hold time
    
    # Trailing strategy parameters
    PROFIT_EXTENSION_PCT = 10.0      # How much to extend target (+10%)
    TRIGGER_THRESHOLD_PCT = 80.0     # When to extend (at 80% of current target)
    TRAILING_STOP_PCT = 5.0          # Trailing stop from peak (5% drawdown)
    
    # Date filtering
    START_DATE = "2024-06-10"
    END_DATE = None
    
    # =================
    # EXECUTION
    # =================
    
    print("🎯 TRAILING PROFIT TARGET BACKTEST")
    print("=" * 50)
    print(f"Strategy: Start with {INITIAL_PROFIT_TARGET_PCT}% target")
    print(f"When price reaches {TRIGGER_THRESHOLD_PCT}% of target → extend by +{PROFIT_EXTENSION_PCT}%")
    print(f"Trailing stop: {TRAILING_STOP_PCT}% from highest point")
    print(f"Fixed stop loss: {STOP_LOSS_PCT}%")
    print("=" * 50)
    
    # Initialize backtester
    backtester = TrailingCryptoBacktester(PRICE_DATA_FOLDER, INITIAL_CAPITAL)
    
    # Run backtest
    results_df = backtester.run_backtest_from_csv(
        coin_analysis_csv=COIN_ANALYSIS_CSV,
        initial_profit_target_pct=INITIAL_PROFIT_TARGET_PCT,
        stop_loss_pct=STOP_LOSS_PCT,
        max_hold_hours=MAX_HOLD_HOURS,
        profit_extension_pct=PROFIT_EXTENSION_PCT,
        trigger_threshold_pct=TRIGGER_THRESHOLD_PCT,
        trailing_stop_pct=TRAILING_STOP_PCT,
        start_date=START_DATE,
        end_date=END_DATE
    )
    
    # Save results
    if not results_df.empty:
        results_df.to_csv(OUTPUT_CSV, index=False)
        print(f"\nResults saved to: {OUTPUT_CSV}")
        
        # Show top performers
        valid_results = results_df[results_df['pnl_percent'].notna()]
        if len(valid_results) > 0:
            print(f"\nTop 5 Performers:")
            top_5 = valid_results.nlargest(5, 'pnl_amount')[
                ['symbol', 'pnl_amount', 'pnl_percent', 'highest_profit_pct', 
                 'target_extensions', 'exit_reason']
            ]
            print(top_5.to_string(index=False))
            
            print(f"\nMost Extended Targets:")
            most_extended = valid_results.nlargest(5, 'target_extensions')[
                ['symbol', 'target_extensions', 'initial_profit_target_pct', 
                 'final_profit_target_pct', 'pnl_percent', 'exit_reason']
            ]
            print(most_extended.to_string(index=False))

if __name__ == '__main__':
    main() 