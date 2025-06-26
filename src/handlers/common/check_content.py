import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to check if the incoming message has content.
    Returns the same input data or stops execution if empty.
    """
    
    try:
        # Extract flow_input from event
        flow_input = event.get('flow_input', {})
        if isinstance(flow_input, str):
            flow_input = json.loads(flow_input)
        
        # Check if message has content
        message_body = flow_input.get('Body', '').strip()
        
        if not message_body:
            logger.info("Message has no content, stopping execution")
            return {
                'flow_input': {
                    'action': 'stop',
                    'reason': 'empty_message'
                }
            }
        
        logger.info(f"Message has content, continuing with same data")
        
        # Return the SAME flow_input data unchanged
        return {
            'flow_input': flow_input
        }
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return {
            'flow_input': {
                'action': 'error',
                'error': str(e)
            }
        }
