import logging
import boto3
import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
import urllib.parse

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(body, default=str) if isinstance(body, (dict, list)) else str(body)
    }

def convert_decimals(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj

def search_spam_users(spam_users, search_query):
    """Filter spam users based on search query"""
    search_query_lower = search_query.lower()
    filtered_users = []
    
    for user in spam_users:
        # Search in lead name or phone
        searchable_text = ' '.join([
            user.get('lead_name', '').lower(),
            user.get('phone', '').lower()
        ])
        
        if search_query_lower in searchable_text:
            filtered_users.append(user)
    
    return filtered_users

def lambda_handler(event, context):
    """Get users classified as spammers with search functionality"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        query_params = event.get('queryStringParameters') or {}
        search_query = query_params.get('search')
        
        # URL decode search query
        if search_query:
            search_query = urllib.parse.unquote(search_query).strip()
            logger.info(f"Searching spam users for: {search_query}")
        
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
        
        # Handle pagination for large result sets
        spam_items = spam_response['Items']
        while 'LastEvaluatedKey' in spam_response:
            spam_response = spam_activities_table.scan(
                FilterExpression='spam_date >= :thirty_days_ago',
                ExpressionAttributeValues={':thirty_days_ago': thirty_days_ago},
                ExclusiveStartKey=spam_response['LastEvaluatedKey']
            )
            spam_items.extend(spam_response['Items'])
        
        # Group by lead_id and count
        spam_counts = {}
        spam_dates = {}
        
        for spam_activity in spam_items:
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
                try:
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
                        if contact['type'] in ['phone', 'whatsapp']:
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
                    
                except Exception as e:
                    logger.warning(f"Error processing spam user {lead_id}: {str(e)}")
                    continue
        
        # Apply search filter if provided
        if search_query:
            spam_users = search_spam_users(spam_users, search_query)
        
        # Sort by spam count (highest first)
        spam_users.sort(key=lambda x: x['spam_count_30_days'], reverse=True)
        
        result = {
            'spam_users': convert_decimals(spam_users),
            'count': len(spam_users)
        }
        
        if search_query:
            result['search_query'] = search_query
        
        logger.info(f"Returning {len(spam_users)} spam users")
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error getting spam users: {str(e)}")
        return create_response(500, {'error': str(e)})
