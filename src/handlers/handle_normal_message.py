import json
import logging
import boto3
import os
from datetime import datetime
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function to handle normal (non-spam) messages.
    Uses Bedrock AI agent with knowledge base and conversation history.
    """
    
    try:
        # Parse input from previous lambda
        if isinstance(event.get('body'), str):
            input_data = json.loads(event.get('body'))
        else:
            input_data = event.get('body', event)
            
        message_data = input_data.get('message_data', {})
        lead_id = input_data.get('lead_id')
        contact_method_id = input_data.get('contact_method_id')
        
        clean_phone_number = message_data.get('clean_phone_number', '')
        message_body = message_data.get('message_body', '')
        message_sid = message_data.get('message_sid', '')
        profile_name = message_data.get('profile_name', '')
        original_to = message_data.get('original_to', '')
        
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
            region_name='us-east-1'
        )
        
        # Load system prompt from S3 or use default
        system_prompt = load_system_prompt_from_s3()
        
        if not system_prompt:
            system_prompt = get_default_system_prompt()
        
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
        if len(ai_response) > 280:
            ai_response = ai_response[:277] + "..."
        
        logger.info(f"AI generated response: {ai_response}")
        
        timestamp = datetime.now().isoformat()
        
        # Create activity record
        activity_id = str(uuid.uuid4())
        activities_table.put_item(
            Item={
                'id': activity_id,
                'lead_id': lead_id,
                'contact_method_id': contact_method_id,
                'activity_type': 'whatsapp',
                'status': 'completed',
                'direction': 'inbound',
                'completed_at': timestamp,
                'created_at': timestamp,
                'metadata': {
                    'twilioSid': message_sid,
                    'profileName': profile_name,
                    'messageType': 'text'
                }
            }
        )
        
        # Store activity content
        activity_content_table.put_item(
            Item={
                'id': str(uuid.uuid4()),
                'activity_id': activity_id,
                'content_type': 'whatsapp',
                'content': {
                    'leadMessage': message_body,
                    'assistantMessage': ai_response
                },
                'created_at': timestamp
            }
        )
        
        # Send WhatsApp response via Twilio
        send_twilio_message(clean_phone_number, ai_response, original_to)
        
        response_data = {
            'action': 'message_processed',
            'activity_id': activity_id,
            'response_sent': True,
            'ai_response': ai_response,
            'conversation_history_count': len(conversation_history)
        }
        
        logger.info(f"Normal message processed successfully for lead {lead_id}")
        
        return {
            'body': response_data
        }
        
    except Exception as e:
        logger.error(f"Error processing normal message: {str(e)}")
        return {
            'body': {
                'action': 'error',
                'error': str(e)
            }
        }

def get_conversation_history(lead_id):
    """Get conversation history for the lead"""
    try:
        dynamodb = boto3.resource('dynamodb')
        activities_table = dynamodb.Table(os.environ['ACTIVITIES_TABLE'])
        activity_content_table = dynamodb.Table(os.environ['ACTIVITY_CONTENT_TABLE'])
        
        # Get recent activities for this lead
        response = activities_table.query(
            IndexName='lead-id-created-at-index',
            KeyConditionExpression='lead_id = :lead_id',
            ExpressionAttributeValues={':lead_id': lead_id},
            ScanIndexForward=False,  # Most recent first
            Limit=10
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

def get_default_system_prompt():
    """Return default system prompt"""
    return """
    ## Overview
    
    Eres un asistente virtual especializado en ventas para Cogelo.shop. Tu objetivo es conseguir cerrar reuniones comerciales con los usuarios que interactúan contigo. Para lograrlo, primero debes ayudar a contestar sus preguntas de forma clara y útil. A continuación se incluye toda la información relevante sobre la empresa para que puedas utilizarla en tus respuestas. Recuerda siempre intentar cerrar una cita mientras resuelves dudas.
    
    ## Company description
    
    Cogelo.shop ofrece máquinas expendedoras inteligentes con tecnología de Inteligencia Artificial que maximizan la facturación en espacios reducidos (desde medio metro cuadrado). Están diseñadas para ofrecer una experiencia de compra rápida, eficiente y sin fricciones:
    
    Experiencia de usuario:
    - El usuario pasa la tarjeta para abrir.
    - Selecciona varios productos libremente.
    - Al cerrar la puerta, se realiza el pago automáticamente.
    
    Tecnología:
    - Sensores de visión con IA: Reconocimiento de productos preciso, seguimiento del inventario sin incidencias.
    - Sensores de peso: Aseguran una dispensación consistente y fiable.
    - Cámara con IA: Automatización total de la experiencia de compra.
    - Diseño configurable: Estantes ajustables para maximizar capacidad y reducir costes operativos.
    
    Ventajas operativas:
    - Reposición rápida mediante escaneo de código.
    - No requiere formación especializada.
    - Aprovechamiento del 95% del espacio.
    - Reducción de tiempo y coste de reposición en hasta un 40%.
    
    Aplicaciones por sector:
    - Oficinas: Mejora del bienestar y productividad.
    - Hospitales: Alimentación 24/7 para todo el personal.
    - Centros deportivos: Nutrición inteligente post-entreno.
    - Aeropuertos y estaciones: Conveniencia 24/7 para viajeros.
    - Centros comerciales: Vending estratégico de apoyo.
    - Centros educativos: Opción saludable en universidades e institutos.
    
    Modelos de adquisición:
    - Renting: 240€/mes + IVA (incluye software, instalación y formación).
    - Compra: 4.900€ + IVA + 27€/mes por software.
    
    Servicios adicionales:
    - Seguro multirriesgo: Incluye cobertura por daños, robos, averías y pérdida de beneficios (30€/mes).
    - Reposición profesional: Desde 19€/semana.
    - Plan de reposición personalizado disponible.
    
    Rentabilidad:
    - Rentable desde 6,5€/día con apenas 10 ventas.
    - Rentabilidad mensual estimada: 1.010€ (hasta 1.060€ con desgravación fiscal).
    - Rentabilidad anual estimada: 12.120€.
    
    ## IMPORTANT
    - Focus the answer to be clear and concise in no more than 280 characters
    - Create a single output message for the last message (consider the previous ones too but with a single output)
    """

def send_twilio_message(to_number, message_body, from_number):
    """Send WhatsApp message via Twilio"""
    try:
        from twilio.rest import Client
        
        account_sid = os.environ['TWILIO_ACCOUNT_SID']
        auth_token = os.environ['TWILIO_AUTH_TOKEN']
        
        client = Client(account_sid, auth_token)
        
        # Extract clean from number
        clean_from = from_number.split(':')[1] if ':' in from_number else from_number
        
        message = client.messages.create(
            from_=f'whatsapp:{clean_from}',
            body=message_body,
            to=f'whatsapp:{to_number}'
        )
        
        logger.info(f"Sent Twilio message: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending Twilio message: {str(e)}")
        return False
