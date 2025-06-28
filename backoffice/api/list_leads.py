import logging
import boto3
import os
from utils import create_response, convert_decimals

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
