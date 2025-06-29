import json
import logging
import boto3
import os
from datetime import datetime
import uuid
import time
import random

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to send messages through different platforms.
    Currently supports WhatsApp (via Twilio), designed to be extended for Telegram, etc.
    Now handles both single messages and lists of messages.
    """
    
    try:
        # Parse input from previous lambda - matches the output format of normal/spam handlers
        send_message_data = event.get('send_message', {})
        platform = send_message_data.get('platform', 'whatsapp')
        to_number = send_message_data.get('to', '')
        from_number = send_message_data.get('from', '')
        answer_to_activity_id = send_message_data.get('answer_to_activity_id', '')
        
        # Handle both single message and list of messages
        if 'messages' in send_message_data:
            messages = send_message_data.get('messages', [])
        else:
            # Fallback to single message format
            single_message = send_message_data.get('message', '')
            messages = [single_message] if single_message else []
        
        if not messages:
            logger.error("No messages to send")
            return {
                'action': 'error',
                'error': 'No messages to send'
            }
        
        logger.info(f"Sending {len(messages)} message(s) via {platform} to {to_number}")
        
        results = []
        sent_count = 0
        
        for i, message_body in enumerate(messages):
            if not message_body.strip():
                continue
                
            logger.info(f"Sending message {i+1}/{len(messages)}: {message_body[:100]}")
            
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
            
            results.append(result)
            
            # Store outbound activity and content ONLY after successful sending
            if result.get('success'):
                log_outbound_message(event, send_message_data, result, answer_to_activity_id, message_body)
                sent_count += 1
        
        response_data = {
            'action': 'message_sent',
            'platform': platform,
            'total_messages': len(messages),
            'sent_messages': sent_count,
            'success': sent_count > 0,
            'all_sent': sent_count == len(messages),
            'results': results
        }
        
        if sent_count == len(messages):
            logger.info(f"All {len(messages)} messages sent successfully via {platform}")
        else:
            logger.warning(f"Only {sent_count}/{len(messages)} messages sent successfully via {platform}")
        
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

def log_outbound_message(original_data, send_data, result, answer_to_activity_id, message_content):
    """Log outbound message to DynamoDB after successful sending"""
    try:
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ.get('ACTIVITIES_TABLE', ''))
        activity_content_table = dynamodb.Table(os.environ.get('ACTIVITY_CONTENT_TABLE', ''))
        
        if not activities_table or not activity_content_table:
            logger.warning("DynamoDB tables not configured for message logging")
            return
        
        timestamp = datetime.now().isoformat()
        activity_id = str(uuid.uuid4())
        
        # Create outbound activity record
        activities_table.put_item(
            Item={
                'id': activity_id,
                'lead_id': original_data.get('lead_id', ''),
                'contact_method_id': original_data.get('contact_method_id', ''),
                'activity_type': send_data.get('platform', 'unknown'),
                'status': 'completed',
                'direction': 'outbound',
                'completed_at': timestamp,
                'created_at': timestamp,
                'metadata': {
                    'messageSid': result.get('message_id', ''),
                    'platform': send_data.get('platform', 'unknown'),
                    'messageType': 'text',
                    'answer_to_activity_id': answer_to_activity_id
                }
            }
        )
        
        # Store outbound activity content (only the assistant message)
        activity_content_table.put_item(
            Item={
                'id': str(uuid.uuid4()),
                'activity_id': activity_id,
                'content_type': send_data.get('platform', 'unknown'),
                'content': {
                    'assistantMessage': message_content
                },
                'created_at': timestamp,
            }
        )
        
        logger.info(f"Logged outbound message activity: {activity_id}")
        
    except Exception as e:
        logger.warning(f"Error logging outbound message: {str(e)}")
        # Don't fail the main operation if logging fails
