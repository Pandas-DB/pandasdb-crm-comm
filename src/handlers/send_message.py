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
        # Parse input from previous lambda
        if isinstance(event.get('body'), str):
            input_data = json.loads(event.get('body'))
        else:
            input_data = event.get('body', event)
            
        send_message_data = input_data.get('send_message', {})
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
                'body': {
                    'action': 'error',
                    'error': f'Unsupported platform: {platform}'
                }
            }
        
        # Log the message activity in DynamoDB (optional - for tracking sent messages)
        if result.get('success'):
            log_sent_message(input_data, send_message_data, result)
        
        response_data = {
            'action': 'message_sent',
            'platform': platform,
            'success': result.get('success', False),
            'message_id': result.get('message_id'),
            'error': result.get('error')
        }
        
        logger.info(f"Message sent successfully via {platform}: {result.get('message_id')}")
        
        return {
            'body': response_data
        }
        
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return {
            'body': {
                'action': 'error',
                'error': str(e)
            }
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

def log_sent_message(original_data, send_data, result):
    """Log sent message to DynamoDB for tracking (optional)"""
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
                'status': 'completed' if result.get('success') else 'failed',
                'direction': 'outbound',
                'completed_at': timestamp,
                'created_at': timestamp,
                'metadata': {
                    'messageSid': result.get('message_id', ''),
                    'platform': send_data.get('platform', 'unknown'),
                    'messageType': 'text',
                    'success': result.get('success', False)
                }
            }
        )
        
        # Store activity content
        activity_content_table.put_item(
            Item={
                'id': str(uuid.uuid4()),
                'activity_id': activity_id,
                'content_type': send_data.get('platform', 'unknown'),
                'content': {
                    'assistantMessage': send_data.get('message', ''),
                    'messageType': 'outbound_response'
                },
                'created_at': timestamp
            }
        )
        
        logger.info(f"Logged sent message activity: {activity_id}")
        
    except Exception as e:
        logger.warning(f"Error logging sent message: {str(e)}")
        # Don't fail the main operation if logging fails
