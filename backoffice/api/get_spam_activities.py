import logging
import boto3
import os
from datetime import datetime, timedelta
from utils import create_response, convert_decimals

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Get recent spam activities with details"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
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
