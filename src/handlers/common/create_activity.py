import yaml
import logging
import boto3
import os
from datetime import datetime
import uuid
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to store inbound activity and activity content.
    """
    
    try:
        # Parse input from previous lambda
        flow_input = event.get('flow_input', {})
        if isinstance(flow_input, str):
            flow_input = yaml.safe_load(flow_input)
            
        lead_id = event.get('lead_id')
        contact_method_id = event.get('contact_method_id')
        platform = flow_input['platform']
        
        message_body = flow_input.get('Body', '')
        message_sid = flow_input.get('MessageSid', '')
        profile_name = flow_input.get('ProfileName', '')
        
        logger.info(f"Storing activity for lead {lead_id}: {message_body[:100]}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        timestamp = datetime.now().isoformat()
        
        # Create inbound activity record
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
                    'messageType': 'text',
                    'platform': platform
                }
            }
        )
        
        # Store inbound activity content
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
        
        logger.info(f"Activity stored successfully for lead {lead_id}")
        
        response_data = {
            'activity_id': activity_id,
            'lead_id': lead_id,
            'contact_method_id': contact_method_id,
            'flow_input': flow_input
        }
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error storing activity: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }
