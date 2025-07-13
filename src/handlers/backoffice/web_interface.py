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

def render_base_page(title, content, current_page='dashboard', base_url='/dev/backoffice'):
    """Render base page template with navigation"""
    nav_items = [
       ('dashboard', 'Dashboard', f'{base_url}'),
       ('analytics', 'Analytics', f'{base_url}?page=analytics'),
       ('leads', 'Leads', f'{base_url}?page=leads'),
       ('spam', 'Spam Activities', f'{base_url}?page=spam'),
       ('spam_users', 'Spam Users', f'{base_url}?page=spam_users')
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

def render_dashboard(admin_api_key, base_url):
    """Render the main dashboard"""
    content = """
    <h2>Welcome to CRM Backoffice</h2>
    <p>Use the navigation above to access different sections of the admin panel.</p>
    <p>All data is securely fetched from your admin API using server-side authentication.</p>
    """
    return render_base_page("Dashboard", content, "dashboard", base_url)

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

def render_spam_activities_page(admin_api_key, base_url):
    """Render spam activities page"""
    data = make_admin_api_call('/spam', admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading spam activities: {data["error"]}</div>'
    elif isinstance(data, list) and data:
        table_rows = []
        for spam in data:
            spam_date = datetime.fromisoformat(spam.get('spam_date', '').replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
            message_preview = (spam.get('message', '')[:50] + '...') if len(spam.get('message', '')) > 50 else spam.get('message', '')
            table_rows.append(f"""
            <tr>
                <td>{spam_date}</td>
                <td>{spam.get('lead_name', 'Unknown')}</td>
                <td>{spam.get('phone', 'N/A')}</td>
                <td title="{spam.get('message', '')}">{message_preview}</td>
                <td>{spam.get('spam_reason', 'N/A')}</td>
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
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
        """
        content = f"<h2>Recent Spam Activities</h2>{table_html}"
    else:
        content = "<h2>Recent Spam Activities</h2><p>No spam activities found.</p>"
    
    return render_base_page("Spam Activities", content, "spam", base_url)

def render_spam_users_page(admin_api_key, base_url):
    """Render spam users page"""
    data = make_admin_api_call('/spam/users', admin_api_key)
    
    if 'error' in data:
        content = f'<div class="error">Error loading spam users: {data["error"]}</div>'
    elif isinstance(data, list) and data:
        table_rows = []
        for user in data:
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
        content = f"<h2>Spam Users</h2>{table_html}"
    else:
        content = "<h2>Spam Users</h2><p>No spam users found.</p>"
    
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
            activities_html = '<table class="table"><thead><tr><th>Date</th><th>Type</th><th>Content</th><th>Platform</th></tr></thead><tbody>'
            for activity in activities:
                activity_date = datetime.fromisoformat(activity.get('created_at', '').replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                activities_html += f"""
                <tr>
                    <td>{activity_date}</td>
                    <td>{activity.get('activity_type', 'N/A')}</td>
                    <td>{activity.get('content', 'N/A')[:100]}...</td>
                    <td>{activity.get('platform', 'N/A')}</td>
                </tr>
                """
            activities_html += '</tbody></table>'
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
        if http_method == 'POST' and not query_params.get('page'):
            # Parse form data
            body = event.get('body', '')
            if event.get('isBase64Encoded'):
                body = base64.b64decode(body).decode('utf-8')
            
            # Simple form parsing
            form_data = {}
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
        
        # Route to different pages
        page = query_params.get('page', 'dashboard')
        
        # Handle POST requests for forms
        if http_method == 'POST':
            if page == 'create_lead':
                body = event.get('body', '')
                if event.get('isBase64Encoded'):
                    body = base64.b64decode(body).decode('utf-8')
                
                form_data = {}
                for item in body.split('&'):
                    if '=' in item:
                        key, value = item.split('=', 1)
                        form_data[key] = urllib.parse.unquote_plus(value)
                
                return create_response(200, handle_create_lead_post(admin_api_key, form_data, base_url))
        
        # Handle GET requests for different pages
        if page == 'analytics':
            start_date = query_params.get('start_date')
            end_date = query_params.get('end_date')
            return create_response(200, render_analytics_page(admin_api_key, base_url, start_date, end_date))
        elif page == 'leads':
            search_query = query_params.get('search')
            return create_response(200, render_leads_page(admin_api_key, base_url, search_query))
        elif page == 'spam':
            return create_response(200, render_spam_activities_page(admin_api_key, base_url))
        elif page == 'spam_users':
            return create_response(200, render_spam_users_page(admin_api_key, base_url))
        elif page == 'lead_detail':
            lead_id = query_params.get('id')
            if lead_id:
                return create_response(200, render_lead_detail_page(admin_api_key, lead_id, base_url))
            else:
                return create_response(200, render_leads_page(admin_api_key, base_url))
        elif page == 'create_lead':
            return create_response(200, render_create_lead_page(base_url))
        elif page == 'dashboard' or page == '':
            return create_response(200, render_dashboard(admin_api_key, base_url))
        else:
            return create_response(200, render_dashboard(admin_api_key, base_url))
    
    except Exception as e:
        logger.error(f"Error in backoffice handler: {str(e)}")
        return create_response(500, f"<h1>Internal Server Error</h1><p>{str(e)}</p>")
