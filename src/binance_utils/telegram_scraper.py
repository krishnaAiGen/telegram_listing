from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from datetime import datetime, timezone
import pandas as pd
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

class TelegramScraper:
    def __init__(self):
        # Get these values from https://my.telegram.org
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        
        if not self.api_id or not self.api_hash:
            raise ValueError("Please set TELEGRAM_API_ID and TELEGRAM_API_HASH in your .env file")
            
        self.client = TelegramClient('anon', self.api_id, self.api_hash)

    async def connect(self):
        """Connect and authenticate with Telegram"""
        if not self.client.is_connected():
            await self.client.connect()
            
        if not await self.client.is_user_authorized():
            print("First time login. Please enter your phone number and the verification code sent to your Telegram app.")
            await self.client.start()

    async def scrape_messages(self, channel_username, start_date, end_date):
        """
        Scrape messages from a Telegram channel/group between start_date and end_date
        
        Args:
            channel_username (str): Username or invite link of the channel/group
            start_date (str): Start date in format 'YYYY-MM-DD'
            end_date (str): End date in format 'YYYY-MM-DD'
            
        Returns:
            pd.DataFrame: DataFrame containing the scraped messages
        """
        try:
            await self.connect()

            # Convert dates to datetime objects (timezone-aware)
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)

            messages = []
            offset_id = 0
            total_messages = 0
            total_count_limit = 0  # Set to 0 for no limit

            while True:
                history = await self.client(GetHistoryRequest(
                    peer=channel_username,
                    offset_id=offset_id,
                    offset_date=None,
                    add_offset=0,
                    limit=100,
                    max_id=0,
                    min_id=0,
                    hash=0
                ))

                if not history.messages:
                    break

                messages.extend(history.messages)
                offset_id = messages[-1].id
                total_messages = len(messages)

                if total_count_limit != 0 and total_messages >= total_count_limit:
                    break

            # Process messages
            data = []
            for message in messages:
                message_date = message.date
                if start_datetime <= message_date <= end_datetime:
                    data.append({
                        'date': message_date,
                        'message_id': message.id,
                        'message': message.message,
                        'views': message.views if hasattr(message, 'views') else None,
                        'forwards': message.forwards if hasattr(message, 'forwards') else None
                    })

            # Create DataFrame
            df = pd.DataFrame(data)
            return df
            
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            raise

    async def close(self):
        """Close the Telegram client connection"""
        await self.client.disconnect()

async def main():
    try:
        scraper = TelegramScraper()
        # Replace 'channel_username' with the actual username or invite link of the channel/group
        # For example: '@trading_signals' or 'https://t.me/trading_signals'
        channel = input("Enter the channel username or invite link: ")
        start_date = input("Enter start date (YYYY-MM-DD): ")
        end_date = input("Enter end date (YYYY-MM-DD): ")
        
        df = await scraper.scrape_messages(channel, start_date, end_date)
        print("\nScraped Messages:")
        print(df)
        
        # Optionally save to CSV
        save_csv = input("\nDo you want to save the results to a CSV file? (y/n): ")
        if save_csv.lower() == 'y':
            filename = f"telegram_messages_{start_date}_to_{end_date}.csv"
            df.to_csv(filename, index=False)
            print(f"Data saved to {filename}")
            
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        await scraper.close()

if __name__ == "__main__":
    asyncio.run(main())