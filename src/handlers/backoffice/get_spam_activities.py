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

def search_spam_activities(spam_activities, search_query):
    """Filter spam activities based on search query"""
    search_query_lower = search_query.lower()
    filtered_activities = []
    
    for activity in spam_activities:
        # Search in lead name, phone, message, or spam reason
        searchable_text = ' '.join([
            activity.get('lead_name', '').lower(),
            activity.get('phone', '').lower(),
            activity.get('message', '').lower(),
            activity.get('spam_reason', '').lower()
        ])
        
        if search_query_lower in searchable_text:
            filtered_activities.append(activity)
    
    return filtered_activities

def lambda_handler(event, context):
    """Get spam activities with search and date filtering"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        query_params = event.get('queryStringParameters') or {}
        search_query = query_params.get('search')
        start_date = query_params.get('start_date')
        end_date = query_params.get('end_date')
        
        # URL decode search query
        if search_query:
            search_query = urllib.parse.unquote(search_query).strip()
        
        # Set default date range (last 30 days) if not provided
        if not start_date or not end_date:
            end_date = datetime.now().date().isoformat()
            start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        
        # Convert dates to datetime strings for comparison
        start_datetime = start_date + 'T00:00:00'
        end_datetime = end_date + 'T23:59:59'
        
        logger.info(f"Filtering spam activities from {start_datetime} to {end_datetime}")
        if search_query:
            logger.info(f"Search query: {search_query}")
        
        dynamodb = boto3.resource('dynamodb')
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        # Get spam activities within date range
        spam_response = spam_activities_table.scan(
            FilterExpression='spam_date >= :start_date AND spam_date <= :end_date',
            ExpressionAttributeValues={
                ':start_date': start_datetime,
                ':end_date': end_datetime
            }
        )
        
        # Handle pagination for large result sets
        spam_items = spam_response['Items']
        while 'LastEvaluatedKey' in spam_response:
            spam_response = spam_activities_table.scan(
                FilterExpression='spam_date >= :start_date AND spam_date <= :end_date',
                ExpressionAttributeValues={
                    ':start_date': start_datetime,
                    ':end_date': end_datetime
                },
                ExclusiveStartKey=spam_response['LastEvaluatedKey']
            )
            spam_items.extend(spam_response['Items'])
        
        spam_activities = []
        for spam_activity in spam_items[:200]:  # Limit to 200 for performance
            try:
                # Get lead info
                lead_response = leads_table.get_item(Key={'id': spam_activity['lead_id']})
                lead_name = lead_response.get('Item', {}).get('name', 'Unknown')
                
                # Get phone number
                contact_response = contact_methods_table.query(
                    IndexName='lead-id-index',
                    KeyConditionExpression='lead_id = :lead_id',
                    ExpressionAttributeValues={':lead_id': spam_activity['lead_id']}
                )
                
                phone = 'N/A'
                for contact in contact_response['Items']:
                    if contact['type'] in ['phone', 'whatsapp']:
                        phone = contact['value']
                        break
                
                # Get activity content
                content_response = activity_content_table.query(
                    IndexName='activity-id-index',
                    KeyConditionExpression='activity_id = :activity_id',
                    ExpressionAttributeValues={':activity_id': spam_activity['activity_id']}
                )
                
                message = 'N/A'
                if content_response['Items']:
                    content = content_response['Items'][0]['content']
                    if isinstance(content, dict):
                        message = content.get('leadMessage', content.get('message', 'N/A'))
                    else:
                        message = str(content)
                
                spam_activities.append({
                    'id': spam_activity.get('id'),
                    'spam_date': spam_activity['spam_date'],
                    'lead_id': spam_activity['lead_id'],
                    'lead_name': lead_name,
                    'phone': phone,
                    'message': message[:100] + '...' if len(message) > 100 else message,
                    'full_message': message,
                    'spam_reason': spam_activity.get('spam_reason', 'Unknown'),
                    'flagged_by': spam_activity.get('flagged_by', 'Unknown')
                })
                
            except Exception as e:
                logger.warning(f"Error processing spam activity {spam_activity.get('id', 'unknown')}: {str(e)}")
                continue
        
        # Apply search filter if provided
        if search_query:
            spam_activities = search_spam_activities(spam_activities, search_query)
        
        # Sort by date (most recent first)
        spam_activities.sort(key=lambda x: x['spam_date'], reverse=True)
        
        result = {
            'spam_activities': convert_decimals(spam_activities),
            'count': len(spam_activities),
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            }
        }
        
        if search_query:
            result['search_query'] = search_query
        
        logger.info(f"Returning {len(spam_activities)} spam activities")
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error getting spam activities: {str(e)}")
        return create_response(500, {'error': str(e)})
