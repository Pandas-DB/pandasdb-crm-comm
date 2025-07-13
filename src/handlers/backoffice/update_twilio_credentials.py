import json
import boto3
import os
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,PUT,OPTIONS'
        },
        'body': json.dumps(body) if isinstance(body, dict) else body
    }

def get_twilio_credentials():
    """Get current Twilio credentials from environment variables"""
    try:
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID', '')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '')
        
        # Mask the auth token for security (show only last 4 characters)
        masked_token = ''
        if auth_token:
            masked_token = '*' * (len(auth_token) - 4) + auth_token[-4:] if len(auth_token) > 4 else '*' * len(auth_token)
        
        return {
            'account_sid': account_sid,
            'auth_token_masked': masked_token,
            'has_credentials': bool(account_sid and auth_token)
        }
        
    except Exception as e:
        logger.error(f"Error getting Twilio credentials: {str(e)}")
        return None

def update_lambda_environment(account_sid, auth_token):
    """Update Lambda environment variables with new Twilio credentials"""
    try:
        lambda_client = boto3.client('lambda')
        
        # Get current function configuration
        function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        if not function_name:
            return False, "Cannot determine current Lambda function name"
        
        # Get all Lambda functions that need to be updated
        functions_to_update = [
            function_name,  # Current function
            # Add other function names that need Twilio credentials
            function_name.replace('twilio-credentials', 'whatsapp-webhook'),
            function_name.replace('twilio-credentials', 'send-message')
        ]
        
        for func_name in functions_to_update:
            try:
                response = lambda_client.get_function_configuration(FunctionName=func_name)
                
                # Update environment variables
                env_vars = response.get('Environment', {}).get('Variables', {})
                env_vars['TWILIO_ACCOUNT_SID'] = account_sid
                env_vars['TWILIO_AUTH_TOKEN'] = auth_token
                
                lambda_client.update_function_configuration(
                    FunctionName=func_name,
                    Environment={'Variables': env_vars}
                )
                
                logger.info(f"Updated Twilio credentials for function: {func_name}")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    logger.warning(f"Function not found: {func_name}")
                    continue
                else:
                    raise e
        
        return True, "Credentials updated successfully"
        
    except Exception as e:
        logger.error(f"Error updating Lambda environment: {str(e)}")
        return False, str(e)

def lambda_handler(event, context):
    """Handle Twilio credentials management requests"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        http_method = event.get('httpMethod', 'GET')
        
        if http_method == 'GET':
            # Get current Twilio credentials
            credentials = get_twilio_credentials()
            if credentials is None:
                return create_response(500, {'error': 'Failed to load Twilio credentials'})
            
            return create_response(200, credentials)
            
        elif http_method == 'PUT':
            # Update Twilio credentials
            body = event.get('body', '{}')
            if event.get('isBase64Encoded'):
                import base64
                body = base64.b64decode(body).decode('utf-8')
            
            try:
                updates = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {'error': 'Invalid JSON in request body'})
            
            account_sid = updates.get('account_sid', '').strip()
            auth_token = updates.get('auth_token', '').strip()
            
            if not account_sid or not auth_token:
                return create_response(400, {'error': 'Both Account SID and Auth Token are required'})
            
            # Validate format (basic validation)
            if not account_sid.startswith('AC') or len(account_sid) != 34:
                return create_response(400, {'error': 'Invalid Account SID format'})
            
            if len(auth_token) != 32:
                return create_response(400, {'error': 'Invalid Auth Token format'})
            
            # Update Lambda environment variables
            success, message = update_lambda_environment(account_sid, auth_token)
            
            if success:
                return create_response(200, {'message': message})
            else:
                return create_response(500, {'error': message})
        
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        logger.error(f"Error in Twilio credentials handler: {str(e)}")
        return create_response(500, {'error': str(e)})
