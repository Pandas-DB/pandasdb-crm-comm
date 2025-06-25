import json
import boto3
import os

def load_business_config():
    """Load business configuration from S3"""
    s3_client = boto3.client('s3')
    bucket_name = os.environ['S3_KNOWLEDGE_BUCKET']
    response = s3_client.get_object(Bucket=bucket_name, Key='config/business.json')
    return json.loads(response['Body'].read().decode('utf-8'))
