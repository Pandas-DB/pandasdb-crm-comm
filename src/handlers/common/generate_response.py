import yaml
import json
import logging
import boto3
import os
import uuid
import sys
import re

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aux import load_business_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to generate AI response for normal (non-spam) messages.
    Uses Bedrock AI agent with knowledge base and conversation history.
    """
    
    try:
        # Parse input from previous lambda
        flow_input = event.get('flow_input', {})
        if isinstance(flow_input, str):
            flow_input = yaml.safe_load(flow_input)
            
        lead_id = event.get('lead_id')
        contact_method_id = event.get('contact_method_id')
        activity_id = event.get('activity_id')
        platform = flow_input['platform']
        
        clean_phone_number = flow_input.get('From', '')
        message_body = flow_input.get('Body', '')
        profile_name = flow_input.get('ProfileName', '')
        original_to = flow_input.get('To', '')
        
        logger.info(f"Generating response for lead {lead_id}: {message_body[:100]}")
        
        # Get conversation history
        conversation_history = get_conversation_history(lead_id, platform)
        
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
        
        # Get platform-specific config or default
        platform_config = config['reply_length'].get(platform, config['reply_length']['default'])
        
        if not system_prompt:
            raise Exception("System prompt not found in S3")
        system_prompt = f'''{system_prompt} 
          ## CRITICAL RESPONSE RULES
          - MAXIMUM {platform_config['max_response_characters']} characters per response - this is MANDATORY
          - Use short sentences and abbreviations when needed
        '''
        
        # Prepare the request for Bedrock
        body = {
            "anthropic_version": config['ai_models']['bedrock_version'],
            "max_tokens": config['ai_models']['max_tokens_conversation'],
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
            modelId=config['ai_models']['bedrock_model_id'],
            accept='application/json',
            contentType='application/json'
        )
        
        # Parse AI response
        response_body = json.loads(response.get('body').read())
        ai_response = response_body.get('content', [{}])[0].get('text', '')
        
        # Split message if it's too long (> N characters)
        max_length = platform_config['character_limit_fallback']
        ai_responses = split_message_by_stops(ai_response, max_length)
        
        logger.info(f"AI generated response: {ai_response}")
        
        response_data = {
            'action': 'message_processed',
            'activity_id': activity_id,
            'ai_response': ai_responses,
            'conversation_history_count': len(conversation_history),
            'flow_input': flow_input,
            'send_message': {
                'platform': platform,
                'to': clean_phone_number,
                'messages': ai_responses,
                'from': original_to,
                'answer_to_activity_id': activity_id
            }
        }
        
        logger.info(f"Response generated successfully for lead {lead_id}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }

def split_message_by_stops(message, max_length):
    """
    Split a message into multiple parts by stops when it exceeds max_length.
    Returns a list of messages.
    """
    if len(message) <= max_length:
        return [message]
    
    # Define stop patterns (sentence endings)
    stop_patterns = ['. ', '! ', '? ', '.\n', '!\n', '?\n']
    
    messages = []
    current_message = ""
    
    # Split the message into sentences
    sentences = re.split(r'([.!?])', message)
    
    i = 0
    while i < len(sentences):
        part = sentences[i]
        
        # Reconstruct sentence with punctuation
        if i + 1 < len(sentences) and sentences[i + 1] in ['.', '!', '?']:
            part += sentences[i + 1]
            i += 2
        else:
            i += 1
        
        # Check if adding this part would exceed max_length
        if len(current_message + part) > max_length:
            if current_message:
                messages.append(current_message.strip())
                current_message = part
            else:
                # Single part is too long, force split by characters
                messages.append(part[:max_length])
                current_message = part[max_length:]
        else:
            current_message += part
    
    # Add remaining content
    if current_message.strip():
        messages.append(current_message.strip())
    
    # Filter out empty messages
    messages = [msg for msg in messages if msg.strip()]
    
    return messages

def get_conversation_history(lead_id, platform):
    """Get conversation history for the lead"""
    try:
        config = load_business_config()
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        # Get platform-specific config or default
        platform_config = config['reply_length'].get(platform, config['reply_length']['default'])
        
        # Get recent activities for this lead
        response = activities_table.query(
            IndexName='lead-id-created-at-index',
            KeyConditionExpression='lead_id = :lead_id',
            ExpressionAttributeValues={':lead_id': lead_id},
            ScanIndexForward=False,  # Most recent first
            Limit=platform_config['conversation_history_limit']
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
