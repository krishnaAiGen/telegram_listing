import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import os
from itertools import product
import time

# Input and output paths
PRICE_DATA_FOLDER = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_coin_price'
INPUT_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_futures_coin_symbols_sorted.json'
BACKTEST_RESULTS_CSV = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/backtest_grid_search_results.csv'
DETAILED_TRADES_CSV = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/detailed_trades_results.csv'

class GridSearchBacktester:
    def __init__(self, price_data_folder, input_json):
        self.price_data_folder = price_data_folder
        self.input_json = input_json
        self.coins_data = self.load_coins_with_timestamps()
        
    def load_coins_with_timestamps(self):
        """Load coins data with timestamps and sort chronologically"""
        # Load the original JSON with timestamps
        with open(self.input_json, 'r') as f:
            coins_list = json.load(f)
        
        coins_data = []
        
        for coin_entry in coins_list:
            symbol = coin_entry['symbol']
            timestamp_str = coin_entry['timestamp']
            
            # Load corresponding price data
            price_file_path = os.path.join(self.price_data_folder, f"{symbol}.json")
            
            if os.path.exists(price_file_path):
                try:
                    with open(price_file_path, 'r') as f:
                        price_data = json.load(f)
                    
                    if price_data.get('price_history') and len(price_data['price_history']) > 10:
                        # Parse timestamp
                        if isinstance(timestamp_str, str):
                            if '+' in timestamp_str:
                                listing_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            else:
                                listing_time = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
                        else:
                            listing_time = datetime.fromisoformat(str(timestamp_str)).replace(tzinfo=timezone.utc)
                        
                        coins_data.append({
                            'symbol': symbol,
                            'listing_timestamp': listing_time,
                            'timestamp_str': timestamp_str,
                            'coin_name': coin_entry['coin_name'],
                            'message': coin_entry['message'],
                            'price_data': price_data
                        })
                        
                except Exception as e:
                    print(f"Error loading price data for {symbol}: {e}")
        
        # Sort by listing timestamp (chronological order)
        coins_data.sort(key=lambda x: x['listing_timestamp'])
        
        print(f"Loaded {len(coins_data)} coins with price data, sorted chronologically")
        print(f"Date range: {coins_data[0]['listing_timestamp'].strftime('%Y-%m-%d')} to {coins_data[-1]['listing_timestamp'].strftime('%Y-%m-%d')}")
        
        return coins_data
    
    def simulate_trade(self, price_history, profit_target_pct, stop_loss_pct, max_hold_hours):
        """
        Simulate a single trade with given parameters
        
        Args:
            price_history: List of price data points
            profit_target_pct: Profit target percentage (e.g., 10 for 10%)
            stop_loss_pct: Stop loss percentage (e.g., 5 for 5%)
            max_hold_hours: Maximum hold time in hours
            
        Returns:
            dict: Trade result with entry/exit details
        """
        if not price_history or len(price_history) < 2:
            return None
        
        # Entry point (first available price)
        entry_price = price_history[0]['close_price']
        entry_time = price_history[0]['timestamp']
        entry_minutes = price_history[0]['minutes_from_listing']
        
        # Calculate target and stop prices
        profit_target_price = entry_price * (1 + profit_target_pct / 100)
        stop_loss_price = entry_price * (1 - stop_loss_pct / 100)
        max_hold_minutes = max_hold_hours * 60
        
        # Simulate the trade
        for i, candle in enumerate(price_history[1:], 1):
            current_time_minutes = candle['minutes_from_listing']
            hold_duration_minutes = current_time_minutes - entry_minutes
            
            # Check if max hold time exceeded
            if hold_duration_minutes >= max_hold_minutes:
                return {
                    'entry_price': entry_price,
                    'exit_price': candle['close_price'],
                    'entry_time': entry_time,
                    'exit_time': candle['timestamp'],
                    'entry_minutes': entry_minutes,
                    'exit_minutes': current_time_minutes,
                    'hold_duration_minutes': hold_duration_minutes,
                    'hold_duration_hours': hold_duration_minutes / 60,
                    'profit_pct': ((candle['close_price'] - entry_price) / entry_price) * 100,
                    'exit_reason': 'max_hold_time',
                    'target_hit': False,
                    'stop_hit': False
                }
            
            # Check profit target (using high price)
            if candle['high_price'] >= profit_target_price:
                return {
                    'entry_price': entry_price,
                    'exit_price': profit_target_price,
                    'entry_time': entry_time,
                    'exit_time': candle['timestamp'],
                    'entry_minutes': entry_minutes,
                    'exit_minutes': current_time_minutes,
                    'hold_duration_minutes': hold_duration_minutes,
                    'hold_duration_hours': hold_duration_minutes / 60,
                    'profit_pct': profit_target_pct,
                    'exit_reason': 'profit_target',
                    'target_hit': True,
                    'stop_hit': False
                }
            
            # Check stop loss (using low price)
            if candle['low_price'] <= stop_loss_price:
                return {
                    'entry_price': entry_price,
                    'exit_price': stop_loss_price,
                    'entry_time': entry_time,
                    'exit_time': candle['timestamp'],
                    'entry_minutes': entry_minutes,
                    'exit_minutes': current_time_minutes,
                    'hold_duration_minutes': hold_duration_minutes,
                    'hold_duration_hours': hold_duration_minutes / 60,
                    'profit_pct': -stop_loss_pct,
                    'exit_reason': 'stop_loss',
                    'target_hit': False,
                    'stop_hit': True
                }
        
        # If we reach here, trade wasn't closed by targets - close at last price
        last_candle = price_history[-1]
        final_minutes = last_candle['minutes_from_listing']
        hold_duration = final_minutes - entry_minutes
        
        return {
            'entry_price': entry_price,
            'exit_price': last_candle['close_price'],
            'entry_time': entry_time,
            'exit_time': last_candle['timestamp'],
            'entry_minutes': entry_minutes,
            'exit_minutes': final_minutes,
            'hold_duration_minutes': hold_duration,
            'hold_duration_hours': hold_duration / 60,
            'profit_pct': ((last_candle['close_price'] - entry_price) / entry_price) * 100,
            'exit_reason': 'end_of_data',
            'target_hit': False,
            'stop_hit': False
        }
    
    def backtest_strategy_chronological(self, profit_target_pct, stop_loss_pct, max_hold_hours):
        """
        Backtest strategy in chronological order (realistic trading simulation)
        
        Returns:
            dict: Aggregated results for this parameter combination
        """
        all_trades = []
        successful_trades = 0
        total_trades = 0
        
        print(f"    Backtesting {len(self.coins_data)} coins in chronological order...")
        
        for i, coin_data in enumerate(self.coins_data):
            symbol = coin_data['symbol']
            listing_time = coin_data['listing_timestamp']
            price_history = coin_data['price_data']['price_history']
            
            print(f"    Trade {i+1}: {symbol} listed on {listing_time.strftime('%Y-%m-%d %H:%M')}")
            
            trade_result = self.simulate_trade(
                price_history, 
                profit_target_pct, 
                stop_loss_pct, 
                max_hold_hours
            )
            
            if trade_result:
                trade_result['symbol'] = symbol
                trade_result['listing_timestamp'] = listing_time.isoformat()
                trade_result['trade_sequence'] = i + 1  # Order in which trade was taken
                trade_result['profit_target_pct'] = profit_target_pct
                trade_result['stop_loss_pct'] = stop_loss_pct
                trade_result['max_hold_hours'] = max_hold_hours
                trade_result['coin_name'] = coin_data['coin_name']
                
                all_trades.append(trade_result)
                total_trades += 1
                
                if trade_result['profit_pct'] > 0:
                    successful_trades += 1
                
                print(f"      Result: {trade_result['profit_pct']:.2f}% profit, "
                      f"exit: {trade_result['exit_reason']}, "
                      f"hold: {trade_result['hold_duration_hours']:.1f}h")
        
        if total_trades == 0:
            return None
        
        # Calculate aggregated metrics
        profits = [trade['profit_pct'] for trade in all_trades]
        win_rate = (successful_trades / total_trades) * 100
        avg_profit = np.mean(profits)
        median_profit = np.median(profits)
        max_profit = np.max(profits)
        min_profit = np.min(profits)
        std_profit = np.std(profits)
        
        # Calculate additional metrics
        winning_trades = [p for p in profits if p > 0]
        losing_trades = [p for p in profits if p <= 0]
        
        avg_win = np.mean(winning_trades) if winning_trades else 0
        avg_loss = np.mean(losing_trades) if losing_trades else 0
        
        # Risk-adjusted returns
        sharpe_ratio = avg_profit / std_profit if std_profit > 0 else 0
        
        # Exit reason analysis
        exit_reasons = {}
        for trade in all_trades:
            reason = trade['exit_reason']
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        # Hold time analysis
        hold_times = [trade['hold_duration_hours'] for trade in all_trades]
        avg_hold_time = np.mean(hold_times)
        
        # Calculate cumulative returns (realistic portfolio simulation)
        initial_capital = 2000.0  # Match your backtest initial capital
        current_capital = initial_capital
        
        for trade in all_trades:
            profit_pct = trade['profit_pct']
            # Apply the profit/loss to current capital
            current_capital = current_capital * (1 + profit_pct / 100)
        
        total_return_pct = ((current_capital - initial_capital) / initial_capital) * 100
        
        return {
            'profit_target_pct': profit_target_pct,
            'stop_loss_pct': stop_loss_pct,
            'max_hold_hours': max_hold_hours,
            'total_trades': total_trades,
            'successful_trades': successful_trades,
            'win_rate': round(win_rate, 2),
            'avg_profit_pct': round(avg_profit, 2),
            'median_profit_pct': round(median_profit, 2),
            'max_profit_pct': round(max_profit, 2),
            'min_profit_pct': round(min_profit, 2),
            'std_profit_pct': round(std_profit, 2),
            'avg_win_pct': round(avg_win, 2),
            'avg_loss_pct': round(avg_loss, 2),
            'sharpe_ratio': round(sharpe_ratio, 3),
            'avg_hold_time_hours': round(avg_hold_time, 2),
            'initial_capital': initial_capital,
            'final_capital': round(current_capital, 2),
            'total_return_pct': round(total_return_pct, 2),
            'profit_target_hits': exit_reasons.get('profit_target', 0),
            'stop_loss_hits': exit_reasons.get('stop_loss', 0),
            'max_hold_exits': exit_reasons.get('max_hold_time', 0),
            'end_of_data_exits': exit_reasons.get('end_of_data', 0),
            'trades_data': all_trades  # Store individual trades for detailed analysis
        }
    
    def run_grid_search(self, profit_targets, stop_losses, max_hold_hours_list):
        """
        Run grid search across all parameter combinations with chronological backtesting
        
        Args:
            profit_targets: List of profit target percentages
            stop_losses: List of stop loss percentages  
            max_hold_hours_list: List of max hold hours
            
        Returns:
            list: Results for all parameter combinations
        """
        results = []
        detailed_trades = []
        
        total_combinations = len(profit_targets) * len(stop_losses) * len(max_hold_hours_list)
        current_combination = 0
        
        print(f"Starting chronological grid search with {total_combinations} parameter combinations...")
        print(f"Profit targets: {profit_targets}")
        print(f"Stop losses: {stop_losses}")
        print(f"Max hold hours: {max_hold_hours_list}")
        print(f"Trading {len(self.coins_data)} coins in chronological order")
        print()
        
        for profit_target, stop_loss, max_hold in product(profit_targets, stop_losses, max_hold_hours_list):
            current_combination += 1
            print(f"Testing combination {current_combination}/{total_combinations}: "
                  f"Profit={profit_target}%, Stop={stop_loss}%, Hold={max_hold}h")
            
            result = self.backtest_strategy_chronological(profit_target, stop_loss, max_hold)
            
            if result:
                # Store aggregated results
                results.append({
                    'profit_target_pct': result['profit_target_pct'],
                    'stop_loss_pct': result['stop_loss_pct'],
                    'max_hold_hours': result['max_hold_hours'],
                    'total_trades': result['total_trades'],
                    'win_rate': result['win_rate'],
                    'avg_profit_pct': result['avg_profit_pct'],
                    'median_profit_pct': result['median_profit_pct'],
                    'max_profit_pct': result['max_profit_pct'],
                    'min_profit_pct': result['min_profit_pct'],
                    'std_profit_pct': result['std_profit_pct'],
                    'avg_win_pct': result['avg_win_pct'],
                    'avg_loss_pct': result['avg_loss_pct'],
                    'sharpe_ratio': result['sharpe_ratio'],
                    'avg_hold_time_hours': result['avg_hold_time_hours'],
                    'initial_capital': result['initial_capital'],
                    'final_capital': result['final_capital'],
                    'total_return_pct': result['total_return_pct'],
                    'profit_target_hits': result['profit_target_hits'],
                    'stop_loss_hits': result['stop_loss_hits'],
                    'max_hold_exits': result['max_hold_exits'],
                    'end_of_data_exits': result['end_of_data_exits']
                })
                
                # Store detailed trades
                detailed_trades.extend(result['trades_data'])
                
                print(f"  Final Results: {result['total_trades']} trades, "
                      f"{result['win_rate']}% win rate, "
                      f"{result['avg_profit_pct']}% avg profit, "
                      f"{result['total_return_pct']}% total return")
            else:
                print("  No valid trades found")
            
            print()
        
        return results, detailed_trades

def main():
    # Initialize backtester
    backtester = GridSearchBacktester(PRICE_DATA_FOLDER, INPUT_JSON)
    
    if not backtester.coins_data:
        print("No coins data found. Please run map_bybit_price.py first.")
        return
    
    # Define parameter ranges for grid search
    profit_targets = [5, 10, 15, 20, 25, 30, 50, 100]  # Profit target percentages
    stop_losses = [2, 5, 10, 15, 20, 25]  # Stop loss percentages
    max_hold_hours = [1, 2, 4, 6, 12, 24, 48]  # Maximum hold times in hours
    
    print(f"Starting chronological backtest with {len(backtester.coins_data)} coins")
    print("=" * 60)
    
    # Run grid search
    start_time = time.time()
    results, detailed_trades = backtester.run_grid_search(profit_targets, stop_losses, max_hold_hours)
    end_time = time.time()
    
    if not results:
        print("No results generated. Check your price data.")
        return
    
    # Save results to CSV
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('total_return_pct', ascending=False)  # Sort by total return
    results_df.to_csv(BACKTEST_RESULTS_CSV, index=False)
    
    # Save detailed trades
    detailed_df = pd.DataFrame(detailed_trades)
    detailed_df = detailed_df.sort_values('trade_sequence')  # Sort by chronological order
    detailed_df.to_csv(DETAILED_TRADES_CSV, index=False)
    
    print("=" * 60)
    print("CHRONOLOGICAL GRID SEARCH COMPLETED!")
    print(f"Time taken: {(end_time - start_time):.1f} seconds")
    print(f"Total parameter combinations tested: {len(results)}")
    print(f"Results saved to: {BACKTEST_RESULTS_CSV}")
    print(f"Detailed trades saved to: {DETAILED_TRADES_CSV}")
    print()
    
    # Display top 10 results
    print("TOP 10 PARAMETER COMBINATIONS (by total return):")
    print("-" * 120)
    top_10 = results_df.head(10)
    
    for idx, row in top_10.iterrows():
        print(f"Rank {list(top_10.index).index(idx) + 1}: "
              f"Profit={row['profit_target_pct']}%, Stop={row['stop_loss_pct']}%, "
              f"Hold={row['max_hold_hours']}h | "
              f"Win Rate: {row['win_rate']}%, Avg Profit: {row['avg_profit_pct']}%, "
              f"Total Return: {row['total_return_pct']}%, Trades: {row['total_trades']}")
    
    print()
    print("Analysis complete! Check the CSV files for detailed results.")

if __name__ == '__main__':
    main() 