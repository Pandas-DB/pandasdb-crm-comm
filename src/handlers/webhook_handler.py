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
       # Validate Twilio signature
       validator = RequestValidator(os.environ['TWILIO_AUTH_TOKEN'])
       signature = event.get('headers', {}).get('X-Twilio-Signature', '')
       url = f"https://{event['headers']['Host']}{event['requestContext']['path']}"
       
       if not validator.validate(url, event.get('body', ''), signature):
           logger.warning("Invalid Twilio signature")
           return {
               'statusCode': 403,
               'headers': {'Content-Type': 'application/xml'},
               'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
           }
       
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
       logger.error(f"Error processing webhook: {str(e)}")
       return {
           'statusCode': 500,
           'headers': {
               'Content-Type': 'application/xml'
           },
           'body': '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
       }
