import os
import asyncio
import logging
import math
import json
from datetime import datetime, timedelta
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET
from dotenv import load_dotenv
from slack_notifier import SlackNotifier

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        # Binance credentials
        self.binance_api_key = os.getenv('BINANCE_API_KEY')
        self.binance_api_secret = os.getenv('BINANCE_API_SECRET')
        
        # Trading parameters
        self.trade_amount = float(os.getenv('TRADE_AMOUNT', '1000'))  # Default $1000
        self.profit_target_pct = float(os.getenv('PROFIT_TARGET_PCT', '15'))  # 15%
        self.stop_loss_pct = float(os.getenv('STOP_LOSS_PCT', '2'))  # 2%
        self.leverage = int(os.getenv('LEVERAGE', '3'))  # 3x leverage
        self.max_retry_minutes = int(os.getenv('MAX_RETRY_MINUTES', '1440'))  # 24 hours
        self.max_hold_hours = 2  # Maximum hold time: 2 hours
        
        # Initialize Binance client
        self.binance_client = Client(self.binance_api_key, self.binance_api_secret, tld='com')
        
        # Initialize Slack notifier
        self.slack_notifier = SlackNotifier()
        
        # Track retry attempts and active trades
        self.retry_attempts = {}  # symbol -> {'attempts': count, 'last_attempt': datetime}
        self.active_trades = {}   # symbol -> trade_info
        
        # Trade logging file
        self.trade_log_file = 'trades.json'
        
        logger.info("TradingBot initialized")
        logger.info(f"Trade amount: ${self.trade_amount}")
        logger.info(f"Profit target: {self.profit_target_pct}%")
        logger.info(f"Stop loss: {self.stop_loss_pct}%")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info(f"Max hold time: {self.max_hold_hours} hours")
    
    def load_trades_log(self):
        """Load existing trades from JSON file"""
        try:
            if os.path.exists(self.trade_log_file):
                with open(self.trade_log_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading trades log: {e}")
            return []
    
    def save_trade_to_log(self, trade_data):
        """Save trade data to JSON file"""
        try:
            trades = self.load_trades_log()
            trades.append(trade_data)
            
            with open(self.trade_log_file, 'w') as f:
                json.dump(trades, f, indent=2, default=str)
            
            logger.info(f"Trade logged to {self.trade_log_file}")
            
        except Exception as e:
            error_msg = f"Error saving trade to log: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(error_msg)
    
    async def test_connection(self):
        """Test Binance connection"""
        try:
            account_info = self.binance_client.get_account()
            logger.info("Binance connection successful")
            return True
        except Exception as e:
            error_msg = f"Binance connection failed: {e}"
            logger.error(error_msg)
            # Send error to Slack
            self.slack_notifier.post_error_to_slack(error_msg)
            return False
    
    async def execute_trade(self, symbol, original_message):
        """Execute a long trade for the given symbol"""
        try:
            logger.info(f"Attempting to execute LONG trade for {symbol}")
            
            # Try to place the trade
            trade_result = await self.place_long_trade(symbol, original_message)
            
            if trade_result['success']:
                logger.info(f"✅ Trade executed successfully for {symbol}")
                
                # Add to active trades for monitoring
                self.active_trades[symbol] = {
                    'entry_time': datetime.now(),
                    'entry_price': trade_result['entry_price'],
                    'quantity': trade_result['quantity'],
                    'stop_loss_price': trade_result['stop_loss_price'],
                    'take_profit_price': trade_result['take_profit_price'],
                    'original_message': original_message,
                    'stop_loss_order_id': trade_result.get('stop_loss_order_id'),
                    'take_profit_order_id': trade_result.get('take_profit_order_id')
                }
                
                # Log trade entry to JSON
                trade_log_entry = {
                    'trade_id': f"{symbol}_{int(datetime.now().timestamp())}",
                    'symbol': symbol,
                    'action': 'BUY',
                    'entry_time': datetime.now().isoformat(),
                    'entry_price': trade_result['entry_price'],
                    'quantity': trade_result['quantity'],
                    'stop_loss_price': trade_result['stop_loss_price'],
                    'take_profit_price': trade_result['take_profit_price'],
                    'leverage': self.leverage,
                    'trade_amount': self.trade_amount,
                    'original_message': original_message,
                    'status': 'ACTIVE',
                    'max_hold_until': (datetime.now() + timedelta(hours=self.max_hold_hours)).isoformat()
                }
                self.save_trade_to_log(trade_log_entry)
                
                # Send success notification to Slack
                trade_info = {
                    'success': True,
                    'symbol': symbol,
                    'entry_price': trade_result.get('entry_price'),
                    'quantity': trade_result.get('quantity'),
                    'stop_loss_price': trade_result.get('stop_loss_price'),
                    'take_profit_price': trade_result.get('take_profit_price'),
                    'stop_loss_pct': self.stop_loss_pct,
                    'profit_target_pct': self.profit_target_pct,
                    'leverage': self.leverage,
                    'trade_amount': self.trade_amount,
                    'original_message': original_message,
                    'max_hold_time': f"{self.max_hold_hours} hours"
                }
                self.slack_notifier.post_trade_notification(trade_info)
                
                # Remove from retry list if it was there
                if symbol in self.retry_attempts:
                    del self.retry_attempts[symbol]
            else:
                logger.warning(f"❌ Trade failed for {symbol} - adding to retry list")
                
                # Send failure notification to Slack
                trade_info = {
                    'success': False,
                    'symbol': symbol,
                    'error': trade_result.get('error', 'Unknown error'),
                    'original_message': original_message,
                    'added_to_retry': True
                }
                self.slack_notifier.post_trade_notification(trade_info)
                
                # Add to retry list
                self.retry_attempts[symbol] = {
                    'attempts': 1,
                    'last_attempt': datetime.now(),
                    'original_message': original_message
                }
                
        except Exception as e:
            error_msg = f"Error executing trade for {symbol}: {e}"
            logger.error(error_msg)
            
            # Send error to Slack
            self.slack_notifier.post_error_to_slack(f"Trade execution error for {symbol}: {e}")
    
    async def place_long_trade(self, symbol, original_message=""):
        """Place a long trade with stop loss and take profit"""
        try:
            # Check if symbol exists and is tradeable
            try:
                ticker = self.binance_client.get_symbol_ticker(symbol=symbol)
                current_price = float(ticker['price'])
                logger.info(f"Current price for {symbol}: ${current_price}")
            except Exception as e:
                error_msg = f"Symbol {symbol} not found or not tradeable: {e}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            # Calculate quantity based on trade amount
            quantity = self.calculate_quantity(symbol, current_price)
            if not quantity:
                error_msg = f"Could not calculate quantity for {symbol}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            # Set leverage
            try:
                self.binance_client.futures_change_leverage(symbol=symbol, leverage=self.leverage)
                logger.info(f"Leverage set to {self.leverage}x for {symbol}")
            except Exception as e:
                logger.warning(f"Could not set leverage for {symbol}: {e}")
            
            # Place market buy order
            market_order = self.binance_client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )
            
            logger.info(f"Market order placed: {market_order}")
            
            # Get actual fill price
            fill_price = float(self.binance_client.get_symbol_ticker(symbol=symbol)['price'])
            
            # Calculate stop loss and take profit prices
            stop_loss_price = fill_price * (1 - self.stop_loss_pct / 100)
            take_profit_price = fill_price * (1 + self.profit_target_pct / 100)
            
            # Round prices based on symbol precision
            precision = self.get_price_precision(fill_price)
            stop_loss_price = round(stop_loss_price, precision)
            take_profit_price = round(take_profit_price, precision)
            
            # Place stop loss order
            stop_loss_order = self.binance_client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type='STOP_MARKET',
                stopPrice=stop_loss_price,
                closePosition='true'
            )
            
            logger.info(f"Stop loss order placed at ${stop_loss_price}")
            
            # Place take profit order
            take_profit_order = self.binance_client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type='LIMIT',
                price=take_profit_price,
                quantity=quantity,
                timeInForce='GTC'
            )
            
            logger.info(f"Take profit order placed at ${take_profit_price}")
            
            # Log trade summary
            logger.info(f"""
            🎯 TRADE EXECUTED FOR {symbol}
            Entry Price: ${fill_price}
            Quantity: {quantity}
            Stop Loss: ${stop_loss_price} (-{self.stop_loss_pct}%)
            Take Profit: ${take_profit_price} (+{self.profit_target_pct}%)
            Leverage: {self.leverage}x
            Trade Amount: ${self.trade_amount}
            Max Hold Time: {self.max_hold_hours} hours
            """)
            
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
            error_msg = f"Error placing trade for {symbol}: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def close_position_at_market(self, symbol, reason="MAX_HOLD_TIME"):
        """Close position at market price"""
        try:
            # Get current position
            positions = self.binance_client.futures_position_information(symbol=symbol)
            position_amt = 0
            
            for pos in positions:
                if pos['symbol'] == symbol:
                    position_amt = float(pos['positionAmt'])
                    break
            
            if position_amt == 0:
                logger.info(f"No open position found for {symbol}")
                return None
            
            # Cancel existing orders
            try:
                self.binance_client.futures_cancel_all_open_orders(symbol=symbol)
                logger.info(f"Cancelled all open orders for {symbol}")
            except Exception as e:
                logger.warning(f"Error cancelling orders for {symbol}: {e}")
            
            # Close position at market price
            close_order = self.binance_client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL if position_amt > 0 else SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=abs(position_amt)
            )
            
            # Get exit price
            exit_price = float(self.binance_client.get_symbol_ticker(symbol=symbol)['price'])
            
            logger.info(f"Position closed for {symbol} at ${exit_price} due to {reason}")
            
            return {
                'exit_price': exit_price,
                'quantity': abs(position_amt),
                'reason': reason,
                'order_id': close_order.get('orderId')
            }
            
        except Exception as e:
            error_msg = f"Error closing position for {symbol}: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(error_msg)
            return None
    
    async def monitor_active_trades(self):
        """Monitor active trades for 2-hour time limit"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = datetime.now()
                trades_to_close = []
                
                for symbol, trade_info in self.active_trades.items():
                    entry_time = trade_info['entry_time']
                    time_elapsed = current_time - entry_time
                    
                    # Check if 2 hours have passed
                    if time_elapsed.total_seconds() >= (self.max_hold_hours * 3600):
                        logger.info(f"Max hold time reached for {symbol} - closing position")
                        trades_to_close.append(symbol)
                
                # Close positions that have exceeded max hold time
                for symbol in trades_to_close:
                    trade_info = self.active_trades[symbol]
                    
                    # Close position at market
                    close_result = await self.close_position_at_market(symbol, "MAX_HOLD_TIME")
                    
                    if close_result:
                        # Calculate P&L
                        entry_price = trade_info['entry_price']
                        exit_price = close_result['exit_price']
                        quantity = close_result['quantity']
                        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                        pnl_amount = (exit_price - entry_price) * quantity
                        
                        # Update trade log
                        trade_log_entry = {
                            'trade_id': f"{symbol}_{int(trade_info['entry_time'].timestamp())}",
                            'symbol': symbol,
                            'action': 'SELL',
                            'entry_time': trade_info['entry_time'].isoformat(),
                            'exit_time': current_time.isoformat(),
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'quantity': quantity,
                            'leverage': self.leverage,
                            'pnl_percentage': round(pnl_pct, 2),
                            'pnl_amount': round(pnl_amount, 2),
                            'hold_duration_minutes': int(time_elapsed.total_seconds() / 60),
                            'exit_reason': 'MAX_HOLD_TIME',
                            'status': 'CLOSED',
                            'original_message': trade_info.get('original_message', '')
                        }
                        self.save_trade_to_log(trade_log_entry)
                        
                        # Also update the original BUY trade status to CLOSED
                        self.update_trade_status_to_closed(symbol, "MAX_HOLD_TIME")
                        
                        # Send Slack notification
                        close_notification = {
                            "🕐 MAX HOLD TIME": "⏰ POSITION CLOSED",
                            "Time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "Symbol": symbol,
                            "Entry Price": f"${entry_price}",
                            "Exit Price": f"${exit_price}",
                            "Quantity": quantity,
                            "Hold Duration": f"{int(time_elapsed.total_seconds() / 3600)}h {int((time_elapsed.total_seconds() % 3600) / 60)}m",
                            "P&L %": f"{pnl_pct:+.2f}%",
                            "P&L Amount": f"${pnl_amount:+.2f}",
                            "Reason": "Maximum 2-hour hold time reached"
                        }
                        self.slack_notifier.post_to_slack(close_notification)
                    
                    # Remove from active trades
                    del self.active_trades[symbol]
                    
            except Exception as e:
                error_msg = f"Error in trade monitoring: {e}"
                logger.error(error_msg)
                self.slack_notifier.post_error_to_slack(error_msg)
    
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
            # Send error to Slack
            self.slack_notifier.post_error_to_slack(f"Quantity calculation error for {symbol}: {e}")
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
    
    async def retry_scheduler(self):
        """Scheduler to retry failed trades every minute"""
        # Start trade monitoring and completion checking in parallel
        asyncio.create_task(self.monitor_active_trades())
        asyncio.create_task(self.check_trade_completion_status())
        
        while True:
            try:
                await asyncio.sleep(60)  # Wait 1 minute
                
                current_time = datetime.now()
                symbols_to_remove = []
                
                for symbol, retry_info in self.retry_attempts.items():
                    # Check if max retry time exceeded
                    time_elapsed = current_time - retry_info['last_attempt']
                    
                    if time_elapsed.total_seconds() / 60 >= self.max_retry_minutes:
                        logger.info(f"Max retry time exceeded for {symbol} - removing from retry list")
                        
                        # Send max retry notification to Slack
                        self.slack_notifier.post_error_to_slack(
                            f"Max retry time exceeded for {symbol}. Stopped retrying after {self.max_retry_minutes} minutes."
                        )
                        
                        symbols_to_remove.append(symbol)
                        continue
                    
                    # Attempt retry
                    logger.info(f"Retrying trade for {symbol} (attempt {retry_info['attempts'] + 1})")
                    
                    trade_result = await self.place_long_trade(symbol, retry_info.get('original_message', ''))
                    
                    if trade_result['success']:
                        logger.info(f"✅ Retry successful for {symbol}")
                        
                        # Add to active trades for monitoring
                        self.active_trades[symbol] = {
                            'entry_time': datetime.now(),
                            'entry_price': trade_result['entry_price'],
                            'quantity': trade_result['quantity'],
                            'stop_loss_price': trade_result['stop_loss_price'],
                            'take_profit_price': trade_result['take_profit_price'],
                            'original_message': retry_info.get('original_message', ''),
                            'stop_loss_order_id': trade_result.get('stop_loss_order_id'),
                            'take_profit_order_id': trade_result.get('take_profit_order_id')
                        }
                        
                        # Log successful retry trade
                        trade_log_entry = {
                            'trade_id': f"{symbol}_{int(datetime.now().timestamp())}",
                            'symbol': symbol,
                            'action': 'BUY',
                            'entry_time': datetime.now().isoformat(),
                            'entry_price': trade_result['entry_price'],
                            'quantity': trade_result['quantity'],
                            'stop_loss_price': trade_result['stop_loss_price'],
                            'take_profit_price': trade_result['take_profit_price'],
                            'leverage': self.leverage,
                            'trade_amount': self.trade_amount,
                            'original_message': retry_info.get('original_message', ''),
                            'status': 'ACTIVE',
                            'retry_attempt': retry_info['attempts'] + 1,
                            'max_hold_until': (datetime.now() + timedelta(hours=self.max_hold_hours)).isoformat()
                        }
                        self.save_trade_to_log(trade_log_entry)
                        
                        # Send retry success notification to Slack
                        self.slack_notifier.post_retry_notification(
                            symbol, 
                            retry_info['attempts'] + 1, 
                            success=True
                        )
                        
                        # Send successful trade notification
                        trade_info = {
                            'success': True,
                            'symbol': symbol,
                            'entry_price': trade_result.get('entry_price'),
                            'quantity': trade_result.get('quantity'),
                            'stop_loss_price': trade_result.get('stop_loss_price'),
                            'take_profit_price': trade_result.get('take_profit_price'),
                            'stop_loss_pct': self.stop_loss_pct,
                            'profit_target_pct': self.profit_target_pct,
                            'leverage': self.leverage,
                            'trade_amount': self.trade_amount,
                            'original_message': retry_info.get('original_message', ''),
                            'max_hold_time': f"{self.max_hold_hours} hours"
                        }
                        self.slack_notifier.post_trade_notification(trade_info)
                        
                        symbols_to_remove.append(symbol)
                    else:
                        # Update retry info
                        retry_info['attempts'] += 1
                        retry_info['last_attempt'] = current_time
                        logger.info(f"❌ Retry failed for {symbol} (attempt {retry_info['attempts']})")
                        
                        # Send retry failure notification to Slack
                        self.slack_notifier.post_retry_notification(
                            symbol, 
                            retry_info['attempts'], 
                            success=False
                        )
                
                # Remove successful or expired symbols
                for symbol in symbols_to_remove:
                    del self.retry_attempts[symbol]
                    
            except Exception as e:
                error_msg = f"Error in retry scheduler: {e}"
                logger.error(error_msg)
                # Send error to Slack
                self.slack_notifier.post_error_to_slack(f"Retry scheduler error: {e}")
    
    def has_active_trade(self):
        """Check if there's currently an active trade"""
        try:
            trades = self.load_trades_log()
            for trade in reversed(trades):  # Check most recent trades first
                if trade.get('status') == 'ACTIVE':
                    logger.info(f"Found active trade: {trade.get('symbol')} at {trade.get('entry_time')}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking active trades: {e}")
            return False
    
    def update_trade_status_to_closed(self, symbol, exit_reason="TARGET_OR_STOPLOSS_HIT"):
        """Update trade status from ACTIVE to CLOSED in trades.json"""
        try:
            trades = self.load_trades_log()
            updated = False
            
            for trade in reversed(trades):  # Check most recent trades first
                if (trade.get('symbol') == symbol and 
                    trade.get('status') == 'ACTIVE' and 
                    trade.get('action') == 'BUY'):
                    
                    # Update the trade status
                    trade['status'] = 'CLOSED'
                    trade['exit_time'] = datetime.now().isoformat()
                    trade['exit_reason'] = exit_reason
                    updated = True
                    
                    logger.info(f"Updated trade status to CLOSED for {symbol} - Reason: {exit_reason}")
                    break
            
            if updated:
                # Save updated trades back to file
                with open(self.trade_log_file, 'w') as f:
                    json.dump(trades, f, indent=2, default=str)
                
                # Send status update notification to Slack
                status_message = {
                    "📊 TRADE STATUS UPDATE": "✅ CLOSED",
                    "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Symbol": symbol,
                    "Previous Status": "ACTIVE",
                    "New Status": "CLOSED",
                    "Reason": exit_reason
                }
                self.slack_notifier.post_to_slack(status_message)
                
                return True
            else:
                logger.warning(f"No active trade found to update for {symbol}")
                return False
                
        except Exception as e:
            error_msg = f"Error updating trade status for {symbol}: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(error_msg)
            return False

    async def check_trade_completion_status(self):
        """Check every 10 minutes if trades have hit target or stop loss"""
        while True:
            try:
                await asyncio.sleep(600)  # Wait 10 minutes
                
                # Get all active trades from JSON
                trades = self.load_trades_log()
                active_trades = [trade for trade in trades if trade.get('status') == 'ACTIVE']
                
                for trade in active_trades:
                    symbol = trade.get('symbol')
                    if not symbol:
                        continue
                    
                    try:
                        # Check if position still exists
                        positions = self.binance_client.futures_position_information(symbol=symbol)
                        position_amt = 0
                        
                        for pos in positions:
                            if pos['symbol'] == symbol:
                                position_amt = float(pos['positionAmt'])
                                break
                        
                        # If position is 0, the trade was closed (target or stop loss hit)
                        if position_amt == 0:
                            logger.info(f"Position closed for {symbol} - updating status")
                            self.update_trade_status_to_closed(symbol, "TARGET_OR_STOPLOSS_HIT")
                            
                            # Remove from active trades tracking if it exists
                            if symbol in self.active_trades:
                                del self.active_trades[symbol]
                        
                    except Exception as e:
                        logger.warning(f"Error checking position for {symbol}: {e}")
                        continue
                
            except Exception as e:
                error_msg = f"Error in trade completion status check: {e}"
                logger.error(error_msg)
                self.slack_notifier.post_error_to_slack(error_msg) 