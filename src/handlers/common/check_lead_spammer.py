import yaml
import logging
import boto3
import os
import sys
from datetime import datetime, timedelta

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aux import load_business_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def check_message_limits_spam(activities_table, lead_id, config):
    """
    Check if user exceeds message limits for any configured time period.
    Returns True if spam detected, False otherwise.
    """
    message_limits = config['spam_detection']['message_limits']
    warning_threshold_offset = config['spam_detection']['warning_threshold_offset']
    
    for days, max_messages in message_limits:
        # Calculate the start date for this period
        start_date = (datetime.now() - timedelta(days=days)).date().isoformat()
        
        # Query activities for this period
        activities_response = activities_table.query(
            IndexName='lead-id-created-at-index',
            KeyConditionExpression='lead_id = :lead_id AND created_at >= :start_date',
            ExpressionAttributeValues={
                ':lead_id': lead_id,
                ':start_date': start_date
            }
        )
        
        message_count = len(activities_response['Items'])
        
        # Check if limit exceeded
        if message_count >= max_messages:
            logger.info(f"Lead {lead_id} marked as spammer: {message_count} messages in last {days} days (limit: {max_messages})")
            return True
        elif message_count >= max_messages - warning_threshold_offset:
            logger.warning(f"Lead {lead_id} approaching spam limit: {message_count} messages in last {days} days (limit: {max_messages})")
        
        logger.info(f"Lead {lead_id}: {message_count} messages in last {days} days (limit: {max_messages})")
    
    return False

def check_spam_activities_limits(spam_activities_table, lead_id, config):
    """
    Check if user exceeds spam activities limits for any configured time period.
    Returns True if spam detected, False otherwise.
    """
    spam_activities_limits = config['spam_detection']['spam_activities_limits']
    
    for days, max_spam_activities in spam_activities_limits:
        # Calculate the start date for this period
        lookback_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
        spam_response = spam_activities_table.query(
            IndexName='lead-id-spam-date-index',
            KeyConditionExpression='lead_id = :lead_id AND spam_date >= :date',
            ExpressionAttributeValues={
                ':lead_id': lead_id,
                ':date': lookback_days_ago
            }
        )
        
        spam_count = len(spam_response['Items'])
        
        # Check if limit exceeded
        if spam_count >= max_spam_activities:
            logger.info(f"Lead {lead_id} marked as spammer: {spam_count} spam activities in last {days} days (limit: {max_spam_activities})")
            return True
        
        logger.info(f"Lead {lead_id}: {spam_count} spam activities in last {days} days (limit: {max_spam_activities})")
    
    return False

def lambda_handler(event, context):
    """
    Lambda function to check spammer status for an existing lead.
    Lead must already exist (validated/created in previous lambda).
    """
    
    try:
        # Get lead info from previous lambda
        lead_id = event['lead_id']
        contact_method_id = event['contact_method_id']
        flow_input = event['flow_input']
        
        logger.info(f"Checking spam status for lead_id: {lead_id}")
        
        # DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        spam_activities_table = dynamodb.Table(os.environ['SPAM_ACTIVITIES_TABLE'])
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        
        config = load_business_config()
        
        # Check spammer status using spam activities
        is_spammer = check_spam_activities_limits(spam_activities_table, lead_id, config)
        
        # Check message limits for all configured periods
        if not is_spammer:
            is_spammer = check_message_limits_spam(activities_table, lead_id, config)
        
        logger.info(f"Spammer status: {is_spammer}")
        
        response_data = {
            'lead_id': lead_id,
            'contact_method_id': contact_method_id,
            'is_spammer': is_spammer,
            'flow_input': flow_input
        }
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error checking spam status: {str(e)}")
        return {
            'action': 'error',
            'error': str(e)
        }
