import json
import logging
import boto3
import os
from urllib.parse import parse_qs

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Webhook handler for Twilio WhatsApp messages.
    Starts Step Functions execution for message processing.
    """
    
    try:
        # Parse Twilio webhook data
        body = event.get('body', '')
        
        # Twilio sends data as form-encoded
        if event.get('headers', {}).get('content-type', '').startswith('application/x-www-form-urlencoded'):
            parsed_body = parse_qs(body)
            # Convert single-item lists to strings
            webhook_data = {k: v[0] if len(v) == 1 else v for k, v in parsed_body.items()}
        else:
            # Handle JSON format if needed
            webhook_data = json.loads(body) if body else {}
        
        logger.info(f"Received webhook: {webhook_data}")
        
        # Validate required fields
        required_fields = ['From', 'To', 'Body']
        for field in required_fields:
            if field not in webhook_data:
                logger.warning(f"Missing required field: {field}")
        
        # Start Step Functions execution
        stepfunctions_client = boto3.client('stepfunctions')
        state_machine_arn = os.environ['STATE_MACHINE_ARN']
        
        execution_input = {
            'body': webhook_data
        }
        
        response = stepfunctions_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(execution_input)
        )
        
        logger.info(f"Started Step Functions execution: {response['executionArn']}")
        
        # Return TwiML response for Twilio
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/xml'
            },
            'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        }
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/xml'
            },
            'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        }
