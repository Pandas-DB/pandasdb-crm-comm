import logging
import boto3
import os
from datetime import datetime, timedelta
from utils import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Get daily analytics and statistics"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
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
            'spam_percentage': spam_percentage,
            'spam_users': len(spam_user_ids),
            'last_updated': datetime.now().isoformat()
        }
        
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error getting daily analytics: {str(e)}")
        return create_response(500, {'error': str(e)})
