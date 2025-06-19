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
    Webhook handler for Twilio WhatsApp messages.
    Starts Step Functions execution for message processing.
    """
    
    try:
        # Add debug logging
        logger.info(f"Raw event: {json.dumps(event, default=str)}")
        
        # Get headers safely - ensure it's always a dict
        headers = event.get('headers') or {}
        if not isinstance(headers, dict):
            headers = {}
        
        request_context = event.get('requestContext', {}) or {}
        
        # Parse Twilio webhook data FIRST
        body = event.get('body', '')
        logger.info(f"Raw body: {body}")
        
        # Check content type safely - try both lowercase and capitalized
        content_type = headers.get('content-type', '') or headers.get('Content-Type', '')
        logger.info(f"Content type: {content_type}")
        
        # Parse the body correctly based on content type
        if content_type.startswith('application/x-www-form-urlencoded'):
            logger.info("Parsing as form-encoded data")
            parsed_body = parse_qs(body)
            webhook_data = {k: v[0] if len(v) == 1 else v for k, v in parsed_body.items()}
        else:
            logger.info("Parsing as JSON data")
            webhook_data = json.loads(body) if body else {}
        
        logger.info(f"Parsed webhook data: {webhook_data}")
        
        # Validate Twilio signature - ALWAYS REQUIRED
        validator = RequestValidator(os.environ['TWILIO_AUTH_TOKEN'])
        signature = headers.get('X-Twilio-Signature', '')
        url = f"https://{headers.get('Host', '')}{request_context.get('path', '')}"
        
        # Pass the parsed webhook_data (dict) instead of raw body (string)
        if not validator.validate(url, webhook_data, signature):
            logger.warning("Invalid Twilio signature - request rejected")
            return {
                'statusCode': 403,
                'headers': {'Content-Type': 'application/xml'},
                'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
            }
        
        logger.info("Twilio signature validated successfully")
        
        # Validate required fields
        required_fields = ['From', 'To', 'Body']
        for field in required_fields:
            if field not in webhook_data:
                logger.warning(f"Missing required field: {field}")
        
        # Construct Step Functions ARN from name
        state_machine_name = os.environ['STATE_MACHINE_NAME']
        region = os.environ.get('AWS_DEFAULT_REGION', 'eu-west-1')
        account_id = context.invoked_function_arn.split(':')[4]
        state_machine_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"
        
        logger.info(f"Using State Machine ARN: {state_machine_arn}")
        
        # Start Step Functions execution
        stepfunctions_client = boto3.client('stepfunctions')
        
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
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        # Still return 200 to Twilio to avoid retries
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/xml'
            },
            'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        }
