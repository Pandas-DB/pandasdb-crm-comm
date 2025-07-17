import logging
import boto3
import os
import json
from decimal import Decimal
from datetime import datetime, timedelta
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

def get_last_activity_date(activities_table, lead_id):
    """Get the last activity date for a lead"""
    try:
        response = activities_table.query(
            IndexName='lead-id-created-at-index',
            KeyConditionExpression='lead_id = :lead_id',
            ExpressionAttributeValues={':lead_id': lead_id},
            ScanIndexForward=False,  # Get most recent first
            Limit=1,
            ProjectionExpression='created_at'
        )
        
        if response['Items']:
            return response['Items'][0]['created_at']
        return None
    except Exception as e:
        logger.warning(f"Error getting last activity for lead {lead_id}: {str(e)}")
        return None

def filter_leads_by_dates(leads, created_start, created_end, last_activity_start, last_activity_end, activities_table):
    """Filter leads by creation date and last activity date"""
    filtered_leads = []
    
    for lead in leads:
        # Filter by creation date
        if created_start or created_end:
            lead_created = lead.get('created_at', '')
            if lead_created:
                lead_date = lead_created[:10]  # Get YYYY-MM-DD part
                
                if created_start and lead_date < created_start:
                    continue
                if created_end and lead_date > created_end:
                    continue
        
        # Filter by last activity date (if specified)
        if last_activity_start or last_activity_end:
            last_activity = get_last_activity_date(activities_table, lead['id'])
            if last_activity:
                activity_date = last_activity[:10]  # Get YYYY-MM-DD part
                
                if last_activity_start and activity_date < last_activity_start:
                    continue
                if last_activity_end and activity_date > last_activity_end:
                    continue
            else:
                # If no activities found and we're filtering by activity date, exclude this lead
                continue
        
        filtered_leads.append(lead)
    
    return filtered_leads

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
    """List all leads with pagination, search, and date filtering functionality"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        last_key = query_params.get('last_key')
        search_query = query_params.get('search')
        
        # New date filter parameters
        created_start = query_params.get('created_start')
        created_end = query_params.get('created_end')
        last_activity_start = query_params.get('last_activity_start')
        last_activity_end = query_params.get('last_activity_end')
        
        # URL decode search query
        if search_query:
            search_query = urllib.parse.unquote(search_query).strip()
        
        dynamodb = boto3.resource('dynamodb')
        leads_table = dynamodb.Table(os.environ['LEADS_TABLE'])
        contact_methods_table = dynamodb.Table(os.environ['CONTACT_METHODS_TABLE'])
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        
        # If search query is provided, search across leads and contact methods
        if search_query:
            logger.info(f"Searching for: {search_query}")
            leads = search_leads_by_name_and_contact(leads_table, contact_methods_table, search_query)
        else:
            # Normal pagination scan
            scan_kwargs = {'Limit': limit * 2}  # Get more leads to account for filtering
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = {'id': last_key}
            
            leads_response = leads_table.scan(**scan_kwargs)
            leads = leads_response['Items']
        
        # Apply date filters if any are specified
        if created_start or created_end or last_activity_start or last_activity_end:
            logger.info(f"Applying date filters: created_start={created_start}, created_end={created_end}, last_activity_start={last_activity_start}, last_activity_end={last_activity_end}")
            leads = filter_leads_by_dates(leads, created_start, created_end, last_activity_start, last_activity_end, activities_table)
        
        # Sort by creation date (most recent first) if not searching
        if not search_query:
            leads.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        else:
            # Sort by name for consistent search results
            leads.sort(key=lambda x: x.get('name', '').lower())
        
        # Apply limit after filtering
        leads = leads[:limit]
        
        # Get contact methods and last activity for each lead
        enriched_leads = []
        for lead in leads:
            try:
                contact_response = contact_methods_table.query(
                    IndexName='lead-id-index',
                    KeyConditionExpression='lead_id = :lead_id',
                    ExpressionAttributeValues={':lead_id': lead['id']}
                )
                
                # Get last activity date
                last_activity = get_last_activity_date(activities_table, lead['id'])
                
                lead_data = dict(lead)
                lead_data['contact_methods'] = contact_response['Items']
                lead_data['last_activity_date'] = last_activity
                enriched_leads.append(lead_data)
            except Exception as e:
                logger.warning(f"Error getting contact methods for lead {lead['id']}: {str(e)}")
                # Include lead without contact methods if there's an error
                lead_data = dict(lead)
                lead_data['contact_methods'] = []
                lead_data['last_activity_date'] = None
                enriched_leads.append(lead_data)
        
        # Build result
        result = {
            'leads': convert_decimals(enriched_leads),
            'count': len(enriched_leads)
        }
        
        # Add search query to result if present
        if search_query:
            result['search_query'] = search_query
        
        # Add date filters to result if present
        if created_start or created_end or last_activity_start or last_activity_end:
            result['filters'] = {
                'created_start': created_start,
                'created_end': created_end,
                'last_activity_start': last_activity_start,
                'last_activity_end': last_activity_end
            }
        
        # Add pagination info only for non-search, non-filtered results
        if not search_query and not (created_start or created_end or last_activity_start or last_activity_end):
            result['last_key'] = leads_response.get('LastEvaluatedKey', {}).get('id') if 'LastEvaluatedKey' in leads_response else None
        
        logger.info(f"Returning {len(enriched_leads)} leads")
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"Error listing leads: {str(e)}")
        return create_response(500, {'error': str(e)})
