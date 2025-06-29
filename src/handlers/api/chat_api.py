import json
import logging
import os
import sys

sys.path.append('/opt/python')
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from handlers_aux import (
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
    Chat webhook handler for web chat platform messages.
    API key authentication is handled by API Gateway.
    """
    
    try:
        logger.info("Processing Chat webhook")
        
        # API key authentication is already handled by API Gateway
        # If the request reaches this function, the API key is valid
        logger.info("Chat platform request authorized by API Gateway")
        
        # Parse and normalize chat webhook data
        try:
            normalized_message = parse_and_normalize_chat(event)
        except ValueError as e:
            logger.error(f"Chat data validation error: {str(e)}")
            return get_platform_error_response('chat', f'Invalid message data: {str(e)}', 400)
        
        if not normalized_message:
            return get_platform_error_response('chat', 'Invalid webhook data', 400)
        
        logger.info(f"Normalized Chat message: From={normalized_message.From}")
        
        # Start Step Functions execution
        start_step_function_execution(normalized_message, context)
        
        return get_platform_success_response('chat')
        
    except Exception as e:
        return handle_webhook_error('chat', e)

def parse_and_normalize_chat(event) -> NormalizedInputMessage:
    """Parse chat platform webhook and return normalized message object"""
    body = event.get('body', '')
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body).decode('utf-8')
    
    # Parse JSON body for chat platform
    try:
        chat_data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        # If not JSON, treat body as plain text message
        chat_data = {'message': body}
    
    # Extract main fields and put the rest in metadata
    main_fields = {'from', 'to', 'message', 'text', 'id', 'name'}
    metadata = {k: v for k, v in chat_data.items() if k.lower() not in main_fields}
    
    # Create normalized message object for chat platform
    return NormalizedInputMessage(
        From=chat_data.get('from', 'chat_user'),
        To=chat_data.get('to', 'chat_bot'),
        Body=chat_data.get('message', '') or chat_data.get('text', ''),
        MessageSid=chat_data.get('id', f"chat_{hash(body)}"),
        ProfileName=chat_data.get('name', 'Chat User'),
        AccountSid='chat_account',
        platform='chat',
        metadata=metadata
    )
