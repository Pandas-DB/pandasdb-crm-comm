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
    Stores spam activity and prepares response for messaging service.
    """
    
    try:
        # Parse input from previous lambda
        flow_input = event.get('flow_input', {})
        if isinstance(flow_input, str):
            flow_input = json.loads(flow_input)
            
        lead_id = event.get('lead_id')
        contact_method_id = event.get('contact_method_id')
        spam_reason = event.get('spam_reason', 'AI detected spam')
        platform = flow_input.get('platform')
        
        clean_phone_number = flow_input.get('From', '')
        message_body = flow_input.get('Body', '')
        message_sid = flow_input.get('MessageSid', '')
        profile_name = flow_input.get('ProfileName', '')
        original_to = flow_input.get('To', '')
        
        logger.info(f"Handling spam message for lead {lead_id} on {platform}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        timestamp = datetime.now().isoformat()
        
        # Create inbound spam activity record
        activity_id = str(uuid.uuid4())
        activities_table.put_item(
            Item={
                'id': activity_id,
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'activity_type': platform,
                'status': 'completed',
                'direction': 'inbound',
                'completed_at': timestamp,
                'created_at': timestamp,
                'metadata': {
                    'messageSid': message_sid,
                    'profileName': profile_name,
                    'spam': 'True',
                    'spam_reason': spam_reason,
                    'platform': platform
                }
            }
        )
        
        # Store inbound activity content (only the lead message)
        activity_content_table.put_item(
            Item={
                'id': str(uuid.uuid4()),
                'activity_id': activity_id,
                'content_type': platform,
                'content': {
                    'leadMessage': message_body
                },
                'created_at': timestamp
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
        
        config = load_business_config()
        
        # Get current spam count to determine response (last N days, by default 30)
        lookback_days = config['spam_detection']['spam_lookback_days']
        lookback_date = (datetime.now() - timedelta(days=lookback_days)).isoformat()
        spam_response = spam_activities_table.query(
            IndexName='lead-id-spam-date-index',
            KeyConditionExpression='lead_id = :lead_id AND spam_date >= :date',
            ExpressionAttributeValues={
                ':lead_id': lead_id,
                ':date': lookback_date
            }
        )
        
        spam_count_window_days = len(spam_response['Items'])
        is_spammer = spam_count_window_days >= config['spam_detection']['spam_threshold_30_days']
        
        # Determine response message based on spam count
        if is_spammer:
            response_message = config['spam_messages']['blocked_message_es']
            action_type = "blocked"
        else:
            response_message = config['spam_messages']['warning_message_es']
            action_type = "warning"
        
        response_data = {
            'action': 'spam_handled',
            'activity_id': activity_id,
            'response_message': response_message,
            'action_type': action_type,
            'spam_count': spam_count_window_days + 1,
            'is_blocked': is_spammer,
            'flow_input': flow_input,
            'send_message': {
                'platform': platform,
                'to': clean_phone_number,
                'message': response_message,
                'from': original_to,
                'answer_to_activity_id': activity_id
            }
        }
        
        logger.info(f"Spam handled successfully for lead {lead_id} on {platform}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error handling spam: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }
