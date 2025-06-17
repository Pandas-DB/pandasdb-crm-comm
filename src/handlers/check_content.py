import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to check if the incoming WhatsApp message has content.
    Returns the processed message data or stops execution if empty.
    """
    
    try:
        # Extract webhook data from event
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract Twilio webhook data
        twilio_data = body
        
        # Extract relevant fields
        message_body = twilio_data.get('Body', '').strip()
        from_number = twilio_data.get('From', '')
        to_number = twilio_data.get('To', '')
        message_sid = twilio_data.get('MessageSid', '')
        profile_name = twilio_data.get('ProfileName', '')
        account_sid = twilio_data.get('AccountSid', '')
        
        logger.info(f"Processing message from {from_number}: {message_body}")
        
        # Check if message has content
        if not message_body:
            logger.info("Message has no content, stopping execution")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'action': 'stop',
                    'reason': 'empty_message'
                })
            }
        
        # Clean phone numbers (remove whatsapp: prefix)
        clean_from_number = from_number.replace('whatsapp:', '') if from_number else ''
        clean_to_number = to_number.replace('whatsapp:', '') if to_number else ''
        
        # Prepare response data for next lambda
        response_data = {
            'action': 'continue',
            'message_data': {
                'clean_phone_number': clean_from_number,
                'original_from': from_number,
                'original_to': to_number,
                'message_body': message_body,
                'message_sid': message_sid,
                'profile_name': profile_name or 'Unknown User',
                'account_sid': account_sid,
                'twilio_whatsapp_number': 'whatsapp:+14155238886'
            }
        }
        
        logger.info(f"Message has content, continuing with: {clean_from_number}")
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_data)
        }
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'action': 'error',
                'error': str(e)
            })
        }
