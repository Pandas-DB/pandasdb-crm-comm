import json
import logging
import boto3
import os
from datetime import datetime, timedelta
import uuid

from aux import load_business_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to handle spam messages.
    Stores spam activity, sends warning/blocking message via Twilio.
    """
    
    try:
        # Parse input from previous lambda
        if isinstance(event.get('body'), str):
            input_data = json.loads(event.get('body'))
        else:
            input_data = event.get('body', event)
            
        message_data = input_data.get('message_data', {})
        lead_id = input_data.get('lead_id')
        contact_method_id = input_data.get('contact_method_id')
        spam_reason = input_data.get('spam_reason', 'AI detected spam')
        
        clean_phone_number = message_data.get('clean_phone_number', '')
        message_body = message_data.get('message_body', '')
        message_sid = message_data.get('message_sid', '')
        profile_name = message_data.get('profile_name', '')
        original_to = message_data.get('original_to', '')
        
        logger.info(f"Handling spam message for lead {lead_id}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        timestamp = datetime.now().isoformat()
        
        # Create spam activity record
        activity_id = str(uuid.uuid4())
        activities_table.put_item(
            Item={
                'id': activity_id,
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'activity_type': 'whatsapp',
                'status': 'completed',
                'direction': 'inbound',
                'completed_at': timestamp,
                'created_at': timestamp,
                'metadata': {
                    'twilioSid': message_sid,
                    'profileName': profile_name,
                    'spam': 'True',
                    'spam_reason': spam_reason
                }
            }
        )
        
        # Create spam_activities record
        spam_activities_table.put_item(
            Item={
                'id': str(uuid.uuid4()),
                'activity_id': activity_id,
                'lead_id': lead_id,
                'flagged_by': 'bot',
                'spam_reason': spam_reason,
                'spam_date': timestamp,
                'created_at': timestamp
            }
        )
        
        # Get current spam count to determine response (last N days, by default 30)
        thirty_days_ago = (datetime.now() - timedelta(days=config['spam_detection']['spam_lookback_days'])).isoformat()  # by default 30 lookback days
        spam_response = spam_activities_table.query(
            IndexName='lead-id-spam-date-index',
            KeyConditionExpression='lead_id = :lead_id AND spam_date >= :date',
            ExpressionAttributeValues={
                ':lead_id': lead_id,
                ':date': thirty_days_ago
            }
        )
        
        spam_count_window_days = len(spam_response['Items'])
        config = load_business_config()
        is_spammer = config['spam_detection']['spam_threshold_days']
        
        # Determine response message based on spam count
        if is_spammer or spam_count_window_days >= config['spam_detection']['spam_threshold_days_window']:  # by default 5
            response_message = "Lo siento, te hemos clasificado como spam y no volveremos a responder tus mensajes. Si se trata de un error envía un email a errores@test.com y encantados revisaremos tu caso."
            action_type = "blocked"
        else:
            response_message = "Creemos que tu mensaje es spam. Después de 5 avisos como este procederemos a bloquear tu número."
            action_type = "warning"
        
        # Store activity content
        activity_content_table.put_item(
            Item={
                'id': str(uuid.uuid4()),
                'activity_id': activity_id,
                'content_type': 'whatsapp',
                'content': {
                    'leadMessage': message_body,
                    'assistantMessage': response_message,
                    'action': action_type
                },
                'created_at': timestamp
            }
        )
        
        # Send WhatsApp response via Twilio
        send_twilio_message(clean_phone_number, response_message, original_to)
        
        response_data = {
            'action': 'spam_handled',
            'activity_id': activity_id,
            'response_sent': True,
            'response_message': response_message,
            'action_type': action_type,
            'spam_count': spam_count_window_days + 1,
            'is_blocked': is_spammer or spam_count_window_days >= config['spam_detection']['spam_threshold_30_days']
        }
        
        logger.info(f"Spam handled successfully for lead {lead_id}")
        
        return {
            'body': response_data
        }
        
    except Exception as e:
        logger.error(f"Error handling spam: {str(e)}")
        return {
            'body': {
                'action': 'error',
                'error': str(e)
            }
        }

def send_twilio_message(to_number, message_body, from_number):
    """Send WhatsApp message via Twilio"""
    try:
        from twilio.rest import Client
        
        account_sid = os.environ['TWILIO_ACCOUNT_SID']
        auth_token = os.environ['TWILIO_AUTH_TOKEN']
        
        client = Client(account_sid, auth_token)
        
        # Extract clean from number
        clean_from = from_number.split(':')[1] if ':' in from_number else from_number
        
        message = client.messages.create(
            from_=f'whatsapp:{clean_from}',
            body=message_body,
            to=f'whatsapp:{to_number}'
        )
        
        logger.info(f"Sent Twilio message: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending Twilio message: {str(e)}")
        return False
