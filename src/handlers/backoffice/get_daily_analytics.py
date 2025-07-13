import logging
import boto3
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict

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

def get_date_range_from_params(event):
    """Extract and validate date range from query parameters"""
    query_params = event.get('queryStringParameters', {}) or {}
    
    # Default to last 90 days if no parameters provided
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=90)
    
    if query_params.get('start_date'):
        try:
            start_date = datetime.strptime(query_params['start_date'], '%Y-%m-%d').date()
        except ValueError:
            logger.warning(f"Invalid start_date format: {query_params['start_date']}")
    
    if query_params.get('end_date'):
        try:
            end_date = datetime.strptime(query_params['end_date'], '%Y-%m-%d').date()
        except ValueError:
            logger.warning(f"Invalid end_date format: {query_params['end_date']}")
    
    # Ensure start_date is not after end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    return start_date, end_date

def scan_activities_by_date_range(table, start_date_str, end_date_str):
    """Scan activities table for items within date range"""
    try:
        response = table.scan(
            FilterExpression='created_at BETWEEN :start_date AND :end_date',
            ExpressionAttributeValues={
                ':start_date': start_date_str,
                ':end_date': end_date_str
            }
        )
        
        activities = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression='created_at BETWEEN :start_date AND :end_date',
                ExpressionAttributeValues={
                    ':start_date': start_date_str,
                    ':end_date': end_date_str
                },
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            activities.extend(response.get('Items', []))
        
        return activities
    except Exception as e:
        logger.error(f"Error scanning activities: {str(e)}")
        return []

def scan_spam_activities_by_date_range(table, start_date_str, end_date_str):
    """Scan spam activities table for items within date range"""
    try:
        response = table.scan(
            FilterExpression='spam_date BETWEEN :start_date AND :end_date',
            ExpressionAttributeValues={
                ':start_date': start_date_str,
                ':end_date': end_date_str
            }
        )
        
        spam_activities = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression='spam_date BETWEEN :start_date AND :end_date',
                ExpressionAttributeValues={
                    ':start_date': start_date_str,
                    ':end_date': end_date_str
                },
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            spam_activities.extend(response.get('Items', []))
        
        return spam_activities
    except Exception as e:
        logger.error(f"Error scanning spam activities: {str(e)}")
        return []

def group_activities_by_date(activities, spam_activities):
    """Group activities by date for daily analytics"""
    daily_data = defaultdict(lambda: {'messages': 0, 'spam': 0})
    
    # Process regular activities
    for activity in activities:
        try:
            created_at = activity.get('created_at', '')
            # Extract date part from ISO timestamp (YYYY-MM-DD)
            activity_date = created_at[:10]
            if activity_date:
                daily_data[activity_date]['messages'] += 1
        except Exception as e:
            logger.warning(f"Error processing activity date: {str(e)}")
    
    # Process spam activities
    for spam in spam_activities:
        try:
            spam_date = spam.get('spam_date', '')
            # Extract date part from ISO timestamp (YYYY-MM-DD)
            spam_date_only = spam_date[:10]
            if spam_date_only:
                daily_data[spam_date_only]['spam'] += 1
        except Exception as e:
            logger.warning(f"Error processing spam date: {str(e)}")
    
    # Convert to sorted list
    daily_analytics = []
    for date_str in sorted(daily_data.keys()):
        daily_analytics.append({
            'date': date_str,
            'messages': daily_data[date_str]['messages'],
            'spam': daily_data[date_str]['spam']
        })
    
    return daily_analytics

def lambda_handler(event, context):
    """Get daily analytics and statistics with date range support"""
    
    # DEBUG: Log the incoming event
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        logger.info("Handling OPTIONS request")
        return create_response(200, {})
    
    try:
        logger.info("Starting analytics processing")
        
        # Get date range from parameters (defaults to last 90 days)
        start_date, end_date = get_date_range_from_params(event)
        
        # Convert to ISO format strings for DynamoDB queries
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')  # Add 1 day to include end_date
        
        logger.info(f"Date range: {start_date_str} to {end_date_str}")
        
        # Initialize DynamoDB tables
        dynamodb = boto3.resource('dynamodb')
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        
        # Get total leads count (this remains the same)
        leads_response = leads_table.scan(Select='COUNT')
        total_leads = leads_response['Count']
        
        # Get activities for the date range
        activities = scan_activities_by_date_range(activities_table, start_date_str, end_date_str)
        spam_activities = scan_spam_activities_by_date_range(spam_activities_table, start_date_str, end_date_str)
        
        # Calculate metrics for the period
        total_messages = len(activities)
        total_spam = len(spam_activities)
        spam_percentage = (total_spam / total_messages * 100) if total_messages > 0 else 0
        
        # Group by date for chart
        daily_analytics = group_activities_by_date(activities, spam_activities)
        
        # Count unique spam users in the period
        spam_user_ids = set()
        for spam_activity in spam_activities:
            spam_user_ids.add(spam_activity.get('lead_id', ''))
        
        result = {
            'total_leads': total_leads,
            'total_messages': total_messages,  # Changed from messages_today
            'total_spam': total_spam,          # Changed from spam_today
            'spam_percentage': round(spam_percentage, 2),
            'spam_users': len(spam_user_ids),
            'daily_analytics': daily_analytics,  # New: for the chart
            'last_updated': datetime.now().isoformat(),
            'date_range': {                    # New: show what range was queried
                'start': start_date_str,
                'end': end_date.strftime('%Y-%m-%d')
            }
        }
        
        logger.info(f"Analytics result: total_messages={total_messages}, total_spam={total_spam}, daily_count={len(daily_analytics)}")
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error getting daily analytics: {str(e)}")
        return create_response(500, {'error': str(e)})
