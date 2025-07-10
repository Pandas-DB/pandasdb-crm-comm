import logging
import boto3
import os
import json
from decimal import Decimal
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'DELETE,OPTIONS'
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

def lambda_handler(event, context):
    """Remove spam activities for a lead (all or specific activity)"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    path_parameters = event.get('pathParameters') or {}
    query_parameters = event.get('queryStringParameters') or {}
    
    lead_id = path_parameters.get('lead_id')
    activity_id = query_parameters.get('activity_id')  # Optional: remove specific activity
    
    if not lead_id:
        return create_response(400, {'error': 'Lead ID is required'})
    
    try:
        dynamodb = boto3.resource('dynamodb')
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        
        # Verify lead exists
        lead_response = leads_table.get_item(Key={'id': lead_id})
        if 'Item' not in lead_response:
            return create_response(404, {'error': 'Lead not found'})
        
        if activity_id:
            # Remove specific spam activity
            removed_count = remove_specific_spam_activity(spam_activities_table, lead_id, activity_id)
            if removed_count == 0:
                return create_response(404, {'error': 'Spam activity not found for this lead'})
            
            result = {
                'success': True,
                'lead_id': lead_id,
                'activity_id': activity_id,
                'removed_count': removed_count,
                'message': f'Removed spam activity {activity_id} for lead {lead_id}'
            }
        else:
            # Remove all spam activities for the lead
            removed_count = remove_all_spam_activities_for_lead(spam_activities_table, lead_id)
            
            result = {
                'success': True,
                'lead_id': lead_id,
                'removed_count': removed_count,
                'message': f'Removed {removed_count} spam activities for lead {lead_id}'
            }
        
        logger.info(f"Successfully removed {removed_count} spam activities for lead {lead_id}")
        return create_response(200, convert_decimals(result))
        
    except ClientError as e:
        logger.error(f"DynamoDB error: {str(e)}")
        return create_response(500, {'error': f'Database error: {str(e)}'})
    
    except Exception as e:
        logger.error(f"Error removing spam activities: {str(e)}")
        return create_response(500, {'error': str(e)})

def remove_specific_spam_activity(spam_activities_table, lead_id, activity_id):
    """Remove a specific spam activity for a lead"""
    try:
        response = spam_activities_table.scan(
            FilterExpression='lead_id = :lead_id AND activity_id = :activity_id',
            ExpressionAttributeValues={
                ':lead_id': lead_id,
                ':activity_id': activity_id
            }
        )
        
        if not response['Items']:
            return 0
        
        spam_activity = response['Items'][0]
        spam_activities_table.delete_item(Key={'id': spam_activity['id']})
        
        logger.info(f"Removed specific spam activity {activity_id} for lead {lead_id}")
        return 1
        
    except ClientError as e:
        logger.error(f"Error removing specific spam activity: {str(e)}")
        raise

def remove_all_spam_activities_for_lead(spam_activities_table, lead_id):
    """Remove all spam activities for a specific lead"""
    try:
        removed_count = 0
        
        response = spam_activities_table.query(
            IndexName='lead-id-spam-date-index',
            KeyConditionExpression='lead_id = :lead_id',
            ExpressionAttributeValues={':lead_id': lead_id}
        )
        
        with spam_activities_table.batch_writer() as batch:
            for spam_activity in response['Items']:
                batch.delete_item(Key={'id': spam_activity['id']})
                removed_count += 1
        
        while 'LastEvaluatedKey' in response:
            response = spam_activities_table.query(
                IndexName='lead-id-spam-date-index',
                KeyConditionExpression='lead_id = :lead_id',
                ExpressionAttributeValues={':lead_id': lead_id},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            
            with spam_activities_table.batch_writer() as batch:
                for spam_activity in response['Items']:
                    batch.delete_item(Key={'id': spam_activity['id']})
                    removed_count += 1
        
        logger.info(f"Removed {removed_count} spam activities for lead {lead_id}")
        return removed_count
        
    except ClientError as e:
        logger.error(f"Error removing all spam activities for lead: {str(e)}")
        raise
