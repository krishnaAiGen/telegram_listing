import os
import re
import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient, events
from dotenv import load_dotenv
from bot import TradingBot
from slack_notifier import SlackNotifier

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelegramListener:
    def __init__(self):
        # Telegram credentials
        self.api_id = int(os.getenv('TELEGRAM_API_ID'))
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone_number = os.getenv('TELEGRAM_PHONE_NUMBER')
        self.channel_username = os.getenv('TELEGRAM_CHANNEL_USERNAME')  # e.g., '@channelname' or 'channelname'
        
        # Initialize Telegram client
        self.telegram_client = TelegramClient('trading_session', self.api_id, self.api_hash)
        
        # Initialize trading bot
        self.trading_bot = TradingBot()
        
        # Initialize Slack notifier
        self.slack_notifier = SlackNotifier()
        
        # Track processed messages
        self.processed_messages = set()
        
        # Regex patterns for symbol extraction
        self.symbol_patterns = [
            r'\$([A-Z]{2,10})\s+listed\s+on\s+binance\s+futures',  # $LA listed on Binance futures
            r'([A-Z]{2,10})\s+listed\s+on\s+binance\s+futures',   # LA listed on Binance futures
            r'\$([A-Z]{2,10})\s+.*binance.*futures',              # $LA ... binance ... futures
            r'([A-Z]{2,10})\s+.*binance.*futures',                # LA ... binance ... futures
        ]
        
        logger.info("TelegramListener initialized")
        logger.info(f"Monitoring channel: {self.channel_username}")
    
    async def start(self):
        """Start the Telegram client and begin monitoring"""
        try:
            await self.telegram_client.start(phone=self.phone_number)
            logger.info("Telegram client started successfully")
            
            # Send startup notification to Slack
            startup_message = {
                "🤖 BOT STARTED": "✅ ONLINE",
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Status": "Telegram listener is now active",
                "Monitoring": self.channel_username,
                "Ready": "Waiting for Binance futures listing messages"
            }
            self.slack_notifier.post_to_slack(startup_message)
            
        except Exception as e:
            error_msg = f"Failed to start Telegram client: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(error_msg)
            return
        
        # Test trading bot connection
        if not await self.trading_bot.test_connection():
            logger.error("Trading bot connection failed - exiting")
            return
        
        try:
            # Register message handler
            @self.telegram_client.on(events.NewMessage(chats=self.channel_username))
            async def handle_new_message(event):
                await self.process_message(event)
            
            logger.info("Message handler registered. Listening for messages...")
            
            # Start retry scheduler in trading bot
            asyncio.create_task(self.trading_bot.retry_scheduler())
            
            # Keep the client running
            await self.telegram_client.run_until_disconnected()
            
        except Exception as e:
            error_msg = f"Error in Telegram listener main loop: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(error_msg)
    
    async def process_message(self, event):
        """Process incoming Telegram messages"""
        try:
            message_text = event.message.message.lower()
            original_text = event.message.message
            message_id = event.message.id
            
            # Skip if already processed
            if message_id in self.processed_messages:
                return
            
            logger.info(f"New message: {original_text}")
            
            # Check if message contains 'binance' and 'futures'
            if 'binance' in message_text and 'futures' in message_text:
                logger.info("Message contains 'binance' and 'futures' - analyzing...")
                
                # Send message detection notification to Slack
                detection_message = {
                    "📨 MESSAGE DETECTED": "🔍 ANALYZING",
                    "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Channel": self.channel_username,
                    "Message": original_text,
                    "Status": "Checking for valid symbol..."
                }
                self.slack_notifier.post_to_slack(detection_message)
                
                # Extract symbol using regex (only first one)
                symbol = self.extract_symbol(original_text)
                
                if symbol:
                    logger.info(f"Symbol extracted: {symbol}")
                    self.processed_messages.add(message_id)
                    
                    # Create trading symbol (add USDT)
                    trading_symbol = f"{symbol}USDT"
                    
                    # Check if there's already an active trade
                    if self.trading_bot.has_active_trade():
                        logger.info(f"Active trade exists - ignoring new trade for {trading_symbol}")
                        
                        # Send active trade notification to Slack
                        active_trade_message = {
                            "⚠️ TRADE IGNORED": "🔄 ACTIVE TRADE EXISTS",
                            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Symbol": symbol,
                            "Trading Pair": trading_symbol,
                            "Reason": "Another trade is currently active",
                            "Action": "Message ignored - no retry",
                            "Original Message": original_text
                        }
                        self.slack_notifier.post_to_slack(active_trade_message)
                        return
                    
                    # Send symbol extraction notification to Slack
                    symbol_message = {
                        "🎯 SYMBOL EXTRACTED": "✅ VALID",
                        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Symbol": symbol,
                        "Trading Pair": trading_symbol,
                        "Action": "Sending to trading bot...",
                        "Original Message": original_text
                    }
                    self.slack_notifier.post_to_slack(symbol_message)
                    
                    # Send to trading bot
                    await self.trading_bot.execute_trade(trading_symbol, original_text)
                else:
                    logger.warning("No valid symbol found in message")
                    
                    # Send no symbol notification to Slack
                    no_symbol_message = {
                        "⚠️ NO SYMBOL FOUND": "❌ INVALID",
                        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Message": original_text,
                        "Reason": "No valid symbol pattern matched",
                        "Action": "Message ignored"
                    }
                    self.slack_notifier.post_to_slack(no_symbol_message)
            else:
                logger.debug("Message doesn't contain required keywords")
                
        except Exception as e:
            error_msg = f"Error processing message: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(f"Message processing error: {e}")
    
    def extract_symbol(self, text):
        """Extract the FIRST coin symbol from message using regex patterns"""
        try:
            for pattern in self.symbol_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    # Return only the FIRST symbol found
                    first_symbol = matches[0].upper()
                    # Validate symbol (2-10 characters, letters only)
                    if 2 <= len(first_symbol) <= 10 and first_symbol.isalpha():
                        logger.info(f"Multiple symbols detected, using first one: {first_symbol}")
                        return first_symbol
            return None
        except Exception as e:
            error_msg = f"Error extracting symbol from text: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(f"Symbol extraction error: {e}")
            return None

async def main():
    """Main function to run the Telegram listener"""
    try:
        listener = TelegramListener()
        await listener.start()
    except KeyboardInterrupt:
        logger.info("Telegram listener stopped by user")
        
        # Send shutdown notification to Slack
        slack_notifier = SlackNotifier()
        shutdown_message = {
            "🤖 BOT STOPPED": "⏹️ OFFLINE",
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Reason": "Manual shutdown by user",
            "Status": "Bot is now offline"
        }
        slack_notifier.post_to_slack(shutdown_message)
        
    except Exception as e:
        error_msg = f"Telegram listener crashed: {e}"
        logger.error(error_msg)
        
        # Send crash notification to Slack
        slack_notifier = SlackNotifier()
        slack_notifier.post_error_to_slack(f"CRITICAL: Telegram listener crashed - {e}")

if __name__ == "__main__":
    print("📱 Telegram Listener Starting...")
    print("Press Ctrl+C to stop")
    asyncio.run(main()) 