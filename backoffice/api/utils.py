import json
from decimal import Decimal

def create_response(status_code, data):
    """Create standardized API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
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
