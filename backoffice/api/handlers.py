import json
import logging
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Backoffice API handler for analytics and monitoring
    """
    
    try:
        path = event.get('path', '')
        http_method = event.get('httpMethod', 'GET')
        path_parameters = event.get('pathParameters') or {}
        
        # Handle different API endpoints
        if path.startswith('/api/lead/'):
            lead_id = path_parameters.get('lead_id')
            return get_lead_details(lead_id)
        
        elif path == '/api/analytics/daily':
            return get_daily_analytics()
        
        elif path == '/api/spam/activities':
            return get_spam_activities()
        
        elif path == '/api/spam/users':
            return get_spam_users()
        
        else:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
                },
                'body': json.dumps({'error': 'API endpoint not found'})
            }
        
    except Exception as e:
        logger.error(f"Error in backoffice API: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }

def get_lead_details(lead_id):
    """Get lead details with recent activities"""
    
    if not lead_id:
        return create_response(400, {'error': 'Lead ID is required'})
    
    try:
        dynamodb = boto3.resource('dynamodb')
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        # Get lead info
        lead_response = leads_table.get_item(Key={'id': lead_id})
        if 'Item' not in lead_response:
            return create_response(404, {'error': 'Lead not found'})
        
        lead = lead_response['Item']
        
        # Get contact methods
        contact_response = contact_methods_table.query(
            IndexName='lead-id-index',
            KeyConditionExpression='lead_id = :lead_id',
            ExpressionAttributeValues={':lead_id': lead_id}
        )
        
        # Get recent activities
        activities_response = activities_table.query(
            IndexName='lead-id-created-at-index',
            KeyConditionExpression='lead_id = :lead_id',
            ExpressionAttributeValues={':lead_id': lead_id},
            ScanIndexForward=False,
            Limit=20
        )
        
        # Get activity content for each activity
        activities_with_content = []
        for activity in activities_response['Items']:
            content_response = activity_content_table.query(
                IndexName='activity-id-index',
                KeyConditionExpression='activity_id = :activity_id',
                ExpressionAttributeValues={':activity_id': activity['id']}
            )
            
            activity_data = dict(activity)
            if content_response['Items']:
                activity_data['content'] = content_response['Items'][0]['content']
            
            activities_with_content.append(activity_data)
        
        result = {
            'lead': convert_decimals(lead),
            'contact_methods': convert_decimals(contact_response['Items']),
            'activities': convert_decimals(activities_with_content)
        }
        
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error getting lead details: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_daily_analytics():
    """Get daily analytics and statistics"""
    
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

def get_spam_activities():
    """Get recent spam activities with details"""
    
    try:
        dynamodb = boto3.resource('dynamodb')
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        # Get recent spam activities (last 7 days)
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        spam_response = spam_activities_table.scan(
            FilterExpression='spam_date >= :seven_days_ago',
            ExpressionAttributeValues={':seven_days_ago': seven_days_ago}
        )
        
        spam_activities = []
        for spam_activity in spam_response['Items'][:50]:  # Limit to 50 for performance
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
                if contact['type'] == 'phone':
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
                message = content.get('leadMessage', 'N/A')
            
            spam_activities.append({
                'id': spam_activity.get('id'),
                'spam_date': spam_activity['spam_date'],
                'lead_id': spam_activity['lead_id'],
                'lead_name': lead_name,
                'phone': phone,
                'message': message[:100] + '...' if len(message) > 100 else message,
                'spam_reason': spam_activity.get('spam_reason', 'Unknown'),
                'flagged_by': spam_activity.get('flagged_by', 'Unknown')
            })
        
        # Sort by date (most recent first)
        spam_activities.sort(key=lambda x: x['spam_date'], reverse=True)
        
        return create_response(200, convert_decimals(spam_activities))
        
    except Exception as e:
        logger.error(f"Error getting spam activities: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_spam_users():
    """Get users classified as spammers"""
    
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

def create_response(status_code, data):
    """Create standardized API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Cache-Control': 'no-cache'
        },
        'body': json.dumps(data, default=str)
    }

def convert_decimals(obj):
    """Convert DynamoDB Decimal objects to float for JSON serialization"""
    if isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj
