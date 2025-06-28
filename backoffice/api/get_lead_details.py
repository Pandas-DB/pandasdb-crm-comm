import logging
import boto3
import os
from utils import create_response, convert_decimals

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Get lead details with recent activities"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    path_parameters = event.get('pathParameters') or {}
    lead_id = path_parameters.get('lead_id')
    
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
