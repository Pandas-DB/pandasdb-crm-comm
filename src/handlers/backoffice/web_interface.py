import json
import base64
import boto3
import os
import logging
from datetime import datetime, timedelta
import uuid
import urllib.request
import urllib.error
import urllib.parse
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB client
dynamodb = boto3.resource('dynamodb')
sessions_table = None

# S3 client
s3_client = boto3.client('s3')

def get_sessions_table():
    """Get DynamoDB sessions table"""
    global sessions_table
    if sessions_table is None:
        table_name = os.environ.get('SESSIONS_TABLE')
        if table_name:
            sessions_table = dynamodb.Table(table_name)
    return sessions_table

def create_response(status_code, body, content_type='text/html', set_cookie=None, location=None):
    headers = {
        'Content-Type': content_type,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    if set_cookie:
        headers['Set-Cookie'] = set_cookie
    if location:
        headers['Location'] = location
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': body
    }

def verify_admin_key(api_key):
    """Verify if the provided API key is valid by testing against admin API"""
    try:
        admin_api_id = os.environ.get('ADMIN_API_ID', '9ea7dore8a')
        stage = os.environ.get('STAGE', 'dev')
        admin_endpoint = f"https://{admin_api_id}.execute-api.eu-west-1.amazonaws.com/{stage}"
        
        req = urllib.request.Request(
            f"{admin_endpoint}/analytics",
            headers={'x-api-key': api_key}
        )
        
        with urllib.request.urlopen(req) as response:
            return response.status == 200
            
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error verifying API key: {e.code}")
        return False
    except Exception as e:
        logger.error(f"Error verifying API key: {str(e)}")
        return False

def create_session(user_id, api_key):
    """Create a secure session in DynamoDB"""
    try:
        table = get_sessions_table()
        if not table:
            logger.error("Sessions table not configured")
            return None
            
        session_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=8)
        
        # Convert to Unix timestamp for DynamoDB TTL
        expires_timestamp = int(expires_at.timestamp())
        
        table.put_item(
            Item={
                'session_id': session_id,
                'user_id': user_id,
                'api_key': api_key,
                'created_at': datetime.utcnow().isoformat(),
                'expires_at': expires_timestamp
            }
        )
        
        return session_id
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        return None

def verify_session(session_id):
    """Verify if session is valid and not expired"""
    try:
        table = get_sessions_table()
        if not table:
            return False
            
        response = table.get_item(
            Key={'session_id': session_id}
        )
        
        if 'Item' not in response:
            return False
            
        session = response['Item']
        expires_at = int(session['expires_at'])
        current_time = int(datetime.utcnow().timestamp())
        
        if current_time > expires_at:
            # Session expired, delete it
            table.delete_item(Key={'session_id': session_id})
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error verifying session: {str(e)}")
        return False

def get_session_api_key(session_id):
    """Get API key from session"""
    try:
        table = get_sessions_table()
        if not table:
            return None
            
        response = table.get_item(
            Key={'session_id': session_id}
        )
        
        if 'Item' not in response:
            return None
            
        return response['Item'].get('api_key')
    except Exception as e:
        logger.error(f"Error getting session API key: {str(e)}")
        return None

def delete_session(session_id):
    """Delete a session from DynamoDB"""
    try:
        table = get_sessions_table()
        if table:
            table.delete_item(Key={'session_id': session_id})
    except Exception as e:
        logger.error(f"Error deleting session: {str(e)}")

def get_session_from_cookie(cookie_header):
    """Extract session ID from cookie"""
    if not cookie_header:
        return None
    
    cookies = {}
    for cookie in cookie_header.split(';'):
        if '=' in cookie:
            key, value = cookie.strip().split('=', 1)
            cookies[key] = value
    
    return cookies.get('session_id')

def make_admin_api_call(endpoint, admin_api_key, method='GET', body=None):
    """Make a secure API call to admin endpoints"""
    try:
        admin_api_id = os.environ.get('ADMIN_API_ID', '9ea7dore8a')
        stage = os.environ.get('STAGE', 'dev')
        admin_endpoint = f"https://{admin_api_id}.execute-api.eu-west-1.amazonaws.com/{stage}"
        
        headers = {'x-api-key': admin_api_key}
        if body:
            headers['Content-Type'] = 'application/json'
            body = body.encode('utf-8')
        
        req = urllib.request.Request(
            f"{admin_endpoint}{endpoint}",
            headers=headers,
            method=method,
            data=body
        )
        
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
            
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error making admin API call: {e.code}")
        return {'error': f'API call failed with status {e.code}'}
    except Exception as e:
        logger.error(f"Error making admin API call: {str(e)}")
        return {'error': str(e)}

def get_base_url(event):
    """Get the base URL from the event"""
    stage = event.get('requestContext', {}).get('stage', 'dev')
    return f"/{stage}/backoffice"

def get_system_prompt_from_s3():
    """Get system prompt content from S3"""
    try:
        bucket_name = os.environ.get('S3_KNOWLEDGE_BUCKET')
        if not bucket_name:
            return None, "S3 bucket not configured"
        
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key='knowledge/system_prompt.txt'
        )
        content = response['Body'].read().decode('utf-8')
        return content, None
    except Exception as e:
        logger.error(f"Error getting system prompt from S3: {str(e)}")
        return None, str(e)

def save_system_prompt_to_s3(content):
    """Save system prompt content to S3"""
    try:
        bucket_name = os.environ.get('S3_KNOWLEDGE_BUCKET')
        if not bucket_name:
            return False, "S3 bucket not configured"
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key='knowledge/system_prompt.txt',
            Body=content.encode('utf-8'),
            ContentType='text/plain'
        )
        return True, None
    except Exception as e:
        logger.error(f"Error saving system prompt to S3: {str(e)}")
        return False, str(e)

def render_base_page(title, content, current_page='dashboard', base_url='/dev/backoffice'):
    """Render base page template with navigation"""
    nav_items = [
       ('analytics', 'Analytics', f'{base_url}'),
       ('leads', 'Leads', f'{base_url}?page=leads'),
       ('spam', 'Spam Activities', f'{base_url}?page=spam'),
       ('spam_users', 'Spam Users', f'{base_url}?page=spam_users'),
       ('spam_config', 'Spam Config', f'{base_url}?page=spam_config'),
       ('integration', 'Integration', f'{base_url}?page=integration'),
       ('system_prompt', 'System Prompt', f'{base_url}?page=system_prompt')
    ]
    
    nav_html = ''.join([
        f'<a href="{url}" style="background: {"#1d4ed8" if page == current_page else "#2563eb"};">{label}</a>'
        for page, label, url in nav_items
    ])
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title} - CRM Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
            .nav {{ margin: 20px 0; }}
            .nav a {{ display: inline-block; padding: 10px 20px; background: #2563eb; color: white; text-decoration: none; border-radius: 6px; margin-right: 10px; }}
            .nav a:hover {{ background: #1d4ed8; }}
            .content {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }}
            .stat-card {{ background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center; }}
            .stat-number {{ font-size: 2em; font-weight: bold; color: #2563eb; }}
            .error {{ background: #fef2f2; color: #dc2626; padding: 10px; border-radius: 6px; margin: 10px 0; }}
            .success {{ background: #f0fdf4; color: #16a34a; padding: 10px; border-radius: 6px; margin: 10px 0; }}
            .logout {{ background: #dc2626; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; }}
            .logout:hover {{ background: #b91c1c; }}
            .table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            .table th, .table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
            .table th {{ background: #f9fafb; font-weight: 600; }}
            .btn {{ background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; }}
            .btn:hover {{ background: #1d4ed8; }}
            .btn-danger {{ background: #dc2626; }}
            .btn-danger:hover {{ background: #b91c1c; }}
            .btn-small {{ padding: 5px 10px; font-size: 12px; }}
            .loading {{ text-align: center; padding: 20px; color: #6b7280; }}
            .form-group {{ margin-bottom: 15px; }}
            .form-group label {{ display: block; margin-bottom: 5px; font-weight: 500; }}
            .form-group input, .form-group textarea, .form-group select {{ width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; }}
            .config-section {{ background: #f8fafc; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #2563eb; }}
            .config-section h3 {{ margin-top: 0; color: #1f2937; }}
            .form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
            .limits-table {{ width: 100%; border-collapse: collapse; }}
            .limits-table th, .limits-table td {{ padding: 8px 12px; border: 1px solid #d1d5db; }}
            .limits-table th {{ background: #f9fafb; }}
            .prompt-editor {{ width: 100%; min-height: 400px; padding: 15px; border: 1px solid #d1d5db; border-radius: 6px; font-family: 'Courier New', monospace; font-size: 14px; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{title}</h1>
                <a href="{base_url}?action=logout" class="logout">Logout</a>
            </div>
            
            <div class="nav">
                {nav_html}
            </div>
            
            <div class="content">
                {content}
            </div>
        </div>
    </body>
    </html>
    """

def render_login_page(error=None):
    """Render the login page"""
    error_html = f'<div class="error">{error}</div>' if error else ''
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>CRM Backoffice - Login</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 50px 20px; }}
            .login-container {{ max-width: 400px; margin: 100px auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ text-align: center; color: #1f2937; margin-bottom: 30px; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 5px; font-weight: 500; }}
            input {{ width: 100%; padding: 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 16px; box-sizing: border-box; }}
            button {{ width: 100%; background: #2563eb; color: white; border: none; padding: 12px; border-radius: 6px; font-size: 16px; cursor: pointer; }}
            button:hover {{ background: #1d4ed8; }}
            .error {{ background: #fef2f2; color: #dc2626; padding: 10px; border-radius: 6px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <h1>CRM Backoffice</h1>
            {error_html}
            <form method="POST">
                <div class="form-group">
                    <label for="api_key">Admin API Key:</label>
                    <input type="password" id="api_key" name="api_key" required>
                </div>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    """

def render_analytics_page(admin_api_key, base_url, start_date=None, end_date=None):
    """Render analytics page with real data and date filtering"""
    
    # Set default date range to last 90 days if not provided
    if not start_date or not end_date:
        end_date = datetime.utcnow().strftime('%Y-%m-%d')
        start_date = (datetime.utcnow() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    # Call analytics API with date range
    endpoint = f'/analytics?start_date={start_date}&end_date={end_date}'
    data = make_admin_api_call(endpoint, admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading analytics: {data["error"]}</div>'
    else:
        # Generate chart data from daily analytics
        daily_data = data.get('daily_analytics', [])
        chart_labels = []
        messages_data = []
        spam_data = []
        
        for day in daily_data:
            chart_labels.append(f"'{day.get('date', '')}'")
            messages_data.append(day.get('messages', 0))
            spam_data.append(day.get('spam', 0))
        
        chart_labels_str = '[' + ','.join(chart_labels) + ']'
        messages_data_str = '[' + ','.join(map(str, messages_data)) + ']'
        spam_data_str = '[' + ','.join(map(str, spam_data)) + ']'
        
        content = f"""
        <h2>System Analytics</h2>
        
        <!-- Date Range Filter -->
        <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <form method="GET" action="{base_url}" style="display: flex; align-items: center; gap: 15px; flex-wrap: wrap;">
                <input type="hidden" name="page" value="analytics">
                <div>
                    <label for="start_date" style="margin-right: 5px; font-weight: 500;">From:</label>
                    <input type="date" id="start_date" name="start_date" value="{start_date}" 
                           min="{(datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')}" 
                           max="{datetime.utcnow().strftime('%Y-%m-%d')}"
                           style="padding: 8px; border: 1px solid #d1d5db; border-radius: 6px;">
                </div>
                <div>
                    <label for="end_date" style="margin-right: 5px; font-weight: 500;">To:</label>
                    <input type="date" id="end_date" name="end_date" value="{end_date}"
                           min="{(datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')}" 
                           max="{datetime.utcnow().strftime('%Y-%m-%d')}"
                           style="padding: 8px; border: 1px solid #d1d5db; border-radius: 6px;">
                </div>
                <button type="submit" class="btn">Apply Filter</button>
                <a href="{base_url}?page=analytics" class="btn" style="background: #6b7280; text-decoration: none;">Reset (90 days)</a>
            </form>
        </div>
        
        <!-- Summary Cards -->
        <div class="stats">
            <div class="stat-card">
                <h3>Total Leads</h3>
                <div class="stat-number">{data.get('total_leads', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Messages (Period)</h3>
                <div class="stat-number">{data.get('total_messages', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Spam (Period)</h3>
                <div class="stat-number">{data.get('total_spam', 0)}</div>
            </div>
            <div class="stat-card">
                <h3>Spam Percentage</h3>
                <div class="stat-number">{data.get('spam_percentage', 0)}%</div>
            </div>
        </div>
        
        <!-- Daily Activity Chart -->
        <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-top: 20px;">
            <h3>Daily Activity Chart</h3>
            <canvas id="activityChart" width="400" height="200"></canvas>
        </div>
        
        <p style="margin-top: 20px;"><strong>Last Updated:</strong> {data.get('last_updated', 'Unknown')}</p>
        <p><strong>Date Range:</strong> {start_date} to {end_date}</p>
        
        <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
        <script>
        const ctx = document.getElementById('activityChart').getContext('2d');
        const activityChart = new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: {chart_labels_str},
                datasets: [{{
                    label: 'Messages',
                    data: {messages_data_str},
                    backgroundColor: 'rgba(37, 99, 235, 0.8)',
                    borderColor: 'rgba(37, 99, 235, 1)',
                    borderWidth: 1
                }}, {{
                    label: 'Spam',
                    data: {spam_data_str},
                    backgroundColor: 'rgba(220, 38, 38, 0.8)',
                    borderColor: 'rgba(220, 38, 38, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Daily Messages vs Spam Activity'
                    }},
                    legend: {{
                        display: true,
                        position: 'top'
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }},
                    x: {{
                        ticks: {{
                            maxRotation: 45,
                            minRotation: 45
                        }}
                    }}
                }},
                interaction: {{
                    mode: 'index',
                    intersect: false
                }}
            }}
        }});
        </script>
        """
    
    return render_base_page("Analytics", content, "analytics", base_url)

def render_leads_page(admin_api_key, base_url, search_query=None):
    """Render leads management page with search functionality"""
    
    # Build API endpoint with search parameter
    endpoint = '/leads'
    if search_query:
        endpoint += f'?search={urllib.parse.quote(search_query)}'
    
    data = make_admin_api_call(endpoint, admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading leads: {data["error"]}</div>'
    else:
        leads = data.get('leads', [])
        
        # Search bar
        search_value = search_query if search_query else ''
        search_bar_html = f"""
        <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <form method="GET" action="{base_url}" style="display: flex; align-items: center; gap: 15px;">
                <input type="hidden" name="page" value="leads">
                <div style="flex: 1;">
                    <label for="search" style="margin-right: 10px; font-weight: 500;">Search:</label>
                    <input type="text" id="search" name="search" value="{search_value}" 
                           placeholder="Search by name or contact method..."
                           style="width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box;">
                </div>
                <button type="submit" class="btn">Search</button>
                <a href="{base_url}?page=leads" class="btn" style="background: #6b7280; text-decoration: none;">Clear</a>
            </form>
        </div>
        """
        
        if leads:
            table_rows = []
            for lead in leads:
                contact_methods = '<br>'.join([f"{cm.get('type', '')}: {cm.get('value', '')}" for cm in lead.get('contact_methods', [])])
                created_date = datetime.fromisoformat(lead.get('created_at', '').replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                table_rows.append(f"""
                <tr>
                    <td>{lead.get('name', 'Unknown')}</td>
                    <td>{contact_methods}</td>
                    <td>{created_date}</td>
                    <td>
                        <a href="{base_url}?page=lead_detail&id={lead.get('id', '')}" class="btn btn-small">View Details</a>
                    </td>
                </tr>
                """)
            
            table_html = f"""
            <table class="table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Contact Methods</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
            """
            
            # Show search results count
            results_info = f"<p style='margin-bottom: 15px; color: #6b7280;'>Found {len(leads)} lead(s)" + (f" matching \"{search_query}\"" if search_query else "") + "</p>"
        else:
            table_html = f"<p>{'No leads found matching your search.' if search_query else 'No leads found.'}</p>"
            results_info = ""
        
        content = f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2>Leads Management</h2>
            <a href="{base_url}?page=create_lead" class="btn">Create Lead</a>
        </div>
        
        {search_bar_html}
        {results_info}
        {table_html}
        """
    
    return render_base_page("Leads", content, "leads", base_url)

def render_spam_activities_page(admin_api_key, base_url, search_query=None, start_date=None, end_date=None):
    """Render spam activities page with search and date filtering"""
    
    # Set default date range to last 30 days if not provided
    if not start_date or not end_date:
        end_date = datetime.utcnow().strftime('%Y-%m-%d')
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Build API endpoint with search and date parameters
    endpoint = '/spam'
    params = []
    if search_query:
        params.append(f'search={urllib.parse.quote(search_query)}')
    if start_date:
        params.append(f'start_date={start_date}')
    if end_date:
        params.append(f'end_date={end_date}')
    
    if params:
        endpoint += '?' + '&'.join(params)
    
    data = make_admin_api_call(endpoint, admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading spam activities: {data["error"]}</div>'
    else:
        spam_activities = data.get('spam_activities', [])
        
        # Search and filter bar
        search_value = search_query if search_query else ''
        filter_bar_html = f"""
        <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <form method="GET" action="{base_url}" style="display: flex; align-items: center; gap: 15px; flex-wrap: wrap;">
                <input type="hidden" name="page" value="spam">
                
                <!-- Search Input -->
                <div style="flex: 1; min-width: 200px;">
                    <label for="search" style="margin-right: 10px; font-weight: 500;">Search:</label>
                    <input type="text" id="search" name="search" value="{search_value}" 
                           placeholder="Search by lead, phone, message..."
                           style="width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box;">
                </div>
                
                <!-- Date Range -->
                <div>
                    <label for="start_date" style="margin-right: 5px; font-weight: 500;">From:</label>
                    <input type="date" id="start_date" name="start_date" value="{start_date}" 
                           min="{(datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')}" 
                           max="{datetime.utcnow().strftime('%Y-%m-%d')}"
                           style="padding: 8px; border: 1px solid #d1d5db; border-radius: 6px;">
                </div>
                <div>
                    <label for="end_date" style="margin-right: 5px; font-weight: 500;">To:</label>
                    <input type="date" id="end_date" name="end_date" value="{end_date}"
                           min="{(datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')}" 
                           max="{datetime.utcnow().strftime('%Y-%m-%d')}"
                           style="padding: 8px; border: 1px solid #d1d5db; border-radius: 6px;">
                </div>
                
                <!-- Action Buttons -->
                <button type="submit" class="btn">Apply Filter</button>
                <a href="{base_url}?page=spam" class="btn" style="background: #6b7280; text-decoration: none;">Reset (30 days)</a>
            </form>
        </div>
        """
        
        if spam_activities:
            table_rows = []
            for spam in spam_activities:
                spam_date = datetime.fromisoformat(spam.get('spam_date', '').replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                message_preview = (spam.get('message', '')[:50] + '...') if len(spam.get('message', '')) > 50 else spam.get('message', '')
                full_message = spam.get('full_message', spam.get('message', ''))
                table_rows.append(f"""
                <tr>
                    <td>{spam_date}</td>
                    <td>{spam.get('lead_name', 'Unknown')}</td>
                    <td>{spam.get('phone', 'N/A')}</td>
                    <td title="{full_message}">{message_preview}</td>
                    <td>{spam.get('spam_reason', 'N/A')}</td>
                    <td>
                        <button onclick="deleteSpamActivity('{spam.get('lead_id', '')}', '{spam.get('id', '')}')" 
                                class="btn btn-danger btn-small">Delete</button>
                    </td>
                </tr>
                """)
            
            table_html = f"""
            <table class="table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Lead</th>
                        <th>Phone</th>
                        <th>Message</th>
                        <th>Reason</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
            """
            
            # Show results count and filter info
            results_info = f"<p style='margin-bottom: 15px; color: #6b7280;'>Found {len(spam_activities)} spam activit{'y' if len(spam_activities) == 1 else 'ies'}"
            if search_query:
                results_info += f" matching \"{search_query}\""
            results_info += f" from {start_date} to {end_date}</p>"
            
            content = f"""
            <h2>Spam Activities</h2>
            {filter_bar_html}
            {results_info}
            {table_html}
            
            <script>
            function deleteSpamActivity(leadId, activityId) {{
                if (confirm('Are you sure you want to delete this spam activity? This action cannot be undone.')) {{
                    fetch('{base_url}?action=delete_spam&lead_id=' + leadId + '&spam_activity_id=' + activityId, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }}
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('Spam activity deleted successfully');
                            location.reload();
                        }} else {{
                            alert('Error deleting spam activity: ' + (data.error || 'Unknown error'));
                        }}
                    }})
                    .catch(error => {{
                        console.error('Error:', error);
                        alert('Error deleting spam activity');
                    }});
                }}
            }}
            </script>
            """
        else:
            search_text = f" matching \"{search_query}\"" if search_query else ""
            date_text = f" from {start_date} to {end_date}"
            content = f"""
            <h2>Spam Activities</h2>
            {filter_bar_html}
            <p>No spam activities found{search_text}{date_text}.</p>
            """
    
    return render_base_page("Spam Activities", content, "spam", base_url)

def render_spam_users_page(admin_api_key, base_url, search_query=None):
    """Render spam users page with search functionality"""
    
    # Build API endpoint with search parameter
    endpoint = '/spam/users'
    if search_query:
        endpoint += f'?search={urllib.parse.quote(search_query)}'
    
    data = make_admin_api_call(endpoint, admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading spam users: {data["error"]}</div>'
    else:
        spam_users = data.get('spam_users', [])
        
        # Search bar
        search_value = search_query if search_query else ''
        search_bar_html = f"""
        <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <form method="GET" action="{base_url}" style="display: flex; align-items: center; gap: 15px;">
                <input type="hidden" name="page" value="spam_users">
                <div style="flex: 1;">
                    <label for="search" style="margin-right: 10px; font-weight: 500;">Search:</label>
                    <input type="text" id="search" name="search" value="{search_value}" 
                           placeholder="Search by name or phone number..."
                           style="width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box;">
                </div>
                <button type="submit" class="btn">Search</button>
                <a href="{base_url}?page=spam_users" class="btn" style="background: #6b7280; text-decoration: none;">Clear</a>
            </form>
        </div>
        """
        
        if spam_users:
            table_rows = []
            for user in spam_users:
                first_spam = datetime.fromisoformat(user.get('first_spam', '').replace('Z', '+00:00')).strftime('%Y-%m-%d')
                last_spam = datetime.fromisoformat(user.get('last_spam', '').replace('Z', '+00:00')).strftime('%Y-%m-%d')
                status = '🚫 Blocked' if user.get('is_blocked') else '⚠️ Monitored'
                table_rows.append(f"""
                <tr>
                    <td>{user.get('lead_name', 'Unknown')}</td>
                    <td>{user.get('phone', 'N/A')}</td>
                    <td>{user.get('spam_count_30_days', 0)}</td>
                    <td>{first_spam}</td>
                    <td>{last_spam}</td>
                    <td>{status}</td>
                </tr>
                """)
            
            table_html = f"""
            <table class="table">
                <thead>
                    <tr>
                        <th>Lead</th>
                        <th>Phone</th>
                        <th>Spam Count (30d)</th>
                        <th>First Spam</th>
                        <th>Last Spam</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
            """
            
            # Show search results count
            results_info = f"<p style='margin-bottom: 15px; color: #6b7280;'>Found {len(spam_users)} spam user(s)" + (f" matching \"{search_query}\"" if search_query else "") + "</p>"
            
            content = f"""
            <h2>Spam Users</h2>
            {search_bar_html}
            {results_info}
            {table_html}
            """
        else:
            search_text = f" matching \"{search_query}\"" if search_query else ""
            content = f"""
            <h2>Spam Users</h2>
            {search_bar_html}
            <p>No spam users found{search_text}.</p>
            """
    
    return render_base_page("Spam Users", content, "spam_users", base_url)

def render_lead_detail_page(admin_api_key, lead_id, base_url):
    """Render individual lead details page"""
    data = make_admin_api_call(f'/leads/{lead_id}', admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading lead details: {data["error"]}</div>'
    else:
        lead = data.get('lead', {})
        activities = data.get('activities', [])
        
        contact_methods_html = '<ul>'
        for cm in lead.get('contact_methods', []):
            contact_methods_html += f"<li>{cm.get('type', '')}: {cm.get('value', '')}</li>"
        contact_methods_html += '</ul>'
        
        if activities:
            # Show only last 10 messages by default
            visible_activities = activities[-10:] if len(activities) > 10 else activities
            hidden_count = len(activities) - len(visible_activities)
            
            activities_html = f'''
            <div id="chat-container" style="background: #e5ddd5; padding: 20px; border-radius: 8px; max-height: 500px; overflow-y: auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            '''
            
            # Add "Load more messages" button if there are hidden messages
            if hidden_count > 0:
                activities_html += f'''
                <div id="load-more-container" style="text-align: center; margin-bottom: 15px;">
                    <button onclick="loadMoreMessages()" class="btn btn-small" style="background: #6b7280; font-size: 12px;">
                        Load {hidden_count} older message{'s' if hidden_count != 1 else ''}
                    </button>
                </div>
                <div id="older-messages" style="display: none;">
                '''
                
                # Render older messages (hidden by default)
                current_date = None
                for activity in activities[:-10]:
                    activity_datetime = datetime.fromisoformat(activity.get('created_at', '').replace('Z', '+00:00'))
                    activity_time = activity_datetime.strftime('%H:%M')
                    activity_date = activity_datetime.strftime('%Y-%m-%d')
                    direction = activity.get('direction', 'inbound')
                    
                    # Show date separator if date changed
                    if current_date != activity_date:
                        current_date = activity_date
                        date_display = activity_datetime.strftime('%d/%m/%Y')
                        activities_html += f'''
                        <div style="text-align: center; margin: 15px 0;">
                            <span style="background: rgba(0,0,0,0.1); padding: 4px 12px; border-radius: 12px; font-size: 12px; color: #666;">{date_display}</span>
                        </div>
                        '''
                    
                    # Extract and render message content
                    content_value = activity.get('content', 'N/A')
                    
                    if isinstance(content_value, dict):
                        if direction == 'inbound':
                            message_content = content_value.get('leadMessage', content_value.get('message', str(content_value)))
                        else:
                            message_content = content_value.get('assistantMessage', content_value.get('message', str(content_value)))
                    elif isinstance(content_value, str):
                        message_content = content_value
                    else:
                        message_content = str(content_value)
                    
                    if not message_content or message_content in ['N/A', 'None', '']:
                        continue
                    
                    is_incoming = direction == 'inbound'
                    
                    if is_incoming:
                        activities_html += f'''
                        <div style="display: flex; justify-content: flex-start; margin-bottom: 8px;">
                            <div style="background: white; padding: 8px 12px; border-radius: 18px; max-width: 70%; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                                <div style="font-size: 14px; line-height: 1.4; color: #333; word-wrap: break-word;">{message_content}</div>
                                <div style="font-size: 11px; color: #999; margin-top: 4px; text-align: right;">{activity_time}</div>
                            </div>
                        </div>
                        '''
                    else:
                        activities_html += f'''
                        <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;">
                            <div style="background: #dcf8c6; padding: 8px 12px; border-radius: 18px; max-width: 70%; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                                <div style="font-size: 14px; line-height: 1.4; color: #333; word-wrap: break-word;">{message_content}</div>
                                <div style="font-size: 11px; color: #999; margin-top: 4px; text-align: right;">{activity_time} ✓</div>
                            </div>
                        </div>
                        '''
                
                activities_html += '''
            </div>
            
            <script>
            function loadMoreMessages() {
                const olderMessages = document.getElementById('older-messages');
                const loadMoreContainer = document.getElementById('load-more-container');
                
                olderMessages.style.display = 'block';
                loadMoreContainer.style.display = 'none';
            }
            
            // Scroll to bottom on page load (like WhatsApp)
            window.addEventListener('load', function() {
                const chatContainer = document.getElementById('chat-container');
                chatContainer.scrollTop = chatContainer.scrollHeight;
            });
            </script>
            '''  # Close older-messages div
            
            # Render visible messages (last 10)
            current_date = None
            for activity in visible_activities:
                activity_datetime = datetime.fromisoformat(activity.get('created_at', '').replace('Z', '+00:00'))
                activity_time = activity_datetime.strftime('%H:%M')
                activity_date = activity_datetime.strftime('%Y-%m-%d')
                direction = activity.get('direction', 'inbound')  # Get the direction
                
                # Show date separator if date changed
                if current_date != activity_date:
                    current_date = activity_date
                    date_display = activity_datetime.strftime('%d/%m/%Y')
                    activities_html += f'''
                    <div style="text-align: center; margin: 15px 0;">
                        <span style="background: rgba(0,0,0,0.1); padding: 4px 12px; border-radius: 12px; font-size: 12px; color: #666;">{date_display}</span>
                    </div>
                    '''
                
                # Extract message content properly
                content_value = activity.get('content', 'N/A')
                
                # Handle both inbound and outbound messages
                if isinstance(content_value, dict):
                    # For inbound messages, use leadMessage
                    # For outbound messages, use assistantMessage
                    if direction == 'inbound':
                        message_content = content_value.get('leadMessage', content_value.get('message', str(content_value)))
                    else:  # outbound
                        message_content = content_value.get('assistantMessage', content_value.get('message', str(content_value)))
                elif isinstance(content_value, str):
                    message_content = content_value
                else:
                    message_content = str(content_value)
                
                # Skip if no actual message content
                if not message_content or message_content in ['N/A', 'None', '']:
                    continue
                
                # Determine if it's incoming or outgoing based on direction
                is_incoming = direction == 'inbound'
                
                if is_incoming:
                    # Incoming message (left side, gray bubble)
                    activities_html += f'''
                    <div style="display: flex; justify-content: flex-start; margin-bottom: 8px;">
                        <div style="background: white; padding: 8px 12px; border-radius: 18px; max-width: 70%; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                            <div style="font-size: 14px; line-height: 1.4; color: #333; word-wrap: break-word;">{message_content}</div>
                            <div style="font-size: 11px; color: #999; margin-top: 4px; text-align: right;">{activity_time}</div>
                        </div>
                    </div>
                    '''
                else:
                    # Outgoing message (right side, green bubble)
                    activities_html += f'''
                    <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;">
                        <div style="background: #dcf8c6; padding: 8px 12px; border-radius: 18px; max-width: 70%; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                            <div style="font-size: 14px; line-height: 1.4; color: #333; word-wrap: break-word;">{message_content}</div>
                            <div style="font-size: 11px; color: #999; margin-top: 4px; text-align: right;">{activity_time} ✓</div>
                        </div>
                    </div>
                    '''
            
            activities_html += '</div>'
        else:
            activities_html = '<p>No activities found for this lead.</p>'
        
        content = f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2>Lead Details: {lead.get('name', 'Unknown')}</h2>
            <a href="{base_url}?page=leads" class="btn">Back to Leads</a>
        </div>
        
        <div style="margin-bottom: 30px;">
            <h3>Contact Information</h3>
            <p><strong>Name:</strong> {lead.get('name', 'Unknown')}</p>
            <p><strong>Created:</strong> {datetime.fromisoformat(lead.get('created_at', '').replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M') if lead.get('created_at') else 'Unknown'}</p>
            <p><strong>Contact Methods:</strong></p>
            {contact_methods_html}
        </div>
        
        <div>
            <h3>Recent Activities</h3>
            {activities_html}
        </div>
        """
    
    return render_base_page("Lead Details", content, "leads", base_url)

def render_create_lead_page(base_url):
    """Render create lead form"""
    content = f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2>Create New Lead</h2>
        <a href="{base_url}?page=leads" class="btn">Back to Leads</a>
    </div>
    
    <form method="POST" action="{base_url}?page=create_lead">
        <div class="form-group">
            <label for="name">Name:</label>
            <input type="text" id="name" name="name" required>
        </div>
        <div class="form-group">
            <label for="contact_type">Contact Type:</label>
            <select id="contact_type" name="contact_type" required>
                <option value="phone">Phone</option>
                <option value="email">Email</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="telegram">Telegram</option>
            </select>
        </div>
        <div class="form-group">
            <label for="contact_value">Contact Value:</label>
            <input type="text" id="contact_value" name="contact_value" required>
        </div>
        <div class="form-group">
            <label for="notes">Notes (optional):</label>
            <textarea id="notes" name="notes" rows="3"></textarea>
        </div>
        <button type="submit" class="btn">Create Lead</button>
    </form>
    """
    
    return render_base_page("Create Lead", content, "leads", base_url)

def handle_create_lead_post(admin_api_key, form_data, base_url):
    """Handle create lead form submission"""
    lead_data = {
        "name": form_data.get('name', ''),
        "contact_methods": [{
            "type": form_data.get('contact_type', ''),
            "value": form_data.get('contact_value', '')
        }],
        "metadata": {
            "source": "admin_panel",
            "notes": form_data.get('notes', '')
        }
    }
    
    result = make_admin_api_call('/leads', admin_api_key, 'POST', json.dumps(lead_data))
    
    if 'error' in result:
        content = f"""
        <div class="error">Error creating lead: {result['error']}</div>
        <a href="{base_url}?page=create_lead" class="btn">Try Again</a>
        """
    else:
        content = f"""
        <div class="success">Lead created successfully!</div>
        <a href="{base_url}?page=leads" class="btn">View All Leads</a>
        """
    
    return render_base_page("Create Lead Result", content, "leads", base_url)

def render_spam_config_page(admin_api_key, base_url):
    """Render spam configuration page"""
    data = make_admin_api_call('/config', admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading configuration: {data["error"]}</div>'
    else:
        spam_detection = data.get('spam_detection', {})
        spam_messages = data.get('spam_messages', {})
        
        # Format spam activities limits for display
        spam_activities_limits = spam_detection.get('spam_activities_limits', [])
        spam_limits_rows = []
        for i, limit in enumerate(spam_activities_limits):
            if isinstance(limit, list) and len(limit) >= 2:
                days, count = limit[0], limit[1]
                action = limit[2] if len(limit) > 2 else 'warn'
            else:
                days, count, action = '', '', 'warn'
            spam_limits_rows.append(f"""
            <tr>
                <td><input type="number" name="spam_activities_limits_{i}_days" value="{days}" style="width: 80px;"></td>
                <td><input type="number" name="spam_activities_limits_{i}_count" value="{count}" style="width: 80px;"></td>
                <td><input type="text" name="spam_activities_limits_{i}_action" value="{action}" style="width: 100px;"></td>
            </tr>
            """)
        
        # Format message limits for display
        message_limits = spam_detection.get('message_limits', [])
        message_limits_rows = []
        for i, limit in enumerate(message_limits):
            if isinstance(limit, list) and len(limit) >= 2:
                days, count = limit[0], limit[1]
                action = limit[2] if len(limit) > 2 else 'warn'
            else:
                days, count, action = '', '', 'warn'
            message_limits_rows.append(f"""
            <tr>
                <td><input type="number" name="message_limits_{i}_days" value="{days}" style="width: 80px;"></td>
                <td><input type="number" name="message_limits_{i}_count" value="{count}" style="width: 80px;"></td>
                <td><input type="text" name="message_limits_{i}_action" value="{action}" style="width: 100px;"></td>
            </tr>
            """)
        
        content = f"""
        <h2>Spam Configuration</h2>
        
        <form method="POST" action="{base_url}?page=spam_config">
            <!-- Spam Detection Settings -->
            <div class="config-section">
                <h3>Spam Detection Settings</h3>
                
                <div class="form-group">
                    <label for="warning_threshold_offset">Warning Threshold Offset:</label>
                    <input type="number" id="warning_threshold_offset" name="warning_threshold_offset" 
                           value="{spam_detection.get('warning_threshold_offset', 5)}" min="0" max="50">
                    <small style="color: #6b7280;">Days before limit to send warning</small>
                </div>
                
                <!-- Spam Activities Limits -->
                <div class="form-group">
                    <label>Spam Activities Limits:</label>
                    <table class="limits-table">
                        <thead>
                            <tr>
                                <th>Days</th>
                                <th>Count</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(spam_limits_rows)}
                        </tbody>
                    </table>
                </div>
                
                <!-- Message Limits -->
                <div class="form-group">
                    <label>Message Limits:</label>
                    <table class="limits-table">
                        <thead>
                            <tr>
                                <th>Days</th>
                                <th>Count</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(message_limits_rows)}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <!-- Spam Messages -->
            <div class="config-section">
                <h3>Spam Response Messages</h3>
                
                <div class="form-group">
                    <label for="warning_message_es">Warning Message (Spanish):</label>
                    <textarea id="warning_message_es" name="warning_message_es" rows="3">{spam_messages.get('warning_message_es', '')}</textarea>
                </div>
                
                <div class="form-group">
                    <label for="blocked_message_es">Blocked Message (Spanish):</label>
                    <textarea id="blocked_message_es" name="blocked_message_es" rows="3">{spam_messages.get('blocked_message_es', '')}</textarea>
                </div>
            </div>
            
            <div style="margin-top: 30px; text-align: center;">
                <button type="submit" class="btn" style="padding: 12px 24px; font-size: 16px;">Save Configuration</button>
                <a href="{base_url}?page=spam_config" class="btn" style="background: #6b7280; text-decoration: none; padding: 12px 24px; margin-left: 10px;">Reset</a>
            </div>
        </form>
        """
    
    return render_base_page("Spam Config", content, "spam_config", base_url)

def handle_spam_config_post(admin_api_key, form_data, base_url):
    """Handle spam configuration form submission"""
    try:
        # Parse spam activities limits
        spam_activities_limits = []
        i = 0
        while f'spam_activities_limits_{i}_days' in form_data:
            days = form_data.get(f'spam_activities_limits_{i}_days')
            count = form_data.get(f'spam_activities_limits_{i}_count')
            action = form_data.get(f'spam_activities_limits_{i}_action')
            
            if days and count and action:
                spam_activities_limits.append({
                    'days': int(days),
                    'count': int(count),
                    'action': action
                })
            i += 1
        
        # Parse message limits
        message_limits = []
        i = 0
        while f'message_limits_{i}_days' in form_data:
            days = form_data.get(f'message_limits_{i}_days')
            count = form_data.get(f'message_limits_{i}_count')
            action = form_data.get(f'message_limits_{i}_action')
            
            if days and count and action:
                message_limits.append({
                    'days': int(days),
                    'count': int(count),
                    'action': action
                })
            i += 1
        
        # Build configuration update object
        config_update = {
            'spam_detection': {
                'spam_activities_limits': spam_activities_limits,
                'message_limits': message_limits,
                'warning_threshold_offset': int(form_data.get('warning_threshold_offset', 5))
            },
            'spam_messages': {
                'warning_message_es': form_data.get('warning_message_es', ''),
                'blocked_message_es': form_data.get('blocked_message_es', '')
            }
        }
        
        # Send update to API
        result = make_admin_api_call('/config', admin_api_key, 'PUT', json.dumps(config_update))
        
        if 'error' in result:
            content = f"""
            <div class="error">Error updating configuration: {result['error']}</div>
            <a href="{base_url}?page=spam_config" class="btn">Try Again</a>
            """
        else:
            content = f"""
            <div class="success">Configuration updated successfully!</div>
            <a href="{base_url}?page=spam_config" class="btn">Back to Configuration</a>
            """
        
        return render_base_page("Config Update Result", content, "spam_config", base_url)
        
    except Exception as e:
        logger.error(f"Error processing config update: {str(e)}")
        content = f"""
        <div class="error">Error processing configuration update: {str(e)}</div>
        <a href="{base_url}?page=spam_config" class="btn">Try Again</a>
        """
        return render_base_page("Config Update Error", content, "spam_config", base_url)

def render_integration_page(admin_api_key, base_url):
    """Render Twilio integration page"""
    data = make_admin_api_call('/twilio', admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading Twilio credentials: {data["error"]}</div>'
    else:
        account_sid = data.get('account_sid', '')
        auth_token_masked = data.get('auth_token_masked', '')
        has_credentials = data.get('has_credentials', False)
        
        status_html = ""
        if has_credentials:
            status_html = f"""
            <div class="success" style="margin-bottom: 20px;">
                Twilio credentials are configured
            </div>
            """
        else:
            status_html = f"""
            <div class="error" style="margin-bottom: 20px;">
                Twilio credentials are not configured
            </div>
            """
        
        content = f"""
        <h2>Integration Configuration</h2>
        
        {status_html}
        
        <form method="POST" action="{base_url}?page=integration" onsubmit="return confirmUpdate()">
            <div class="config-section">
                <h3>Twilio Credentials</h3>
                
                <div class="form-group">
                    <label for="account_sid">Account SID:</label>
                    <input type="text" id="account_sid" name="account_sid" 
                           value="{account_sid}" placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" required>
                    <small style="color: #6b7280;">Your Twilio Account SID (starts with AC)</small>
                </div>
                
                <div class="form-group">
                    <label for="auth_token">Auth Token:</label>
                    <input type="password" id="auth_token" name="auth_token" 
                           placeholder="{'Current token: ' + auth_token_masked if auth_token_masked else 'Enter your Auth Token'}" required>
                    <small style="color: #6b7280;">Your Twilio Auth Token (32 characters)</small>
                </div>
                
                <div style="margin-top: 30px; text-align: center;">
                    <button type="submit" class="btn" style="padding: 12px 24px; font-size: 16px;">Update Credentials</button>
                    <a href="{base_url}?page=integration" class="btn" style="background: #6b7280; text-decoration: none; padding: 12px 24px; margin-left: 10px;">Cancel</a>
                </div>
            </div>
        </form>
        
        <script>
        function confirmUpdate() {{
            return confirm('Are you sure you want to update the Twilio credentials? This will affect WhatsApp message sending functionality.');
        }}
        </script>
        """
    
    return render_base_page("Integration", content, "integration", base_url)

def handle_integration_post(admin_api_key, form_data, base_url):
    """Handle Twilio integration form submission"""
    try:
        account_sid = form_data.get('account_sid', '').strip()
        auth_token = form_data.get('auth_token', '').strip()
        
        if not account_sid or not auth_token:
            content = f"""
            <div class="error">Both Account SID and Auth Token are required.</div>
            <a href="{base_url}?page=integration" class="btn">Try Again</a>
            """
            return render_base_page("Integration Error", content, "integration", base_url)
        
        # Send update to API
        twilio_update = {
            'account_sid': account_sid,
            'auth_token': auth_token
        }
        
        result = make_admin_api_call('/twilio', admin_api_key, 'PUT', json.dumps(twilio_update))
        
        if 'error' in result:
            content = f"""
            <div class="error">Error updating Twilio credentials: {result['error']}</div>
            <a href="{base_url}?page=integration" class="btn">Try Again</a>
            """
        else:
            content = f"""
            <div class="success">Twilio credentials updated successfully!</div>
            <p>Your WhatsApp messaging functionality is now configured.</p>
            <a href="{base_url}?page=integration" class="btn">Back to Integration</a>
            """
        
        return render_base_page("Integration Result", content, "integration", base_url)
        
    except Exception as e:
        logger.error(f"Error processing Twilio integration update: {str(e)}")
        content = f"""
        <div class="error">Error processing Twilio credentials update: {str(e)}</div>
        <a href="{base_url}?page=integration" class="btn">Try Again</a>
        """
        return render_base_page("Integration Error", content, "integration", base_url)

def render_system_prompt_page(base_url):
    """Render system prompt editor page"""
    content, error = get_system_prompt_from_s3()
    
    if error:
        content_html = f'<div class="error">Error loading system prompt: {error}</div>'
        prompt_content = ""
    else:
        prompt_content = content if content else ""
        content_html = ""
    
    page_content = f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2>System Prompt Editor</h2>
        <div>
            <button type="button" onclick="resetContent()" class="btn" style="background: #6b7280; margin-right: 10px;">Reset</button>
            <button type="submit" form="promptForm" class="btn">Save Changes</button>
        </div>
    </div>
    
    {content_html}
    
    <div class="config-section">
        <h3>AI Assistant System Prompt</h3>
        <p style="color: #6b7280; margin-bottom: 15px;">
            This prompt defines the behavior and knowledge of your AI assistant. It includes company information, 
            product details, and interaction guidelines. Changes will take effect immediately after saving.
        </p>
        
        <form id="promptForm" method="POST" action="{base_url}?page=system_prompt" onsubmit="return confirmSave()">
            <div class="form-group">
                <label for="prompt_content">System Prompt Content:</label>
                <textarea id="prompt_content" name="prompt_content" class="prompt-editor" required>{prompt_content}</textarea>
            </div>
            
            <div style="margin-top: 20px; padding: 15px; background: #f0fdf4; border-radius: 6px; border-left: 4px solid #16a34a;">
                <h4 style="margin-top: 0; color: #15803d;">Guidelines for editing:</h4>
                <ul style="color: #166534; margin: 0;">
                    <li>Keep the assistant focused on sales and lead generation</li>
                    <li>Maintain the character limit (280 characters for responses)</li>
                    <li>Ensure company information is accurate and up-to-date</li>
                    <li>Test changes with the chat interface after saving</li>
                </ul>
            </div>
        </form>
    </div>
    
    <script>
    let originalContent = `{prompt_content}`;
    
    function confirmSave() {{
        const currentContent = document.getElementById('prompt_content').value;
        if (currentContent !== originalContent) {{
            return confirm('Are you sure you want to save these changes to the system prompt? This will affect all AI interactions immediately.');
        }}
        return true;
    }}
    
    function resetContent() {{
        if (confirm('Are you sure you want to reset the content to the original version? All unsaved changes will be lost.')) {{
            document.getElementById('prompt_content').value = originalContent;
        }}
    }}
    
    // Track changes
    document.getElementById('prompt_content').addEventListener('input', function() {{
        const hasChanges = this.value !== originalContent;
        const saveButton = document.querySelector('button[type="submit"]');
        if (hasChanges) {{
            saveButton.style.background = '#dc2626';
            saveButton.textContent = 'Save Changes*';
        }} else {{
            saveButton.style.background = '#2563eb';
            saveButton.textContent = 'Save Changes';
        }}
    }});
    </script>
    """
    
    return render_base_page("System Prompt", page_content, "system_prompt", base_url)

def handle_system_prompt_post(form_data, base_url):
    """Handle system prompt form submission"""
    try:
        prompt_content = form_data.get('prompt_content', '').strip()
        
        if not prompt_content:
            content = f"""
            <div class="error">System prompt content cannot be empty.</div>
            <a href="{base_url}?page=system_prompt" class="btn">Go Back</a>
            """
            return render_base_page("System Prompt Error", content, "system_prompt", base_url)
        
        # Save to S3
        success, error = save_system_prompt_to_s3(prompt_content)
        
        if not success:
            content = f"""
            <div class="error">Error saving system prompt: {error}</div>
            <a href="{base_url}?page=system_prompt" class="btn">Try Again</a>
            """
        else:
            content = f"""
            <div class="success">System prompt updated successfully!</div>
            <p>The AI assistant will now use the updated prompt for all new conversations.</p>
            <div style="margin-top: 20px;">
                <a href="{base_url}?page=system_prompt" class="btn">Edit Again</a>
                <a href="{base_url}" class="btn" style="background: #6b7280; text-decoration: none; margin-left: 10px;">Back to Dashboard</a>
            </div>
            """
        
        return render_base_page("System Prompt Result", content, "system_prompt", base_url)
        
    except Exception as e:
        logger.error(f"Error processing system prompt update: {str(e)}")
        content = f"""
        <div class="error">Error processing system prompt update: {str(e)}</div>
        <a href="{base_url}?page=system_prompt" class="btn">Try Again</a>
        """
        return render_base_page("System Prompt Error", content, "system_prompt", base_url)

def lambda_handler(event, context):
    """Main Lambda handler for secure backoffice web interface"""
    
    try:
        # Parse request
        http_method = event.get('httpMethod', 'GET')
        query_params = event.get('queryStringParameters') or {}
        headers = event.get('headers') or {}
        
        # Get base URL from the event
        base_url = get_base_url(event)
        
        # Get session from cookie
        cookie_header = headers.get('Cookie') or headers.get('cookie')
        session_id = get_session_from_cookie(cookie_header)
        
        # Handle logout
        if query_params.get('action') == 'logout':
            if session_id:
                delete_session(session_id)
            return create_response(
                302, 
                '', 
                set_cookie=f'session_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path={base_url}; Secure',
                location=base_url
            )
        
        # Handle login
        if http_method == 'POST' and not query_params.get('page') and not query_params.get('action'):
            # Parse form data
            body = event.get('body', '')
            if event.get('isBase64Encoded'):
                body = base64.b64decode(body).decode('utf-8')
            
            # Simple form parsing
            form_data = {}
            if body:  # Only parse if body is not empty
                for item in body.split('&'):
                    if '=' in item:
                        key, value = item.split('=', 1)
                        form_data[key] = urllib.parse.unquote_plus(value)
            
            api_key = form_data.get('api_key')
            
            if api_key and verify_admin_key(api_key):
                # Create session
                session_id = create_session('admin', api_key)
                if session_id:
                    # Redirect to dashboard with session cookie
                    return create_response(
                        302, 
                        '', 
                        set_cookie=f'session_id={session_id}; path={base_url}; HttpOnly; Secure; SameSite=Strict',
                        location=base_url
                    )
                else:
                    return create_response(200, render_login_page("Session creation failed"))
            else:
                return create_response(200, render_login_page("Invalid API key"))
        
        # Check if user is authenticated
        if not session_id or not verify_session(session_id):
            return create_response(200, render_login_page())
        
        # Get API key from session
        admin_api_key = get_session_api_key(session_id)
        if not admin_api_key:
            return create_response(200, render_login_page("Session expired"))
        
        # Handle special actions
        if query_params.get('action') == 'delete_spam':
            lead_id = query_params.get('lead_id')
            spam_activity_id = query_params.get('spam_activity_id')
            
            if not lead_id or not spam_activity_id:
                return create_response(400, json.dumps({'error': 'Lead ID and Spam Activity ID are required'}), 'application/json')
            
            # Make API call to delete spam activity
            result = make_admin_api_call(f'/leads/{lead_id}?spam_activity_id={spam_activity_id}', admin_api_key, 'DELETE')
            
            return create_response(200, json.dumps(result), 'application/json')
        
        # Route to different pages
        page = query_params.get('page', 'analytics')
        
        # Handle POST requests for forms
        if http_method == 'POST':
            body = event.get('body', '')
            if event.get('isBase64Encoded'):
                body = base64.b64decode(body).decode('utf-8')
            
            # Simple form parsing
            form_data = {}
            if body:  # Only parse if body is not empty
                for item in body.split('&'):
                    if '=' in item:
                        key, value = item.split('=', 1)
                        form_data[key] = urllib.parse.unquote_plus(value)
            
            if page == 'create_lead':
                return create_response(200, handle_create_lead_post(admin_api_key, form_data, base_url))
            elif page == 'spam_config':
                return create_response(200, handle_spam_config_post(admin_api_key, form_data, base_url))
            elif page == 'integration':
                return create_response(200, handle_integration_post(admin_api_key, form_data, base_url))
            elif page == 'system_prompt':
                return create_response(200, handle_system_prompt_post(form_data, base_url))
        
        # Handle GET requests for different pages
        if page == 'analytics':
            start_date = query_params.get('start_date')
            end_date = query_params.get('end_date')
            return create_response(200, render_analytics_page(admin_api_key, base_url, start_date, end_date))
        elif page == 'leads':
            search_query = query_params.get('search')
            return create_response(200, render_leads_page(admin_api_key, base_url, search_query))
        elif page == 'spam':
            search_query = query_params.get('search')
            start_date = query_params.get('start_date')
            end_date = query_params.get('end_date')
            return create_response(200, render_spam_activities_page(admin_api_key, base_url, search_query, start_date, end_date))
        elif page == 'spam_users':
            search_query = query_params.get('search')
            return create_response(200, render_spam_users_page(admin_api_key, base_url, search_query))
        elif page == 'lead_detail':
            lead_id = query_params.get('id')
            if lead_id:
                return create_response(200, render_lead_detail_page(admin_api_key, lead_id, base_url))
            else:
                return create_response(200, render_leads_page(admin_api_key, base_url))
        elif page == 'create_lead':
            return create_response(200, render_create_lead_page(base_url))
        elif page == 'spam_config':
            return create_response(200, render_spam_config_page(admin_api_key, base_url))
        elif page == 'integration':
            return create_response(200, render_integration_page(admin_api_key, base_url))
        elif page == 'system_prompt':
            return create_response(200, render_system_prompt_page(base_url))
        elif page == 'analytics' or page == '':
            start_date = query_params.get('start_date')
            end_date = query_params.get('end_date')
            return create_response(200, render_analytics_page(admin_api_key, base_url, start_date, end_date))
        else:
            start_date = query_params.get('start_date')
            end_date = query_params.get('end_date')
            return create_response(200, render_analytics_page(admin_api_key, base_url, start_date, end_date))
    
    except Exception as e:
        logger.error(f"Error in backoffice handler: {str(e)}")
        return create_response(500, f"<h1>Internal Server Error</h1><p>{str(e)}</p>")
