import logging
import boto3
import os
import json
from decimal import Decimal
from botocore.exceptions import ClientError
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

def search_leads_by_name_and_contact(leads_table, contact_methods_table, search_query):
    """Search leads by name or contact method"""
    search_query_lower = search_query.lower()
    matching_leads = []
    lead_ids_found = set()
    
    # Search by lead name
    try:
        leads_response = leads_table.scan()
        leads = leads_response['Items']
        
        # Handle pagination for leads
        while 'LastEvaluatedKey' in leads_response:
            leads_response = leads_table.scan(ExclusiveStartKey=leads_response['LastEvaluatedKey'])
            leads.extend(leads_response['Items'])
        
        # Filter leads by name
        for lead in leads:
            lead_name = lead.get('name', '').lower()
            if search_query_lower in lead_name:
                lead_ids_found.add(lead['id'])
                matching_leads.append(lead)
    except Exception as e:
        logger.error(f"Error searching leads by name: {str(e)}")
    
    # Search by contact method
    try:
        contact_response = contact_methods_table.scan()
        contacts = contact_response['Items']
        
        # Handle pagination for contacts
        while 'LastEvaluatedKey' in contact_response:
            contact_response = contact_methods_table.scan(ExclusiveStartKey=contact_response['LastEvaluatedKey'])
            contacts.extend(contact_response['Items'])
        
        # Find matching contact methods
        matching_lead_ids = set()
        for contact in contacts:
            contact_value = contact.get('value', '').lower()
            contact_type = contact.get('type', '').lower()
            if search_query_lower in contact_value or search_query_lower in contact_type:
                matching_lead_ids.add(contact['lead_id'])
        
        # Get leads for matching contact methods (if not already found by name)
        for lead_id in matching_lead_ids:
            if lead_id not in lead_ids_found:
                try:
                    lead_response = leads_table.get_item(Key={'id': lead_id})
                    if 'Item' in lead_response:
                        matching_leads.append(lead_response['Item'])
                        lead_ids_found.add(lead_id)
                except Exception as e:
                    logger.warning(f"Error getting lead {lead_id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error searching contact methods: {str(e)}")
    
    return matching_leads

def lambda_handler(event, context):
    """List all leads with pagination and search functionality"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        last_key = query_params.get('last_key')
        search_query = query_params.get('search')
        
        # URL decode search query
        if search_query:
            search_query = urllib.parse.unquote(search_query).strip()
        
        dynamodb = boto3.resource('dynamodb')
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        
        # If search query is provided, search across leads and contact methods
        if search_query:
            logger.info(f"Searching for: {search_query}")
            leads = search_leads_by_name_and_contact(leads_table, contact_methods_table, search_query)
            
            # Sort by name for consistent results
            leads.sort(key=lambda x: x.get('name', '').lower())
            
            # Apply limit for search results
            leads = leads[:limit]
        else:
            # Normal pagination scan
            scan_kwargs = {'Limit': limit}
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = {'id': last_key}
            
            leads_response = leads_table.scan(**scan_kwargs)
            leads = leads_response['Items']
        
        # Get contact methods for each lead
        enriched_leads = []
        for lead in leads:
            try:
                contact_response = contact_methods_table.query(
                    IndexName='lead-id-index',
                    KeyConditionExpression='lead_id = :lead_id',
                    ExpressionAttributeValues={':lead_id': lead['id']}
                )
                
                lead_data = dict(lead)
                lead_data['contact_methods'] = contact_response['Items']
                enriched_leads.append(lead_data)
            except Exception as e:
                logger.warning(f"Error getting contact methods for lead {lead['id']}: {str(e)}")
                # Include lead without contact methods if there's an error
                lead_data = dict(lead)
                lead_data['contact_methods'] = []
                enriched_leads.append(lead_data)
        
        # For search results, don't include pagination info
        if search_query:
            result = {
                'leads': convert_decimals(enriched_leads),
                'count': len(enriched_leads),
                'search_query': search_query
            }
        else:
            result = {
                'leads': convert_decimals(enriched_leads),
                'count': len(enriched_leads),
                'last_key': leads_response.get('LastEvaluatedKey', {}).get('id') if 'LastEvaluatedKey' in leads_response else None
            }
        
        logger.info(f"Returning {len(enriched_leads)} leads")
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error listing leads: {str(e)}")
        return create_response(500, {'error': str(e)})
