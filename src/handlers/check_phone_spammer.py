import json
import logging
import boto3
import os
from datetime import datetime, timedelta
import uuid
from botocore.exceptions import ClientError

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
        clean_phone_number = message_data.get('clean_phone_number', '')
        profile_name = message_data.get('profile_name', 'Unknown User')
        message_sid = message_data.get('message_sid', '')
        
        logger.info(f"Checking phone number: {clean_phone_number}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_settings_table = dynamodb.Table(os.environ['CONTACT_METHOD_SETTINGS_TABLE'])
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        
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
            
            spam_count_30_days = len(spam_response['Items'])
            is_spammer = spam_count_30_days >= 5
            logger.info(f"Spammer status: {is_spammer}, 30-day count: {spam_count_30_days}")
            
            response_data = {
                'action': 'existing_user',
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'is_spammer': is_spammer,
                'message_data': message_data
            }
            
        else:
            # Phone doesn't exist, create new lead and contact method
            logger.info(f"Creating new lead for phone: {clean_phone_number}")
            
            # Create new lead
            lead_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            leads_table.put_item(
                Item={
                    'id': lead_id,
                    'name': profile_name,
                    'metadata': {
                        'source': 'whatsapp',
                        'twilioSid': message_sid,
                        'firstContact': timestamp,
                        'profileName': profile_name
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
                'message_data': message_data
            }
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_data)
        }
        
    except Exception as e:
        logger.error(f"Error checking phone/spammer status: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'action': 'error',
                'error': str(e)
            })
        }
