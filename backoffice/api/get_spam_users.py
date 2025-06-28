import logging
import boto3
import os
from datetime import datetime, timedelta
from utils import create_response, convert_decimals

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Get users classified as spammers"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        dynamodb = boto3.resource('dynamodb')
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        
        # Get spam activities from last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        spam_response = spam_activities_table.scan(
            FilterExpression='spam_date >= :thirty_days_ago',
            ExpressionAttributeValues={':thirty_days_ago': thirty_days_ago}
        )
        
        # Group by lead_id and count
        spam_counts = {}
        spam_dates = {}
        
        for spam_activity in spam_response['Items']:
            lead_id = spam_activity['lead_id']
            spam_date = spam_activity['spam_date']
            
            if lead_id not in spam_counts:
                spam_counts[lead_id] = 0
                spam_dates[lead_id] = {'first': spam_date, 'last': spam_date}
            
            spam_counts[lead_id] += 1
            
            # Update first and last spam dates
            if spam_date < spam_dates[lead_id]['first']:
                spam_dates[lead_id]['first'] = spam_date
            if spam_date > spam_dates[lead_id]['last']:
                spam_dates[lead_id]['last'] = spam_date
        
        spam_users = []
        for lead_id, count in spam_counts.items():
            if count >= 2:  # Show users with 2+ spam activities
                # Get lead info
                lead_response = leads_table.get_item(Key={'id': lead_id})
                lead_name = lead_response.get('Item', {}).get('name', 'Unknown')
                
                # Get phone number
                contact_response = contact_methods_table.query(
                    IndexName='lead-id-index',
                    KeyConditionExpression='lead_id = :lead_id',
                    ExpressionAttributeValues={':lead_id': lead_id}
                )
                
                phone = 'N/A'
                for contact in contact_response['Items']:
                    if contact['type'] == 'phone':
                        phone = contact['value']
                        break
                
                spam_users.append({
                    'lead_id': lead_id,
                    'lead_name': lead_name,
                    'phone': phone,
                    'spam_count_30_days': count,
                    'first_spam': spam_dates[lead_id]['first'],
                    'last_spam': spam_dates[lead_id]['last'],
                    'is_blocked': count >= 5
                })
        
        # Sort by spam count (highest first)
        spam_users.sort(key=lambda x: x['spam_count_30_days'], reverse=True)
        
        return create_response(200, convert_decimals(spam_users))
        
    except Exception as e:
        logger.error(f"Error getting spam users: {str(e)}")
        return create_response(500, {'error': str(e)})
