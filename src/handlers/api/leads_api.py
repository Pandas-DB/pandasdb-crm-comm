import json
import os
import uuid
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Get table names from environment variables
LEADS_TABLE = os.environ['LEADS_TABLE']
CONTACT_METHODS_TABLE = os.environ['CONTACT_METHODS_TABLE']
CONTACT_METHOD_SETTINGS_TABLE = os.environ['CONTACT_METHOD_SETTINGS_TABLE']

# Initialize tables
leads_table = dynamodb.Table(LEADS_TABLE)
contact_methods_table = dynamodb.Table(CONTACT_METHODS_TABLE)
contact_method_settings_table = dynamodb.Table(CONTACT_METHOD_SETTINGS_TABLE)

def create_response(status_code, body, headers=None):
    """Create standardized API response"""
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }
    
    if headers:
        default_headers.update(headers)
    
    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body)
    }

def validate_contact_method(contact_method):
    """Validate contact method data"""
    required_fields = ['type', 'value']
    
    for field in required_fields:
        if field not in contact_method:
            return f"Missing required field: {field}"
    
    valid_types = ['phone', 'email', 'other']
    if contact_method['type'] not in valid_types:
        return f"Invalid contact method type. Must be one of: {', '.join(valid_types)}"
    
    if not contact_method['value'].strip():
        return "Contact method value cannot be empty"
    
    return None

def check_contact_method_exists(contact_type, value):
    """Check if contact method already exists"""
    type_value = f"{contact_type}#{value}"
    
    try:
        response = contact_methods_table.query(
            IndexName='type-value-index',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('type_value').eq(type_value)
        )
        return len(response['Items']) > 0
    except ClientError:
        return False

def create_lead(lead_data):
    """Create a new lead"""
    lead_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    lead_item = {
        'id': lead_id,
        'name': lead_data.get('name', '').strip(),
        'metadata': lead_data.get('metadata', {}),
        'created_at': timestamp,
        'updated_at': timestamp
    }
    
    leads_table.put_item(Item=lead_item)
    return lead_id, lead_item

def create_contact_method(lead_id, contact_method_data, is_primary=False):
    """Create a new contact method"""
    contact_method_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    contact_type = contact_method_data['type']
    value = contact_method_data['value'].strip()
    type_value = f"{contact_type}#{value}"
    
    # Create contact method
    contact_method_item = {
        'id': contact_method_id,
        'lead_id': lead_id,
        'type': contact_type,
        'value': value,
        'type_value': type_value,
        'created_at': timestamp,
        'updated_at': timestamp
    }
    
    contact_methods_table.put_item(Item=contact_method_item)
    
    # Create contact method settings
    settings_id = str(uuid.uuid4())
    settings_item = {
        'id': settings_id,
        'contact_method_id': contact_method_id,
        'is_primary': is_primary,
        'is_active': True,
        'created_at': timestamp,
        'updated_at': timestamp
    }
    
    contact_method_settings_table.put_item(Item=settings_item)
    
    return contact_method_id, contact_method_item, settings_item

def lambda_handler(event, context):
    """Main Lambda handler for leads API"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    # API key authentication is already handled by API Gateway
    # If the request reaches this function, the API key is valid
    
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Validate required fields
        if 'contact_methods' not in body or not isinstance(body['contact_methods'], list):
            return create_response(400, {
                'error': 'contact_methods field is required and must be an array'
            })
        
        if not body['contact_methods']:
            return create_response(400, {
                'error': 'At least one contact method is required'
            })
        
        # Validate each contact method
        for i, contact_method in enumerate(body['contact_methods']):
            validation_error = validate_contact_method(contact_method)
            if validation_error:
                return create_response(400, {
                    'error': f"Contact method {i + 1}: {validation_error}"
                })
        
        # Check for duplicate contact methods
        for contact_method in body['contact_methods']:
            if check_contact_method_exists(contact_method['type'], contact_method['value']):
                return create_response(409, {
                    'error': f"Contact method {contact_method['type']}:{contact_method['value']} already exists"
                })
        
        lead_id = body.get('lead_id')
        
        # If lead_id is provided, verify it exists
        if lead_id:
            try:
                response = leads_table.get_item(Key={'id': lead_id})
                if 'Item' not in response:
                    return create_response(404, {'error': f'Lead with id {lead_id} not found'})
                lead_item = response['Item']
            except ClientError as e:
                return create_response(500, {'error': f'Error retrieving lead: {str(e)}'})
        else:
            # Create new lead
            try:
                lead_id, lead_item = create_lead(body)
            except ClientError as e:
                return create_response(500, {'error': f'Error creating lead: {str(e)}'})
        
        # Create contact methods
        created_contact_methods = []
        
        for i, contact_method_data in enumerate(body['contact_methods']):
            try:
                # First contact method is primary by default
                is_primary = (i == 0)
                contact_method_id, contact_method_item, settings_item = create_contact_method(
                    lead_id, contact_method_data, is_primary
                )
                
                created_contact_methods.append({
                    'id': contact_method_id,
                    'type': contact_method_item['type'],
                    'value': contact_method_item['value'],
                    'is_primary': is_primary,
                    'is_active': True
                })
                
            except ClientError as e:
                return create_response(500, {
                    'error': f'Error creating contact method {i + 1}: {str(e)}'
                })
        
        # Prepare response
        response_data = {
            'success': True,
            'lead': {
                'id': lead_id,
                'name': lead_item.get('name', ''),
                'metadata': lead_item.get('metadata', {}),
                'created_at': lead_item['created_at'],
                'updated_at': lead_item['updated_at']
            },
            'contact_methods': created_contact_methods,
            'total_contact_methods': len(created_contact_methods)
        }
        
        return create_response(201, response_data)
        
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_response(500, {'error': 'Internal server error'})
