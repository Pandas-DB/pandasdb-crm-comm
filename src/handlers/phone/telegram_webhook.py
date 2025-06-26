import json
import logging
import os
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
    Telegram webhook handler for Telegram bot messages.
    """
    
    try:
        logger.info("Processing Telegram webhook")
        
        # Parse and normalize Telegram webhook data
        try:
            normalized_message = parse_and_normalize_telegram(event)
        except ValueError as e:
            logger.error(f"Telegram data validation error: {str(e)}")
            return get_platform_error_response('telegram', f'Invalid message data: {str(e)}', 400)
        
        if not normalized_message:
            return get_platform_error_response('telegram', 'Invalid webhook data', 400)
        
        logger.info(f"Normalized Telegram message: From={normalized_message.From}")
        
        # Start Step Functions execution
        start_step_function_execution(normalized_message, context)
        
        return get_platform_success_response('telegram')
        
    except Exception as e:
        return handle_webhook_error('telegram', e)


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
    
    # Extract main fields and put the rest in metadata
    main_fields = {'message_id', 'text', 'chat', 'from'}
    metadata = {k: v for k, v in telegram_data.items() if k not in main_fields}
    
    # Create normalized message object
    return NormalizedInputMessage(
        From=str(chat.get('id', '')),
        To='telegram_bot',
        Body=message.get('text', ''),
        MessageSid=str(message.get('message_id', '')),
        ProfileName=f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip() or 'Telegram User',
        AccountSid='telegram_account',
        platform='telegram',
        metadata=metadata
    )
