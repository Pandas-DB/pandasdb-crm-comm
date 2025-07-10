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

def lambda_handler(event, context):
    """List all leads with pagination"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        last_key = query_params.get('last_key')
        
        dynamodb = boto3.resource('dynamodb')
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        
        # Scan leads with pagination
        scan_kwargs = {'Limit': limit}
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = {'id': last_key}
        
        leads_response = leads_table.scan(**scan_kwargs)
        leads = leads_response['Items']
        
        # Get contact methods for each lead
        enriched_leads = []
        for lead in leads:
            contact_response = contact_methods_table.query(
                IndexName='lead-id-index',
                KeyConditionExpression='lead_id = :lead_id',
                ExpressionAttributeValues={':lead_id': lead['id']}
            )
            
            lead_data = dict(lead)
            lead_data['contact_methods'] = contact_response['Items']
            enriched_leads.append(lead_data)
        
        result = {
            'leads': convert_decimals(enriched_leads),
            'count': len(enriched_leads),
            'last_key': leads_response.get('LastEvaluatedKey', {}).get('id') if 'LastEvaluatedKey' in leads_response else None
        }
        
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error listing leads: {str(e)}")
        return create_response(500, {'error': str(e)})
