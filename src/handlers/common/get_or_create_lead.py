import yaml
import logging
import boto3
import os
import sys
from datetime import datetime
import uuid
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to check if phone exists in DB and get/create lead.
    Creates lead if doesn't exist, returns lead info if exists.
    """
    
    try:
        # Parse input from previous lambda
        flow_input = event.get('flow_input', {})
        if isinstance(flow_input, str):
            flow_input = yaml.safe_load(flow_input)
            
        platform = flow_input['platform']
        clean_phone_number = flow_input.get('From', '')
        profile_name = flow_input.get('ProfileName', 'Unknown User')
        message_sid = flow_input.get('MessageSid', '')
        
        logger.info(f"Checking {platform} phone number: {clean_phone_number}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_settings_table = dynamodb.Table(os.environ['CONTACT_METHOD_SETTINGS_TABLE'])
        
        # Check if phone number exists using GSI
        type_value = f"phone#{clean_phone_number}"
        response = contact_methods_table.query(
            IndexName='type-value-index',
            KeyConditionExpression='type_value = :tv',
            ExpressionAttributeValues={':tv': type_value}
        )
        
        if response['Items']:
            # Phone exists, get lead info
            contact_method = response['Items'][0]
            contact_method_id = contact_method['id']
            lead_id = contact_method['lead_id']
            
            logger.info(f"Phone found for lead_id: {lead_id}")
            
            response_data = {
                'action': 'existing_user',
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'flow_input': flow_input
            }
            
        else:
            # Phone doesn't exist, create new lead and contact method
            logger.info(f"Creating new lead for {platform} phone: {clean_phone_number}")
            
            # Create new lead
            lead_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            leads_table.put_item(
                Item={
                    'id': lead_id,
                    'name': profile_name,
                    'metadata': {
                        'source': platform,
                        'messageSid': message_sid,
                        'firstContact': timestamp,
                        'profileName': profile_name,
                        'platform': platform
                    },
                    'created_at': timestamp,
                    'updated_at': timestamp
                }
            )
            
            # Create contact method
            contact_method_id = str(uuid.uuid4())
            contact_methods_table.put_item(
                Item={
                    'id': contact_method_id,
                    'lead_id': lead_id,
                    'type': 'phone',
                    'value': clean_phone_number,
                    'type_value': f"phone#{clean_phone_number}",
                    'created_at': timestamp,
                    'updated_at': timestamp
                }
            )
            
            # Set as primary contact method
            contact_settings_table.put_item(
                Item={
                    'id': str(uuid.uuid4()),
                    'contact_method_id': contact_method_id,
                    'is_primary': True,
                    'is_active': True,
                    'created_at': timestamp,
                    'updated_at': timestamp
                }
            )
            
            logger.info(f"Created new lead {lead_id} with contact method {contact_method_id}")
            
            response_data = {
                'action': 'new_user',
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'flow_input': flow_input
            }
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error getting/creating lead: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }
