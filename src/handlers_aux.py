import json
import logging
import boto3
import os
from dataclasses import dataclass, field
from typing import Dict, Any


logger = logging.getLogger()
logger.setLevel(logging.INFO)


@dataclass
class NormalizedInputMessage:
    """Standardized message format for all platforms"""
    From: str
    To: str
    Body: str
    MessageSid: str
    ProfileName: str
    platform: str
    AccountSid: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate required fields after initialization"""
        required_fields = ['From', 'To', 'Body', 'MessageSid', 'ProfileName', 'platform']
        for field_name in required_fields:
            value = getattr(self, field_name)
            if not value or value.strip() == '':
                raise ValueError(f"Required field '{field_name}' cannot be empty")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'From': self.From,
            'To': self.To,
            'Body': self.Body,
            'MessageSid': self.MessageSid,
            'ProfileName': self.ProfileName,
            'AccountSid': self.AccountSid,
            'platform': self.platform,
            'metadata': self.metadata
        }


def validate_api_key(api_key):
    """
    Validate API key against AWS API Gateway.
    Returns True if valid, False otherwise.
    """
    try:
        client = boto3.client('apigateway')
        
        # Get all API keys and check if the provided key exists
        response = client.get_api_keys()
        
        for key_info in response.get('items', []):
            if key_info.get('value') == api_key:
                # Check if key is enabled
                return key_info.get('enabled', False)
        
        return False
    except Exception as e:
        logger.error(f"Error validating API key: {str(e)}")
        return False


def start_step_function_execution(normalized_message: NormalizedInputMessage, context):
    """
    Start Step Functions execution with normalized data
    """
    stepfunctions_client = boto3.client('stepfunctions')
    state_machine_name = os.environ['STATE_MACHINE_NAME']
    region = os.environ.get('AWS_DEFAULT_REGION', 'eu-west-1')
    account_id = context.invoked_function_arn.split(':')[4]
    state_machine_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"
    
    execution_input = {
        'flow_input': normalized_message.to_dict()  # Wrap in flow_input structure
    }
    
    response = stepfunctions_client.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(execution_input)
    )
    
    logger.info(f"Started Step Functions execution: {response['executionArn']}")
    return response


def get_platform_success_response(platform: str):
    """Return appropriate success response based on platform"""
    if platform == 'whatsapp':
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/xml'},
            'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        }
    elif platform == 'telegram':
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'ok': True})
        }
    elif platform == 'chat':
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'status': 'received'})
        }
    else:
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'ok': True})
        }


def get_platform_error_response(platform: str, error_message: str, status_code: int = 400):
    """Return appropriate error response based on platform"""
    if platform == 'whatsapp':
        # WhatsApp/Twilio expects 200 response even for errors
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/xml'},
            'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        }
    else:
        return {
            'statusCode': status_code,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': error_message})
        }


def handle_webhook_error(platform: str, error: Exception):
    """Handle webhook processing errors with appropriate platform response"""
    logger.error(f"Error processing {platform} webhook: {str(error)}", exc_info=True)
    return get_platform_success_response(platform)  # Return success to avoid retries
