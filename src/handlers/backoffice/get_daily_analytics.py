import logging
import boto3
import os
import json
from datetime import datetime, timedelta

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
        'body': json.dumps(body) if isinstance(body, dict) else body
    }

def lambda_handler(event, context):
    """Get daily analytics and statistics"""
    
    # DEBUG: Log the incoming event
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        logger.info("Handling OPTIONS request")
        return create_response(200, {})
    
    try:
        logger.info("Starting analytics processing")
        dynamodb = boto3.resource('dynamodb')
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time()).isoformat()
        
        # Get total leads count
        leads_response = leads_table.scan(Select='COUNT')
        total_leads = leads_response['Count']
        
        # Get today's activities
        activities_response = activities_table.scan(
            FilterExpression='begins_with(created_at, :today)',
            ExpressionAttributeValues={':today': today_start[:10]}
        )
        
        messages_today = len(activities_response['Items'])
        
        # Get today's spam activities
        spam_response = spam_activities_table.scan(
            FilterExpression='begins_with(spam_date, :today)',
            ExpressionAttributeValues={':today': today_start[:10]}
        )
        
        spam_today = len(spam_response['Items'])
        
        # Calculate spam percentage
        spam_percentage = (spam_today / messages_today * 100) if messages_today > 0 else 0
        
        # Get count of users with spam in last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        spam_users_response = spam_activities_table.scan(
            FilterExpression='spam_date >= :thirty_days_ago',
            ExpressionAttributeValues={':thirty_days_ago': thirty_days_ago}
        )
        
        # Count unique spam users
        spam_user_ids = set()
        for spam_activity in spam_users_response['Items']:
            spam_user_ids.add(spam_activity['lead_id'])
        
        result = {
            'total_leads': total_leads,
            'messages_today': messages_today,
            'spam_today': spam_today,
            'spam_percentage': round(spam_percentage, 2),
            'spam_users': len(spam_user_ids),
            'last_updated': datetime.now().isoformat()
        }
        
        logger.info(f"Analytics result: {result}")
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error getting daily analytics: {str(e)}")
        return create_response(500, {'error': str(e)})
