#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Slack Notifier for Trading Bot
Sends trade notifications and error messages to Slack channel
"""

import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SlackNotifier:
    def __init__(self):
        """Initialize Slack notifier with webhook URL from environment variables"""
        try:
            # Get webhook URL from environment variables
            self.webhook_url = os.getenv('SLACK_WEBHOOK_URL')
            
            if self.webhook_url:
                print("Slack notifier initialized successfully")
            else:
                print("Warning: SLACK_WEBHOOK_URL not found in environment variables")
                
        except Exception as e:
            print(f"Error initializing Slack notifier: {e}")
            self.webhook_url = None

    def post_to_slack(self, message):
        """Post a message dictionary to Slack channel"""
        if not self.webhook_url:
            print("Slack webhook URL not configured")
            return False
            
        try:
            # Convert message dictionary to a string with each key-value on a new line
            formatted_message = "\n".join([f"{key}: {value}" for key, value in message.items()])
            
            # Create the payload to send to Slack
            payload = {
                "text": formatted_message  # Message to send to Slack
            }
            
            # Send a POST request to the Slack webhook URL
            response = requests.post(self.webhook_url, json=payload)
        
            # Check if the request was successful
            if response.status_code == 200:
                print("Message posted successfully to Slack")
                return True
            else:
                print(f"Failed to post message: {response.status_code}, {response.text}")
                return False
        
        except Exception as e:
            print(f"Error posting message to Slack: {e}")
            return False
            
    def post_error_to_slack(self, error_message):
        """Post an error message to Slack channel"""
        if not self.webhook_url:
            print("Slack webhook URL not configured")
            return False
            
        # Add timestamp and error formatting
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_error = f"🚨 TRADING BOT ERROR 🚨\nTime: {timestamp}\nError: {error_message}"
        
        payload = {
            "text": formatted_error  # Message to send to Slack
        }
        
        try:
            # Send a POST request to the Slack webhook URL
            response = requests.post(self.webhook_url, json=payload)
        
            # Check if the request was successful
            if response.status_code == 200:
                print("Error message posted successfully to Slack")
                return True
            else:
                print(f"Failed to post error message: {response.status_code}, {response.text}")
                return False
        
        except Exception as e:
            print(f"Error posting error message to Slack: {e}")
            return False

    def post_trade_notification(self, trade_info):
        """Post a formatted trade notification to Slack"""
        if not self.webhook_url:
            print("Slack webhook URL not configured")
            return False
            
        try:
            # Create a formatted trade message
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if trade_info.get('success', False):
                # Successful trade notification
                message = {
                    "🎯 TRADE EXECUTED": "✅ SUCCESS",
                    "Time": timestamp,
                    "Symbol": trade_info.get('symbol', 'N/A'),
                    "Entry Price": f"${trade_info.get('entry_price', 'N/A')}",
                    "Quantity": trade_info.get('quantity', 'N/A'),
                    "Stop Loss": f"${trade_info.get('stop_loss_price', 'N/A')} (-{trade_info.get('stop_loss_pct', 'N/A')}%)",
                    "Take Profit": f"${trade_info.get('take_profit_price', 'N/A')} (+{trade_info.get('profit_target_pct', 'N/A')}%)",
                    "Leverage": f"{trade_info.get('leverage', 'N/A')}x",
                    "Trade Amount": f"${trade_info.get('trade_amount', 'N/A')}",
                    "Max Hold Time": trade_info.get('max_hold_time', 'N/A'),
                    "Original Message": trade_info.get('original_message', 'N/A')
                }
            else:
                # Failed trade notification
                message = {
                    "🚨 TRADE FAILED": "❌ ERROR",
                    "Time": timestamp,
                    "Symbol": trade_info.get('symbol', 'N/A'),
                    "Error": trade_info.get('error', 'Unknown error'),
                    "Original Message": trade_info.get('original_message', 'N/A'),
                    "Action": "Added to retry queue" if trade_info.get('added_to_retry', False) else "Not retrying"
                }
            
            return self.post_to_slack(message)
            
        except Exception as e:
            print(f"Error creating trade notification: {e}")
            return False

    def post_retry_notification(self, symbol, attempt_number, success=False):
        """Post a retry attempt notification to Slack"""
        if not self.webhook_url:
            print("Slack webhook URL not configured")
            return False
            
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if success:
                message = {
                    "🔄 RETRY SUCCESS": "✅ TRADE EXECUTED",
                    "Time": timestamp,
                    "Symbol": symbol,
                    "Attempt": f"#{attempt_number}",
                    "Status": "Successfully executed after retry"
                }
            else:
                message = {
                    "🔄 RETRY FAILED": "❌ STILL FAILING",
                    "Time": timestamp,
                    "Symbol": symbol,
                    "Attempt": f"#{attempt_number}",
                    "Status": "Will retry again in 1 minute"
                }
            
            return self.post_to_slack(message)
            
        except Exception as e:
            print(f"Error creating retry notification: {e}")
            return False 