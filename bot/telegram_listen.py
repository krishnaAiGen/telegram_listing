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
    def __init__(self, timing_mode=1):
        # Telegram credentials
        self.api_id = int(os.getenv('TELEGRAM_API_ID'))
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone_number = os.getenv('TELEGRAM_PHONE_NUMBER')
        self.channel_username = os.getenv('TELEGRAM_CHANNEL_USERNAME')  # e.g., '@channelname' or 'channelname'
        
        # Initialize Telegram client
        self.telegram_client = TelegramClient('trading_session', self.api_id, self.api_hash)
        
        # Initialize trading bot with timing mode
        self.trading_bot = TradingBot(timing_mode=timing_mode)
        
        # Initialize Slack notifier
        self.slack_notifier = SlackNotifier()
        
        # Track processed messages
        self.processed_messages = set()
        
        # Regex patterns for symbol extraction
        self.symbol_patterns = [
            r'\$([A-Z]{2,10})(?:\s*,|\s+listed)',  # $MYX, or $SPK listed
            r'\$([A-Z]{2,10})\b',                  # Any $SYMBOL format
            r'\b([A-Z]{2,10})\s+listed\s+on\s+binance\s+futures',  # SYMBOL listed on binance futures
            r'\b([A-Z]{2,10})\s+.*binance.*futures',               # SYMBOL ... binance ... futures
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
                        return
                    
                    # Send symbol extraction notification to Slack (ONLY when symbol is found)
                    symbol_message = {
                        "🎯 SYMBOL EXTRACTED": "✅ EXECUTING IN 2 SECONDS",
                        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Symbol": symbol,
                        "Trading Pair": trading_symbol,
                        "Original Message": original_text,
                        "Status": "Will attempt execution in 2 seconds, queue if failed"
                    }
                    self.slack_notifier.post_to_slack(symbol_message)
                    
                    # Send to trading bot (will be queued for timed execution)
                    await self.trading_bot.execute_trade(trading_symbol, original_text)
                else:
                    logger.warning("No valid symbol found in message")
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
                    # Filter out common words that are not symbols
                    excluded_words = {'LISTED', 'ON', 'BINANCE', 'FUTURES', 'AND', 'THE', 'FOR', 'TO', 'IN', 'AT', 'IS', 'ARE'}
                    
                    for match in matches:
                        symbol = match.upper().strip()
                        # Validate symbol (2-10 characters, letters only, not excluded words)
                        if (2 <= len(symbol) <= 10 and 
                            symbol.isalpha() and 
                            symbol not in excluded_words):
                            if len(matches) > 1:
                                logger.info(f"Multiple symbols detected, using first one: {symbol}")
                            return symbol
            return None
        except Exception as e:
            error_msg = f"Error extracting symbol from text: {e}"
            logger.error(error_msg)
            self.slack_notifier.post_error_to_slack(f"Symbol extraction error: {e}")
            return None

async def main():
    """Main function to run the Telegram listener"""
    try:
        # Get timing mode from environment variable or default to 1
        timing_mode = int(os.getenv('TIMING_MODE', '1'))
        if timing_mode not in [1, 10]:
            logger.warning(f"Invalid TIMING_MODE {timing_mode}, defaulting to 1")
            timing_mode = 1
        
        logger.info(f"Starting with timing mode: {timing_mode} ({'every minute' if timing_mode == 1 else 'every 10 minutes'} at :02 seconds)")
        
        listener = TelegramListener(timing_mode=timing_mode)
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