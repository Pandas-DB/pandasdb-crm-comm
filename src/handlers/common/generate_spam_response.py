import yaml
import logging
import boto3
import os
from datetime import datetime, timedelta
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aux import load_business_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to generate spam response messages.
    """
    
    try:
        # Parse input from previous lambda
        flow_input = event.get('flow_input', {})
        if isinstance(flow_input, str):
            flow_input = yaml.safe_load(flow_input)
            
        lead_id = event.get('lead_id')
        activity_id = event.get('activity_id')
        platform = flow_input['platform']
        
        clean_phone_number = flow_input.get('From', '')
        original_to = flow_input.get('To', '')
        
        logger.info(f"Generating spam response for lead {lead_id} on {platform}")
        
        config = load_business_config()
        
        # Check spam history to determine response
        dynamodb = boto3.resource('dynamodb')
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        
        spam_activities_limits = config['spam_detection']['spam_activities_limits']
        is_new_spammer = False
        
        for days, max_spam_activities in spam_activities_limits:
            lookback_date = (datetime.now() - timedelta(days=days)).isoformat()
            spam_response = spam_activities_table.query(
                IndexName='lead-id-spam-date-index',
                KeyConditionExpression='lead_id = :lead_id AND spam_date >= :date',
                ExpressionAttributeValues={
                    ':lead_id': lead_id,
                    ':date': lookback_date
                }
            )
            
            spam_count = len(spam_response['Items'])
            if spam_count == max_spam_activities:
                is_new_spammer = True
                break
        
        if is_new_spammer:
            response_message = config['spam_messages']['blocked_message_es']
            action_type = "blocked"
            is_blocked = True
        else:
            response_message = config['spam_messages']['warning_message_es']
            action_type = "warning"
            is_blocked = False
        
        response_data = {
            'action': 'spam_handled',
            'activity_id': activity_id,
            'response_message': response_message,
            'action_type': action_type,
            'is_blocked': is_blocked,
            'flow_input': flow_input,
            'send_message': {
                'platform': platform,
                'to': clean_phone_number,
                'message': response_message,
                'from': original_to,
                'answer_to_activity_id': activity_id
            }
        }
        
        logger.info(f"Spam response generated successfully for lead {lead_id} on {platform}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error generating spam response: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }
