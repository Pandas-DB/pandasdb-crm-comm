import json
import logging
import boto3
import os
from urllib.parse import parse_qs
from twilio.request_validator import RequestValidator

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Webhook handler for platform messages (WhatsApp, Telegram, etc.).
    Normalizes data from all platforms to unified format for downstream processing.
    """
    
    try:
        # Get platform from query parameter (REQUIRED)
        platform = event.get('queryStringParameters', {}).get('platform', 'whatsapp')
        logger.info(f"Processing webhook for platform: {platform}")
        
        # Add debug logging
        logger.info(f"Raw event: {json.dumps(event, default=str)}")
        
        # Get headers safely - ensure it's always a dict
        headers = event.get('headers') or {}
        if not isinstance(headers, dict):
            headers = {}
        
        request_context = event.get('requestContext', {}) or {}
        
        # Parse and normalize webhook data based on platform
        if platform == 'whatsapp':
            normalized_data = parse_and_normalize_whatsapp(event, headers, request_context)
        elif platform == 'telegram':
            normalized_data = parse_and_normalize_telegram(event)
        else:
            logger.error(f"Unsupported platform: {platform}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Unsupported platform: {platform}'})
            }
        
        if not normalized_data:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid webhook data'})
            }
        
        logger.info(f"Normalized webhook data: {normalized_data}")
        
        # Construct Step Functions ARN from name
        state_machine_name = os.environ['STATE_MACHINE_NAME']
        region = os.environ.get('AWS_DEFAULT_REGION', 'eu-west-1')
        account_id = context.invoked_function_arn.split(':')[4]
        state_machine_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"
        
        logger.info(f"Using State Machine ARN: {state_machine_arn}")
        
        # Start Step Functions execution with normalized data
        stepfunctions_client = boto3.client('stepfunctions')
        
        execution_input = {
            'body': normalized_data  # Normalized data that all lambdas expect (platform included in body)
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

def parse_and_normalize_whatsapp(event, headers, request_context):
    """
    Parse WhatsApp webhook from Twilio and return normalized format.
    This is the "master" format that all other platforms will match.
    """
    try:
        # Parse Twilio webhook data (your original logic)
        body = event.get('body', '')
        logger.info(f"Raw WhatsApp body: {body}")
        
        content_type = headers.get('content-type', '') or headers.get('Content-Type', '')
        logger.info(f"Content type: {content_type}")
        
        if content_type.startswith('application/x-www-form-urlencoded'):
            logger.info("Parsing as form-encoded data")
            parsed_body = parse_qs(body)
            webhook_data = {k: v[0] if len(v) == 1 else v for k, v in parsed_body.items()}
        else:
            logger.info("Parsing as JSON data")
            webhook_data = json.loads(body) if body else {}
        
        # Validate Twilio signature
        validator = RequestValidator(os.environ['TWILIO_AUTH_TOKEN'])
        signature = headers.get('X-Twilio-Signature', '')
        url = f"https://{headers.get('Host', '')}{request_context.get('path', '')}"
        
        if not validator.validate(url, webhook_data, signature):
            logger.warning("Invalid Twilio signature - request rejected")
            return None
        
        logger.info("Twilio signature validated successfully")
        
        # Validate required fields
        required_fields = ['From', 'To', 'Body']
        for field in required_fields:
            if field not in webhook_data:
                logger.warning(f"Missing required field: {field}")
        
        # Add platform to top level for WhatsApp (for consistency)
        webhook_data['platform'] = 'whatsapp'
        
        # Add platform-specific metadata
        if 'metadata' not in webhook_data:
            webhook_data['metadata'] = {}
        
        # Return the WhatsApp format with platform info
        return webhook_data
        
    except Exception as e:
        logger.error(f"Error parsing WhatsApp webhook: {str(e)}")
        return None

def parse_and_normalize_telegram(event):
    """
    Parse Telegram webhook and normalize to match WhatsApp format.
    Maps Telegram fields to the expected WhatsApp field structure.
    """
    try:
        body = event.get('body', '')
        if event.get('isBase64Encoded'):
            import base64
            body = base64.b64decode(body).decode('utf-8')
        
        telegram_data = json.loads(body) if body else {}
        logger.info(f"Parsed Telegram data: {telegram_data}")
        
        # Extract Telegram message components
        message = telegram_data.get('message', {})
        chat = message.get('chat', {})
        from_user = message.get('from', {})
        
        # Map to WhatsApp format (what downstream lambdas expect)
        normalized_data = {
            # Core fields that match WhatsApp structure
            'From': f"whatsapp:+{chat.get('id', '')}",  # Format: whatsapp:+chatid
            'To': 'whatsapp:+telegram_bot',  # Standard bot identifier
            'Body': message.get('text', ''),
            'MessageSid': str(message.get('message_id', '')),
            'ProfileName': f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip() or 'Telegram User',
            'AccountSid': 'telegram_account',
            
            # Platform at top level for routing
            'platform': 'telegram',
            
            # Platform-specific metadata (business data only)
            'metadata': {
                'chat_id': chat.get('id'),
                'chat_type': chat.get('type', 'private'),
                'user_id': from_user.get('id'),
                'username': from_user.get('username', ''),
                'language_code': from_user.get('language_code', ''),
                'is_bot': from_user.get('is_bot', False),
                'message_date': message.get('date'),
                'raw_data': telegram_data
            }
        }
        
        logger.info(f"Normalized Telegram data: From={normalized_data['From']}, ProfileName={normalized_data['ProfileName']}")
        return normalized_data
        
    except Exception as e:
        logger.error(f"Error parsing Telegram webhook: {str(e)}")
        return None
