import json
import logging
import boto3
import os
from urllib.parse import parse_qs
from twilio.request_validator import RequestValidator
from dataclasses import dataclass, field
from typing import Dict, Any


logger = logging.getLogger()
logger.setLevel(logging.INFO)


# this specifies the output structure of this lambda
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

def lambda_handler(event, context):
    """
    Webhook handler for platform messages (WhatsApp, Telegram, etc.).
    Normalizes data from all platforms to unified format for downstream processing.
    """
    
    try:
        # Get platform from query parameter (REQUIRED)
        platform = event.get('queryStringParameters', {}).get('platform')
        if not platform:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Platform parameter is required'})
            }
            
        logger.info(f"Processing webhook for platform: {platform}")
        
        # Parse and normalize webhook data based on platform
        try:
            if platform == 'whatsapp':
                normalized_message = parse_and_normalize_whatsapp(event)
            elif platform == 'telegram':
                normalized_message = parse_and_normalize_telegram(event)
            else:
                logger.error(f"Unsupported platform: {platform}")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': f'Unsupported platform: {platform}'})
                }
        except ValueError as e:
            logger.error(f"Data validation error: {str(e)}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Invalid message data: {str(e)}'})
            }
        
        if not normalized_message:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid webhook data'})
            }
        
        logger.info(f"Normalized message: From={normalized_message.From}, Platform={normalized_message.platform}")
        
        # Start Step Functions execution with normalized data
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
        
        # Return appropriate response based on platform
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
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        # Return platform-appropriate error response
        if platform == 'whatsapp':
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/xml'},
                'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
            }
        else:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'ok': True})
            }

def parse_and_normalize_whatsapp(event) -> NormalizedInputMessage:
    """Parse WhatsApp webhook and return normalized message object"""
    headers = event.get('headers') or {}
    request_context = event.get('requestContext', {}) or {}
    
    # Parse Twilio webhook data
    body = event.get('body', '')
    content_type = headers.get('content-type', '') or headers.get('Content-Type', '')
    
    if content_type.startswith('application/x-www-form-urlencoded'):
        parsed_body = parse_qs(body)
        webhook_data = {k: v[0] if len(v) == 1 else v for k, v in parsed_body.items()}
    else:
        webhook_data = json.loads(body) if body else {}
    
    # Validate Twilio signature
    validator = RequestValidator(os.environ['TWILIO_AUTH_TOKEN'])
    signature = headers.get('X-Twilio-Signature', '')
    url = f"https://{headers.get('Host', '')}{request_context.get('path', '')}"
    
    if not validator.validate(url, webhook_data, signature):
        logger.warning("Invalid Twilio signature - request rejected")
        return None
    
    # Extract main fields and put the rest in metadata
    main_fields = {'From', 'To', 'Body', 'MessageSid', 'ProfileName', 'AccountSid'}
    metadata = {k: v for k, v in webhook_data.items() if k not in main_fields}
    
    # Create normalized message object
    return NormalizedInputMessage(
        From=webhook_data.get('From', '').replace('whatsapp:', ''),  # Remove prefix
        To=webhook_data.get('To', '').replace('whatsapp:', ''),     # Remove prefix
        Body=webhook_data.get('Body', ''),
        MessageSid=webhook_data.get('MessageSid', ''),
        ProfileName=webhook_data.get('ProfileName', 'Unknown User'),
        AccountSid=webhook_data.get('AccountSid', ''),
        platform='whatsapp',
        metadata=metadata
    )

def parse_and_normalize_telegram(event) -> NormalizedInputMessage:
    """Parse Telegram webhook and return normalized message object"""
    body = event.get('body', '')
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body).decode('utf-8')
    
    telegram_data = json.loads(body) if body else {}
    message = telegram_data.get('message', {})
    chat = message.get('chat', {})
    from_user = message.get('from', {})
    
    # Create normalized message object
    return NormalizedInputMessage(
        From=str(chat.get('id', '')),
        To='telegram_bot',
        Body=message.get('text', ''),
        MessageSid=str(message.get('message_id', '')),
        ProfileName=f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip() or 'Telegram User',
        AccountSid='telegram_account',
        platform='telegram',
        metadata={
            'chat_id': chat.get('id'),
            'chat_type': chat.get('type', 'private'),
            'user_id': from_user.get('id'),
            'username': from_user.get('username', ''),
            'language_code': from_user.get('language_code', ''),
            'is_bot': from_user.get('is_bot', False),
            'message_date': message.get('date'),
            'raw_data': telegram_data
        }
    )
