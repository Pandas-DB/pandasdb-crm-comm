import json
import logging
import os
import base64
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import sys
sys.path.append('/opt/python')
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from handlers_aux import (
    NormalizedInputMessage, 
    start_step_function_execution, 
    get_platform_success_response,
    get_platform_error_response,
    handle_webhook_error
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Gmail polling handler that checks for new emails every X minutes.
    Triggered by CloudWatch Events (EventBridge).
    """
    
    try:
        logger.info("Starting Gmail polling")
        
        # Get polling configuration
        poll_interval_minutes = int(os.environ.get('GMAIL_POLL_INTERVAL_MINUTES', 5))
        
        # Poll for new emails
        new_emails = poll_gmail_for_new_emails(poll_interval_minutes)
        
        if not new_emails:
            logger.info("No new emails found")
            return {"statusCode": 200, "body": "No new emails"}
        
        logger.info(f"Found {len(new_emails)} new emails")
        
        # Process each new email
        processed_count = 0
        for email_data in new_emails:
            try:
                normalized_message = normalize_gmail_message(email_data)
                if normalized_message:
                    start_step_function_execution(normalized_message, context)
                    processed_count += 1
                    logger.info(f"Processed email from {normalized_message.From}")
            except Exception as e:
                logger.error(f"Error processing email {email_data.get('id', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Successfully processed {processed_count} emails")
        return {
            "statusCode": 200, 
            "body": json.dumps({
                "found": len(new_emails),
                "processed": processed_count
            })
        }
        
    except Exception as e:
        logger.error(f"Gmail polling error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def poll_gmail_for_new_emails(poll_interval_minutes):
    """Poll Gmail for new emails within the specified time interval"""
    
    try:
        # Initialize Gmail API service
        service = get_gmail_service()
        
        # Calculate time range for polling
        now = datetime.utcnow()
        since_time = now - timedelta(minutes=poll_interval_minutes)
        
        # Gmail uses epoch time in seconds
        since_timestamp = int(since_time.timestamp())
        
        # Search for recent emails in INBOX
        query = f'in:inbox after:{since_timestamp}'
        
        # Use the configured Gmail user or 'me'
        user_id = os.environ.get('GMAIL_USER_EMAIL', 'me')
        
        # Search for messages
        result = service.users().messages().list(
            userId=user_id,
            q=query,
            maxResults=50  # Limit to prevent overwhelming the system
        ).execute()
        
        messages = result.get('messages', [])
        
        if not messages:
            return []
        
        # Get full message details for each message
        new_emails = []
        for message in messages:
            try:
                full_message = service.users().messages().get(
                    userId=user_id,
                    id=message['id'],
                    format='full'
                ).execute()
                
                # Check if this email was already processed
                if not is_email_already_processed(full_message):
                    new_emails.append(full_message)
                
            except Exception as e:
                logger.error(f"Error fetching message {message['id']}: {str(e)}")
                continue
        
        return new_emails
        
    except Exception as e:
        logger.error(f"Error polling Gmail: {str(e)}")
        raise

def is_email_already_processed(email_data):
    """
    Check if this email was already processed.
    This is a simple implementation - you might want to store processed message IDs in DynamoDB.
    """
    
    # Get email timestamp
    internal_date = int(email_data.get('internalDate', 0))
    email_time = datetime.fromtimestamp(internal_date / 1000)  # Convert from milliseconds
    
    # Only process emails from the last polling interval to avoid reprocessing
    poll_interval_minutes = int(os.environ.get('GMAIL_POLL_INTERVAL_MINUTES', 5))
    cutoff_time = datetime.utcnow() - timedelta(minutes=poll_interval_minutes + 1)  # Add 1 minute buffer
    
    # If email is older than our polling window, consider it already processed
    return email_time < cutoff_time

def normalize_gmail_message(email_data) -> NormalizedInputMessage:
    """Convert Gmail message to normalized format"""
    
    try:
        # Extract headers
        headers = {}
        payload = email_data.get('payload', {})
        for header in payload.get('headers', []):
            headers[header['name']] = header['value']
        
        # Extract main fields
        from_email = headers.get('From', '')
        to_email = headers.get('To', '')
        subject = headers.get('Subject', '')
        message_id = email_data.get('id', '')
        
        # Extract email body
        body = extract_email_body(payload)
        
        # Create metadata
        metadata = {
            'messageId': message_id,
            'threadId': email_data.get('threadId'),
            'labelIds': email_data.get('labelIds', []),
            'snippet': email_data.get('snippet', ''),
            'internalDate': email_data.get('internalDate'),
            'headers': headers,
            'subject': subject
        }
        
        # Create normalized message
        return NormalizedInputMessage(
            From=from_email,
            To=to_email,
            Body=f"Subject: {subject}\n\n{body}",
            MessageSid=message_id,
            ProfileName=extract_sender_name(from_email),
            AccountSid=to_email,  # Use recipient email as account identifier
            platform='gmail',
            metadata=metadata
        )
        
    except Exception as e:
        logger.error(f"Error normalizing Gmail message: {str(e)}")
        raise ValueError(f"Failed to normalize Gmail message: {str(e)}")

def get_gmail_service():
    """Initialize Gmail API service with service account credentials"""
    
    try:
        # Load service account credentials from environment variable
        service_account_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not service_account_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set")
        
        service_account_info = json.loads(service_account_json)
        
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        
        # If using domain-wide delegation, specify the user email
        gmail_user = os.environ.get('GMAIL_USER_EMAIL')
        if gmail_user:
            credentials = credentials.with_subject(gmail_user)
        
        service = build('gmail', 'v1', credentials=credentials)
        return service
        
    except Exception as e:
        logger.error(f"Error initializing Gmail service: {str(e)}")
        raise

def extract_email_body(payload):
    """Extract email body from Gmail message payload"""
    
    body = ""
    
    def extract_text_from_part(part):
        """Recursively extract text from message parts"""
        text = ""
        
        mime_type = part.get('mimeType', '')
        
        if mime_type == 'text/plain':
            data = part.get('body', {}).get('data', '')
            if data:
                text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        elif mime_type == 'text/html':
            # For HTML, extract text and remove HTML tags
            data = part.get('body', {}).get('data', '')
            if data:
                html_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                # Simple HTML tag removal
                import re
                text = re.sub(r'<[^>]+>', '', html_text)
                text = re.sub(r'\s+', ' ', text).strip()  # Clean up whitespace
        elif 'parts' in part:
            # Multipart message
            for subpart in part['parts']:
                text += extract_text_from_part(subpart)
        
        return text
    
    if 'parts' in payload:
        # Multipart message
        for part in payload['parts']:
            body += extract_text_from_part(part)
    else:
        # Single part message
        body = extract_text_from_part(payload)
    
    return body.strip()

def extract_sender_name(from_email):
    """Extract sender name from From header"""
    
    if not from_email:
        return "Unknown Sender"
    
    if '<' in from_email and '>' in from_email:
        # Format: "Name <email@example.com>"
        name = from_email.split('<')[0].strip().strip('"')
        return name if name else from_email
    else:
        # Just email address - extract name part before @
        return from_email.split('@')[0]
