import json
import logging
import boto3
import os
from datetime import datetime, timedelta
import uuid
from botocore.exceptions import ClientError

from aux import load_business_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to check if phone exists in DB and spammer status.
    Creates lead if doesn't exist, checks spammer status if exists.
    """
    
    try:
        # Parse input from previous lambda
        if isinstance(event.get('body'), str):
            input_data = json.loads(event.get('body'))
        else:
            input_data = event.get('body', event)
            
        message_data = input_data.get('message_data', {})
        platform = input_data['platform']  # Get platform (mandatory)
        clean_phone_number = message_data.get('clean_phone_number', '')
        profile_name = message_data.get('profile_name', 'Unknown User')
        message_sid = message_data.get('message_sid', '')
        
        logger.info(f"Checking {platform} phone number: {clean_phone_number}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_settings_table = dynamodb.Table(os.environ['CONTACT_METHOD_SETTINGS_TABLE'])
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])  # Add activities table
        
        # Check if phone number exists using GSI
        type_value = f"phone#{clean_phone_number}"
        response = contact_methods_table.query(
            IndexName='type-value-index',
            KeyConditionExpression='type_value = :tv',
            ExpressionAttributeValues={':tv': type_value}
        )
        
        if response['Items']:
            # Phone exists, get lead info and check spammer status
            contact_method = response['Items'][0]
            contact_method_id = contact_method['id']
            lead_id = contact_method['lead_id']
            
            logger.info(f"Phone found for lead_id: {lead_id}")
            
            # Check spammer status (last 30 days)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            spam_response = spam_activities_table.query(
                IndexName='lead-id-spam-date-index',
                KeyConditionExpression='lead_id = :lead_id AND spam_date >= :date',
                ExpressionAttributeValues={
                    ':lead_id': lead_id,
                    ':date': thirty_days_ago
                }
            )
            
            config = load_business_config()

            spam_count_in_days_window = len(spam_response['Items'])
            is_spammer = spam_count_in_days_window >= config['spam_detection']['spam_threshold_in_days_window']
            
            # Check daily message volume
            today = datetime.now().date().isoformat()
            daily_activities_response = activities_table.query(
                IndexName='lead-id-created-at-index',
                KeyConditionExpression='lead_id = :lead_id AND created_at >= :today',
                ExpressionAttributeValues={
                    ':lead_id': lead_id,
                    ':today': today
                }
            )
            
            daily_message_count = len(daily_activities_response['Items'])
            
            # Check if daily limit reached (50+ messages = spam)
            if daily_message_count >= config['spam_detection']['daily_message_spam_threshold']:  # 50 by default
                is_spammer = True
                logger.info(f"Lead {lead_id} marked as spammer: {daily_message_count} messages today")
            elif daily_message_count >= daily_message_count >= config['spam_detection']['daily_message_warning_threshold']:  # 40 by default
                logger.warning(f"Lead {lead_id} approaching spam limit: {daily_message_count} messages today")
            
            logger.info(f"Spammer status: {is_spammer}, 30-day count: {spam_count_in_days_window}, daily count: {daily_message_count}")
            
            response_data = {
                'action': 'existing_user',
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'is_spammer': is_spammer,
                'platform': platform,  # Pass platform along
                'daily_message_count': daily_message_count,  # Add daily count
                'message_data': message_data
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
                        'source': platform,  # Use platform instead of hardcoded 'whatsapp'
                        'messageSid': message_sid,  # Platform-agnostic field name
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
                'is_spammer': False,
                'platform': platform,  # Pass platform along
                'daily_message_count': 1,  # First message of the day
                'message_data': message_data
            }
        
        return {
            'body': response_data
        }
        
    except Exception as e:
        logger.error(f"Error checking phone/spammer status: {str(e)}")
        return {
            'body': {
                'action': 'error',
                'error': str(e)
            }
        }
