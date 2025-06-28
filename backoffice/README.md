# PandasDB CRM Backoffice

Modern web-based backoffice interface for monitoring and managing the PandasDB CRM Communication System.

## 🎯 Features

### **📊 Dashboard Analytics**
- Real-time system statistics
- Daily message volume tracking
- Spam detection metrics
- System health monitoring

### **👥 Lead Management**
- Create new leads with contact methods
- Lead lookup and listing with pagination
- Complete conversation history
- Contact method tracking
- Activity timeline view

### **🚫 Spam Monitoring**
- Recent spam activities list
- Spam user classification
- Detection reason tracking
- Blocking status overview

## 🏗️ Architecture

```
Frontend (S3 + CloudFront) ←→ API Gateway ←→ Lambda Functions ←→ DynamoDB
```

### **Separate Infrastructure**
The backoffice has its own serverless.yml and deployment pipeline, making it completely optional:

- **Independent Deployment**: Deploy only if needed
- **Separate Scaling**: Different performance requirements
- **Optional Feature**: Can be skipped for minimal deployments
- **Easy Removal**: Clean removal without affecting main system

### **Handler-Based Architecture**
Each API endpoint has its own dedicated Lambda function:

- **Modular Design**: Separate handlers per endpoint
- **Easy Maintenance**: Focused, single-purpose functions
- **Independent Scaling**: Each function scales independently
- **Clear Separation**: Lead management vs analytics

## 🚀 Deployment

### **Prerequisites**
Deploy the main CRM system first to create the required DynamoDB tables:
```bash
# From project root
npm run deploy:dev
```

### **Deploy Backoffice (Option 1: Automated Script)**
```bash
cd backoffice
chmod +x scripts/deploy.sh
./scripts/deploy.sh dev
```

### **Deploy Backoffice (Option 2: Manual Steps)**
```bash
cd backoffice

# 1. Deploy infrastructure
npx serverless deploy --stage dev

# 2. Deploy frontend files
npm run deploy-frontend

# 3. Invalidate CloudFront cache
npm run invalidate

# Or all in one command
npm run deploy-all
```

### **Production Deployment**
```bash
cd backoffice

# Automated
./scripts/deploy.sh prod

# Manual
npm run deploy-all:prod
```

### **Remove Backoffice**
```bash
cd backoffice
npm run remove-infra
```

## 📁 File Structure

```
backoffice/
├── api/                    # Lambda function handlers
│   ├── utils.py           # Shared utilities
│   ├── create_leads.py    # Lead creation endpoint
│   ├── list_leads.py      # Lead listing with pagination
│   ├── get_lead_details.py # Lead details with activities
│   ├── get_daily_analytics.py # Dashboard statistics
│   ├── get_spam_activities.py # Spam monitoring
│   ├── get_spam_users.py  # Spam user classification
│   ├── get_spam_analytics.py # Additional spam analytics
│   └── handlers.py        # Legacy single handler (optional)
├── frontend/              # Static web interface
│   ├── index.html        # Main backoffice page
│   ├── style.css         # Modern styling
│   └── scripts.js        # Application logic
├── scripts/              # Deployment automation
│   └── deploy.sh         # Automated deployment script
├── serverless.yml        # Infrastructure as Code
├── package.json          # Frontend deployment scripts
└── README.md             # This file
```

## 🔧 Configuration

### **Automatic Configuration**
The deployment script automatically:
- Detects main API Gateway URL
- Retrieves auto-generated API key
- Updates frontend configuration in `scripts.js`
- Deploys to correct S3 bucket
- Invalidates CloudFront cache
- Provides access URLs and credentials

### **Manual Configuration**
If needed, update the API URL and key in `frontend/scripts.js`:
```javascript
getApiBaseUrl() {
    return 'https://your-actual-api-gateway-url.com/dev';
}

getApiKey() {
    return 'your-auto-generated-api-key';
}
```

## 📊 API Endpoints

### **Lead Management**
| Method | Endpoint | Handler | Purpose |
|--------|----------|---------|---------|
| `POST` | `/api/leads` | `create_leads.py` | Create lead with contact methods |
| `GET` | `/api/leads` | `list_leads.py` | List leads with pagination |
| `GET` | `/api/lead/{id}` | `get_lead_details.py` | Lead details with history |

### **Analytics & Monitoring**
| Method | Endpoint | Handler | Purpose |
|--------|----------|---------|---------|
| `GET` | `/api/analytics/daily` | `get_daily_analytics.py` | Dashboard statistics |
| `GET` | `/api/spam/activities` | `get_spam_activities.py` | Recent spam activities |
| `GET` | `/api/spam/users` | `get_spam_users.py` | Spam user classification |
| `GET` | `/api/spam/analytics` | `get_spam_analytics.py` | Additional spam analytics |
| `DELETE` | `/api/spam/activities/{lead_id}` | `remove_spam_activities.py` | Remove spam activities for lead |

### **API Security**
All endpoints require API key authentication:
```bash
# Remove all spam activities for a lead
curl -X DELETE -H "x-api-key: YOUR-API-KEY" \
  https://api-url/api/spam/activities/lead-123

# Remove specific spam activity for a lead
curl -X DELETE -H "x-api-key: YOUR-API-KEY" \
  https://api-url/api/spam/activities/lead-123?activity_id=activity-456

# Get analytics
curl -H "x-api-key: YOUR-API-KEY" https://api-url/api/analytics/daily
```

## 🎨 UI/UX Features

### **Modern Design**
- **Gradient Backgrounds**: Purple/blue gradients
- **Glass Morphism**: Translucent cards with backdrop blur  
- **Smooth Animations**: Hover effects and transitions
- **Responsive Layout**: Works on all devices

### **Performance Optimized**
- **CloudFront CDN**: Global edge locations
- **Compressed Assets**: Gzip compression enabled
- **Optimized Caching**: Smart cache policies
- **Fast Loading**: < 2 second initial load

## 🔍 Monitoring Capabilities

### **Real-time Analytics**
- Total leads in system
- Daily message volume
- Spam detection percentage
- Active spam users count

### **Lead Management**
- Create new leads via API
- Search and filter leads
- View complete conversation history
- Track contact methods and settings

### **Detailed Insights**
- Individual lead conversation history
- Spam activity timeline with reasons
- System health indicators
- Performance metrics

## 🚨 Troubleshooting

### **Common Issues**

1. **Main Stack Not Found**
   ```bash
   # Deploy main system first
   serverless deploy --stage dev
   ```

2. **API Authentication Failed**
   ```bash
   # Check API key in CloudFormation outputs
   aws cloudformation describe-stacks --stack-name pandasdb-crm-comm-backoffice-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`BackofficeApiKeyValue`].OutputValue' --output text
   ```

3. **CloudFront Not Updating**
   ```bash
   # Invalidate cache manually
   npm run invalidate
   
   # Or using the deploy script
   ./scripts/deploy.sh dev
   ```

4. **API Connection Issues**
   ```bash
   # Test with API key
   curl -H "x-api-key: YOUR-API-KEY" https://your-api-url/api/analytics/daily
   ```

5. **Permission Errors**
   ```bash
   # Check AWS credentials
   aws sts get-caller-identity
   ```

6. **Lambda Import Errors**
   ```bash
   # Check handler path structure
   ls -la api/
   
   # Verify utils.py exists
   cat api/utils.py
   ```

### **Debug Commands**
```bash
# Check backoffice infrastructure
npx serverless info --stage dev

# View deployment logs
npx serverless logs -f createLeads --stage dev

# Test API endpoints with authentication
curl -H "x-api-key: YOUR-API-KEY" https://your-api-url/api/analytics/daily

# Use automated deployment script
./scripts/deploy.sh dev
```

## 🔐 Security

### **API Key Authentication**
- **Auto-generated Keys**: Deterministic API key per deployment
- **Rate Limiting**: 100 req/sec, 200 burst, 10K daily quota
- **Private Endpoints**: All API endpoints require valid API key
- **Secure Headers**: API key passed via `x-api-key` header

### **Access Control**
- **Secured API**: All endpoints protected with API key authentication
- **API Gateway**: CORS enabled with rate limiting
- **Lambda Functions**: Minimal IAM permissions
- **DynamoDB**: Read/write access to required tables only

### **Data Protection**
- **HTTPS Only**: Enforced via CloudFront
- **No Sensitive Data**: Only business data
- **Encrypted Transit**: All data encrypted in transit
- **Resource Isolation**: Separate from main system

### **Security Features**
- **Auto-generated API Keys**: Format: `{StackName}-{AccountId}-{Region}-{Stage}`
- **Usage Plans**: Throttling and quota management
- **Request Validation**: Input validation at API Gateway level
- **Error Handling**: No sensitive info in error responses

## 💰 Cost Implications

### **Additional Costs**
- **Lambda Functions**: ~$0.01-0.10/month per function
- **S3 Storage**: ~$0.50/month for static files
- **CloudFront**: ~$1-5/month depending on usage
- **API Gateway**: ~$0.10/month for API calls + usage plan overhead

### **Cost Optimization**
- **Pay-per-request**: Only pay for actual usage
- **CDN Caching**: Reduces API calls
- **Static Hosting**: No server costs
- **Optional Deployment**: Only deploy if needed

## 📈 Performance

### **Handler Performance**
- **Cold Start**: < 1 second per function
- **Warm Execution**: < 100ms
- **Memory**: 512MB per function
- **Timeout**: 30 seconds

### **Frontend Performance**
- **Initial Load**: < 2 seconds
- **API Response**: < 500ms average
- **Interactive Time**: < 1 second

### **Rate Limiting**
- **Normal Rate**: 100 requests/second
- **Burst Capacity**: 200 requests/second
- **Daily Quota**: 10,000 requests/day
- **Throttling**: Automatic with HTTP 429 responses

## 🤝 Contributing

### **Adding New Endpoints**
1. Create new handler in `api/`
2. Add function definition to `serverless.yml` with `private: true`
3. Update frontend to include API key in requests
4. Test and deploy

### **Frontend Changes**
1. Edit files in `frontend/`
2. Ensure API key is included in all requests
3. Run `./scripts/deploy.sh dev` to update S3
4. CloudFront cache automatically invalidated

### **Infrastructure Changes**
1. Edit `serverless.yml`
2. Deploy with `npx serverless deploy`
3. Update documentation

### **API Key Management**
- **Rotation**: Redeploy stack to generate new key
- **Retrieval**: Use CloudFormation outputs to get current key
- **Distribution**: Update frontend configuration after key changes

## 📋 Roadmap

- [ ] **Enhanced Authentication**: JWT-based authentication system
- [ ] **Real-time Updates**: WebSocket integration
- [ ] **Advanced Charts**: Data visualization
- [ ] **Bulk Operations**: Batch lead import/export
- [ ] **Activity Management**: Create/edit activities
- [ ] **Contact Method Settings**: Manage preferences
- [ ] **Spam Management**: Block/unblock users
- [ ] **Audit Logs**: Track all changes
- [ ] **API Key Rotation**: Automated key rotation
- [ ] **User Management**: Multiple API keys for different users
