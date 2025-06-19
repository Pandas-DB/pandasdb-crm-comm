import json
import logging
import boto3
import os
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to check if message is spam using Bedrock.
    Uses Claude/other model to analyze message content.
    """
    
    try:
        # Parse input from previous lambda
        if isinstance(event.get('body'), str):
            input_data = json.loads(event.get('body'))
        else:
            input_data = event.get('body', event)
            
        message_data = input_data.get('message_data', {})
        message_body = message_data.get('message_body', '')
        is_existing_spammer = input_data.get('is_spammer', False)
        
        logger.info(f"Analyzing message for spam: {message_body[:100]}...")
        
        # If already flagged as spammer, skip AI check
        if is_existing_spammer:
            logger.info("User already flagged as spammer, skipping AI check")
            return {
                'body': {
                    'is_spam': True,
                    'spam_reason': 'existing_spammer',
                    'confidence': 1.0,
                    **input_data
                }
            }
        
        # Initialize Bedrock client - USE CORRECT REGION!
        # Get region from environment or default to eu-west-1
        aws_region = os.environ.get('AWS_REGION', 'eu-west-1')
        
        bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=aws_region  # ✅ NOW USING CORRECT REGION
        )
        
        # Prepare the prompt for spam detection
        spam_detection_prompt = f"""
        Analyze the following message and determine if it's spam, meaningless, or a legitimate conversation message.

        Message: "{message_body}"

        Consider the message spam if it:
        - Contains repetitive meaningless text
        - Has promotional content without context
        - Contains suspicious links or requests
        - Is clearly automated or bot-generated
        - Has no conversational value

        Respond with a JSON object containing:
        - "is_spam": true/false
        - "confidence": 0.0-1.0 (confidence level)
        - "reason": brief explanation

        Example response: {{"is_spam": true, "confidence": 0.9, "reason": "repetitive meaningless text"}}
        """
        
        # Prepare the request body for Claude
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "messages": [
                {
                    "role": "user",
                    "content": spam_detection_prompt
                }
            ]
        }
        
        # Call Bedrock
        response = bedrock_runtime.invoke_model(
            body=json.dumps(body),
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            accept='application/json',
            contentType='application/json'
        )
        
        # Parse response
        response_body = json.loads(response.get('body').read())
        ai_response = response_body.get('content', [{}])[0].get('text', '')
        
        logger.info(f"Bedrock response: {ai_response}")
        
        # Parse AI response
        try:
            spam_analysis = json.loads(ai_response)
            is_spam = spam_analysis.get('is_spam', False)
            confidence = spam_analysis.get('confidence', 0.5)
            reason = spam_analysis.get('reason', 'AI analysis')
        except:
            # Fallback parsing if JSON is malformed
            is_spam = 'true' in ai_response.lower() and 'spam' in ai_response.lower()
            confidence = 0.7
            reason = 'AI analysis with fallback parsing'
        
        logger.info(f"Spam detection result: {is_spam}, confidence: {confidence}")
        
        # Prepare response
        response_data = {
            'is_spam': is_spam,
            'spam_reason': reason,
            'confidence': confidence,
            'ai_response': ai_response,
            **input_data
        }
        
        return {
            'body': response_data
        }
        
    except ClientError as e:
        logger.error(f"Bedrock client error: {str(e)}")
        # Fallback: return non-spam if Bedrock fails
        return {
            'body': {
                'is_spam': False,
                'spam_reason': 'bedrock_error',
                'confidence': 0.0,
                'error': str(e),
                **input_data
            }
        }
        
    except Exception as e:
        logger.error(f"Error in spam detection: {str(e)}")
        return {
            'body': {
                'action': 'error',
                'error': str(e)
            }
        }
