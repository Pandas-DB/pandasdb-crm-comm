import json
import logging
import boto3
import os
from datetime import datetime
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to send messages through different platforms.
    Currently supports WhatsApp (via Twilio), designed to be extended for Telegram, etc.
    """
    
    try:
        # Parse input from previous lambda - matches the output format of normal/spam handlers
        send_message_data = event.get('send_message', {})
        platform = send_message_data.get('platform', 'whatsapp')
        to_number = send_message_data.get('to', '')
        message_body = send_message_data.get('message', '')
        from_number = send_message_data.get('from', '')
        
        logger.info(f"Sending message via {platform} to {to_number}: {message_body[:100]}")
        
        # Route to appropriate platform handler
        if platform == 'whatsapp':
            result = send_whatsapp_message(to_number, message_body, from_number)
        elif platform == 'telegram':
            result = send_telegram_message(to_number, message_body)
        else:
            logger.error(f"Unsupported platform: {platform}")
            return {
                'action': 'error',
                'error': f'Unsupported platform: {platform}'
            }
        
        response_data = {
            'action': 'message_sent',
            'platform': platform,
            'success': result.get('success', False),
            'message_id': result.get('message_id'),
            'error': result.get('error')
        }
        
        logger.info(f"Message sent successfully via {platform}: {result.get('message_id')}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }

def send_whatsapp_message(to_number, message_body, from_number):
    """Send WhatsApp message via Twilio"""
    try:
        from twilio.rest import Client
        
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        
        if not account_sid or not auth_token:
            logger.error("Twilio credentials not configured")
            return {
                'success': False,
                'error': 'Twilio credentials not configured'
            }
        
        client = Client(account_sid, auth_token)
        
        # Extract clean from number
        clean_from = from_number.split(':')[1] if ':' in from_number else from_number
        
        message = client.messages.create(
            from_=f'whatsapp:{clean_from}',
            body=message_body,
            to=f'whatsapp:{to_number}'
        )
        
        logger.info(f"Sent WhatsApp message: {message.sid}")
        return {
            'success': True,
            'message_id': message.sid,
            'platform': 'whatsapp'
        }
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'platform': 'whatsapp'
        }

def send_telegram_message(to_number, message_body):
    """Send Telegram message (placeholder for future implementation)"""
    try:
        # Placeholder for Telegram implementation
        # Will require Telegram Bot API integration
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        
        if not bot_token:
            logger.error("Telegram bot token not configured")
            return {
                'success': False,
                'error': 'Telegram bot token not configured'
            }
        
        # TODO: Implement Telegram Bot API call
        # Example structure:
        # import requests
        # url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        # payload = {
        #     'chat_id': to_number,  # This would be Telegram chat_id, not phone
        #     'text': message_body
        # }
        # response = requests.post(url, json=payload)
        
        logger.warning("Telegram messaging not yet implemented")
        return {
            'success': False,
            'error': 'Telegram messaging not yet implemented',
            'platform': 'telegram'
        }
        
    except Exception as e:
        logger.error(f"Error sending Telegram message: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'platform': 'telegram'
        }
