import json
import boto3
import os
import logging
import yaml
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

def normalize_limits_to_list_format(limits):
    """Convert limits from object format to list format for YAML storage"""
    if not limits:
        return []
    
    normalized = []
    for limit in limits:
        if isinstance(limit, dict):
            # Convert from object format: {days: 30, count: 5, action: "warn"}
            # to list format: [30, 5] (action is optional and typically not stored in the original format)
            days = limit.get('days')
            count = limit.get('count')
            if days is not None and count is not None:
                normalized.append([int(days), int(count)])
        elif isinstance(limit, list) and len(limit) >= 2:
            # Already in list format: [30, 5]
            normalized.append([int(limit[0]), int(limit[1])])
    
    return normalized

def normalize_limits_to_object_format(limits):
    """Convert limits from list format to object format for frontend"""
    if not limits:
        return []
    
    normalized = []
    for limit in limits:
        if isinstance(limit, list) and len(limit) >= 2:
            # Convert from list format: [30, 5]
            # to object format: {days: 30, count: 5, action: "warn"}
            normalized.append({
                'days': int(limit[0]),
                'count': int(limit[1]),
                'action': limit[2] if len(limit) > 2 else 'warn'
            })
        elif isinstance(limit, dict):
            # Already in object format
            normalized.append({
                'days': int(limit.get('days', 0)),
                'count': int(limit.get('count', 0)),
                'action': limit.get('action', 'warn')
            })
    
    return normalized

def get_config_from_s3():
    """Read configuration from S3"""
    try:
        s3 = boto3.client('s3')
        bucket_name = os.environ.get('S3_KNOWLEDGE_BUCKET')
        config_key = 'config/business.yml'
        
        response = s3.get_object(Bucket=bucket_name, Key=config_key)
        config_content = response['Body'].read().decode('utf-8')
        
        # Parse YAML content
        config = yaml.safe_load(config_content)
        return config
        
    except ClientError as e:
        logger.error(f"Error reading config from S3: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error parsing config: {str(e)}")
        return None

def save_config_to_s3(config):
    """Save configuration to S3"""
    try:
        s3 = boto3.client('s3')
        bucket_name = os.environ.get('S3_KNOWLEDGE_BUCKET')
        config_key = 'config/business.yml'
        
        # Convert config to YAML
        yaml_content = yaml.safe_dump(config, default_flow_style=False, sort_keys=False)
        
        # Upload to S3
        s3.put_object(
            Bucket=bucket_name,
            Key=config_key,
            Body=yaml_content.encode('utf-8'),
            ContentType='application/x-yaml'
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error saving config to S3: {str(e)}")
        return False

def lambda_handler(event, context):
    """Handle configuration management requests"""
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})
    
    try:
        http_method = event.get('httpMethod', 'GET')
        
        if http_method == 'GET':
            # Get current configuration
            config = get_config_from_s3()
            if config is None:
                return create_response(500, {'error': 'Failed to load configuration'})
            
            # Extract relevant settings for frontend
            spam_detection = config.get('spam_detection', {})
            
            # Convert limits to object format for frontend display
            spam_activities_limits = normalize_limits_to_object_format(
                spam_detection.get('spam_activities_limits', [])
            )
            message_limits = normalize_limits_to_object_format(
                spam_detection.get('message_limits', [])
            )
            
            result = {
                'spam_detection': {
                    'spam_activities_limits': spam_activities_limits,
                    'message_limits': message_limits,
                    'warning_threshold_offset': spam_detection.get('warning_threshold_offset', 5),
                    'ai_confidence_threshold': spam_detection.get('ai_confidence_threshold', 0.7),
                    'fallback_confidence': spam_detection.get('fallback_confidence', 0.7)
                },
                'spam_messages': {
                    'warning_message_es': config.get('spam_messages', {}).get('warning_message_es', ''),
                    'blocked_message_es': config.get('spam_messages', {}).get('blocked_message_es', ''),
                    'support_email': config.get('spam_messages', {}).get('support_email', '')
                },
                'ai_models': {
                    'bedrock_model_id': config.get('ai_models', {}).get('bedrock_model_id', ''),
                    'bedrock_version': config.get('ai_models', {}).get('bedrock_version', ''),
                    'max_tokens_spam_detection': config.get('ai_models', {}).get('max_tokens_spam_detection', 200),
                    'max_tokens_conversation': config.get('ai_models', {}).get('max_tokens_conversation', 300)
                },
                'reply_length': {
                    'default': {
                        'max_response_characters': config.get('reply_length', {}).get('default', {}).get('max_response_characters', 199),
                        'character_limit_fallback': config.get('reply_length', {}).get('default', {}).get('character_limit_fallback', 280),
                        'character_limit_truncate': config.get('reply_length', {}).get('default', {}).get('character_limit_truncate', 277),
                        'conversation_history_limit': config.get('reply_length', {}).get('default', {}).get('conversation_history_limit', 10)
                    },
                    'whatsapp': {
                        'max_response_characters': config.get('reply_length', {}).get('whatsapp', {}).get('max_response_characters', 199),
                        'character_limit_fallback': config.get('reply_length', {}).get('whatsapp', {}).get('character_limit_fallback', 280),
                        'character_limit_truncate': config.get('reply_length', {}).get('whatsapp', {}).get('character_limit_truncate', 277),
                        'conversation_history_limit': config.get('reply_length', {}).get('whatsapp', {}).get('conversation_history_limit', 10)
                    }
                }
            }
            
            return create_response(200, result)
            
        elif http_method == 'PUT':
            # Update configuration
            body = event.get('body', '{}')
            if event.get('isBase64Encoded'):
                import base64
                body = base64.b64decode(body).decode('utf-8')
            
            try:
                updates = json.loads(body)
            except json.JSONDecodeError:
                return create_response(400, {'error': 'Invalid JSON in request body'})
            
            # Get current config
            config = get_config_from_s3()
            if config is None:
                return create_response(500, {'error': 'Failed to load current configuration'})
            
            # Update the configuration with new values
            if 'spam_detection' in updates:
                if 'spam_detection' not in config:
                    config['spam_detection'] = {}
                
                spam_detection_updates = updates['spam_detection']
                
                # Handle spam_activities_limits conversion
                if 'spam_activities_limits' in spam_detection_updates:
                    config['spam_detection']['spam_activities_limits'] = normalize_limits_to_list_format(
                        spam_detection_updates['spam_activities_limits']
                    )
                
                # Handle message_limits conversion
                if 'message_limits' in spam_detection_updates:
                    config['spam_detection']['message_limits'] = normalize_limits_to_list_format(
                        spam_detection_updates['message_limits']
                    )
                
                # Handle other spam detection settings
                for key in ['warning_threshold_offset', 'ai_confidence_threshold', 'fallback_confidence']:
                    if key in spam_detection_updates:
                        config['spam_detection'][key] = spam_detection_updates[key]
            
            if 'spam_messages' in updates:
                if 'spam_messages' not in config:
                    config['spam_messages'] = {}
                config['spam_messages'].update(updates['spam_messages'])
            
            if 'ai_models' in updates:
                if 'ai_models' not in config:
                    config['ai_models'] = {}
                config['ai_models'].update(updates['ai_models'])
            
            if 'reply_length' in updates:
                if 'reply_length' not in config:
                    config['reply_length'] = {}
                
                if 'default' in updates['reply_length']:
                    if 'default' not in config['reply_length']:
                        config['reply_length']['default'] = {}
                    config['reply_length']['default'].update(updates['reply_length']['default'])
                
                if 'whatsapp' in updates['reply_length']:
                    if 'whatsapp' not in config['reply_length']:
                        config['reply_length']['whatsapp'] = {}
                    config['reply_length']['whatsapp'].update(updates['reply_length']['whatsapp'])
            
            # Save updated configuration
            if save_config_to_s3(config):
                return create_response(200, {'message': 'Configuration updated successfully'})
            else:
                return create_response(500, {'error': 'Failed to save configuration'})
        
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        logger.error(f"Error in config handler: {str(e)}")
        return create_response(500, {'error': str(e)})
