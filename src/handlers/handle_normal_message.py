import json
import logging
import boto3
import os
from datetime import datetime
import uuid

from aux import load_business_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to handle normal (non-spam) messages.
    Uses Bedrock AI agent with knowledge base and conversation history.
    """
    
    try:
        # Parse input from previous lambda
        flow_input = event.get('flow_input', {})
        if isinstance(flow_input, str):
            flow_input = json.loads(flow_input)
            
        lead_id = event.get('lead_id')
        contact_method_id = event.get('contact_method_id')
        platform = flow_input.get('platform')
        
        clean_phone_number = flow_input.get('From', '')
        message_body = flow_input.get('Body', '')
        message_sid = flow_input.get('MessageSid', '')
        profile_name = flow_input.get('ProfileName', '')
        original_to = flow_input.get('To', '')
        
        logger.info(f"Processing normal message for lead {lead_id}: {message_body[:100]}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        # Get conversation history
        conversation_history = get_conversation_history(lead_id)
        
        # Prepare conversation context for AI
        conversation_context = f"""
        Lead Information:
        - Name: {profile_name}
        - Phone: {clean_phone_number}
        
        Current Message: {message_body}
        
        Previous Conversations (JSON format): {json.dumps(conversation_history)}
        """
        
        # Initialize Bedrock client
        bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.environ.get('AWS_REGION', 'eu-west-1')
        )
        
        # Load system prompt from S3 or raise error
        system_prompt = load_system_prompt_from_s3()
        config = load_business_config()
        
        if not system_prompt:
            raise Exception("System prompt not found in S3")
        system_prompt = f'''{system_prompt} 
          ## CRITICAL RESPONSE RULES
          - MAXIMUM {config['message_limits']['max_response_characters']} characters per response - this is MANDATORY
          - Use short sentences and abbreviations when needed
        '''
        
        # Prepare the request for Bedrock
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": conversation_context
                }
            ]
        }
        
        # Call Bedrock AI
        response = bedrock_runtime.invoke_model(
            body=json.dumps(body),
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            accept='application/json',
            contentType='application/json'
        )
        
        # Parse AI response
        response_body = json.loads(response.get('body').read())
        ai_response = response_body.get('content', [{}])[0].get('text', '')
        
        # Ensure response is within character limit
        if len(ai_response) > config['message_limits']['character_limit_fallback']:
            ai_response = ai_response[:config['message_limits']['character_limit_truncate']] + "..."
            
        
        logger.info(f"AI generated response: {ai_response}")
        
        timestamp = datetime.now().isoformat()
        
        # Create activity record
        activity_id = str(uuid.uuid4())
        activities_table.put_item(
            Item={
                'id': activity_id,
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'activity_type': platform,
                'status': 'completed',
                'direction': 'inbound',
                'completed_at': timestamp,
                'created_at': timestamp,
                'metadata': {
                    'messageSid': message_sid,
                    'profileName': profile_name,
                    'messageType': 'text',
                    'platform': platform
                }
            }
        )
        
        # Store activity content
        activity_content_table.put_item(
            Item={
                'id': str(uuid.uuid4()),
                'activity_id': activity_id,
                'content_type': platform,
                'content': {
                    'leadMessage': message_body,
                    'assistantMessage': ai_response
                },
                'created_at': timestamp
            }
        )
        
        response_data = {
            'action': 'message_processed',
            'activity_id': activity_id,
            'ai_response': ai_response,
            'conversation_history_count': len(conversation_history),
            'flow_input': flow_input,
            'send_message': {
                'platform': platform,
                'to': clean_phone_number,
                'message': ai_response,
                'from': original_to
            }
        }
        
        logger.info(f"Normal message processed successfully for lead {lead_id}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error processing normal message: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }

def get_conversation_history(lead_id):
    """Get conversation history for the lead"""
    try:
        config = load_business_config()
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        # Get recent activities for this lead
        response = activities_table.query(
            IndexName='lead-id-created-at-index',
            KeyConditionExpression='lead_id = :lead_id',
            ExpressionAttributeValues={':lead_id': lead_id},
            ScanIndexForward=False,  # Most recent first
            Limit=config['message_limits']['conversation_history_limit']
        )
        
        conversation_history = []
        for activity in response['Items']:
            # Get content for each activity
            content_response = activity_content_table.query(
                IndexName='activity-id-index',
                KeyConditionExpression='activity_id = :activity_id',
                ExpressionAttributeValues={':activity_id': activity['id']}
            )
            
            if content_response['Items']:
                content = content_response['Items'][0]['content']
                conversation_history.append({
                    'timestamp': activity.get('created_at', ''),
                    'lead_message': content.get('leadMessage', ''),
                    'assistant_message': content.get('assistantMessage', '')
                })
        
        return conversation_history
        
    except Exception as e:
        logger.warning(f"Error getting conversation history: {str(e)}")
        return []

def load_system_prompt_from_s3():
    """Load system prompt from S3 file. Returns None if file doesn't exist or error occurs."""
    try:
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_KNOWLEDGE_BUCKET')
        file_key = os.environ.get('S3_KNOWLEDGE_FILE', 'knowledge/system_prompt.txt')
        
        if not bucket_name:
            logger.info("No S3 bucket configured, using default system prompt")
            return None
            
        response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        system_prompt = response['Body'].read().decode('utf-8')
        logger.info(f"Loaded system prompt from S3: {bucket_name}/{file_key}")
        return system_prompt
        
    except Exception as e:
        logger.warning(f"Could not load system prompt from S3: {str(e)}, using default")
        return None
