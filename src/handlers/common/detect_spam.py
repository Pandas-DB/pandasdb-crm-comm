import yaml
import json
import logging
import boto3
import os
import sys
from botocore.exceptions import ClientError

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aux import load_business_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to check if message is spam using Bedrock.
    Uses Claude/other model to analyze message content.
    """
    
    try:
        # Parse input from previous lambda - the event IS the input data
        input_data = event
        
        # Extract mandatory fields - no defaults, will raise KeyError if missing
        flow_input = input_data['flow_input']
        message_body = flow_input['Body']
        is_existing_spammer = input_data['is_spammer']
        
        logger.info(f"Analyzing message for spam: {message_body[:100]}...")
        
        # If already flagged as spammer, skip AI check
        if is_existing_spammer:
            logger.info("User already flagged as spammer, skipping AI check")
            return {
                'is_spam': True,
                'spam_reason': 'existing_spammer',
                'confidence': 1.0,
                **input_data
            }
        
        # Initialize Bedrock client - USE CORRECT REGION!
        # Get region from environment or default to eu-west-1
        aws_region = os.environ.get('AWS_REGION', 'eu-west-1')
        
        bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=aws_region
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
        
        config = load_business_config()
        # Prepare the request body for Claude
        body = {
            "anthropic_version": config['ai_models']['bedrock_version'],
            "max_tokens": config['ai_models']['max_tokens_spam_detection'],
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
            modelId=config['ai_models']['bedrock_model_id'],
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
            confidence = config['spam_detection']['fallback_confidence']
            reason = 'AI analysis with fallback parsing'
        
        # Check confidence threshold
        ai_confidence_threshold = config['spam_detection']['ai_confidence_threshold']
        if is_spam and confidence < ai_confidence_threshold:
            logger.info(f"Spam confidence {confidence} below threshold {ai_confidence_threshold}, treating as non-spam")
            is_spam = False
            reason = f"Low confidence: {reason}"
        
        logger.info(f"Spam detection result: {is_spam}, confidence: {confidence}")
        
        # Prepare response
        response_data = {
            'is_spam': is_spam,
            'spam_reason': reason,
            'confidence': confidence,
            'ai_response': ai_response,
            **input_data
        }
        
        return response_data
        
    except ClientError as e:
        logger.error(f"Bedrock client error: {str(e)}")
        # Fallback: return non-spam if Bedrock fails
        return {
            'is_spam': False,
            'spam_reason': 'bedrock_error',
            'confidence': 0.0,
            'error': str(e),
            **input_data
        }
        
    except Exception as e:
        logger.error(f"Error in spam detection: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }
