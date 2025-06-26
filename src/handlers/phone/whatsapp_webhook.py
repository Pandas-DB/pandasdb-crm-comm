import json
import logging
import os
from urllib.parse import parse_qs
from twilio.request_validator import RequestValidator
import sys
sys.path.append('/opt/python')
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from webhook_utils import (
    NormalizedInputMessage, 
    start_step_function_execution, 
    get_platform_success_response,
    get_platform_error_response,
    handle_webhook_error
)


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    WhatsApp webhook handler for Twilio WhatsApp messages.
    """
    
    try:
        logger.info("Processing WhatsApp webhook")
        
        # Parse and normalize WhatsApp webhook data
        try:
            normalized_message = parse_and_normalize_whatsapp(event)
        except ValueError as e:
            logger.error(f"WhatsApp data validation error: {str(e)}")
            return get_platform_error_response('whatsapp', f'Invalid message data: {str(e)}', 400)
        
        if not normalized_message:
            return get_platform_error_response('whatsapp', 'Invalid webhook data', 400)
        
        logger.info(f"Normalized WhatsApp message: From={normalized_message.From}")
        
        # Start Step Functions execution
        start_step_function_execution(normalized_message, context)
        
        return get_platform_success_response('whatsapp')
        
    except Exception as e:
        return handle_webhook_error('whatsapp', e)


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
