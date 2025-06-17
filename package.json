# PandasDB CRM Communication System

A serverless WhatsApp bot for lead generation and sales automation using AWS Lambda, Step Functions, DynamoDB, and Bedrock AI.

## 🏗️ Architecture

```
Twilio Webhook → API Gateway → Step Functions → Lambda Functions → DynamoDB
                                     ↓
                               Bedrock AI (Spam Detection + Sales Agent)
                                     ↓
                               S3 Knowledge Base
```

## 🚀 Features

- **Spam Detection**: AI-powered spam filtering using AWS Bedrock
- **Lead Management**: Automatic lead creation and tracking in DynamoDB
- **Conversation History**: Maintains context across interactions
- **Sales Automation**: AI sales agent with product knowledge
- **Scalable Architecture**: Serverless with automatic scaling

## 📁 Project Structure

```
pandasdb-crm-comm/
├── src/
│   └── handlers/
│       ├── webhook_handler.py
│       ├── check_content.py
│       ├── check_phone_spammer.py
│       ├── spam_detection.py
│       ├── handle_spam.py
│       └── handle_normal_message.py
├── database/
│   └── dynamodb_schema.yml
├── knowledge/
│   └── system_prompt.txt
├── serverless.yml
├── requirements.txt
├── package.json
├── .env.example
└── README.md
```

## 🛠️ Setup & Deployment

### Prerequisites

- Node.js 18+ and npm
- Python 3.9+
- AWS CLI configured
- Twilio account

### 1. Clone and Install

```bash
git clone <your-repo>
cd pandasdb-crm-comm
npm install
```

### 2. Environment Configuration

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required environment variables:
- `TWILIO_ACCOUNT_SID`: Twilio Account SID
- `TWILIO_AUTH_TOKEN`: Twilio Auth Token

### 3. Database Setup

DynamoDB tables are automatically created during deployment via CloudFormation.

### 4. Deploy Infrastructure

```bash
# Deploy to development
npm run deploy:dev

# Deploy to production
npm run deploy:prod
```

### 5. Upload Knowledge Base

```bash
# Upload system prompt to S3
npm run upload-knowledge
```

### 6. Configure Twilio Webhook

1. Get your webhook URL from the deployment output
2. Set it in Twilio Console: `https://your-api-id.execute-api.region.amazonaws.com/dev/webhook/whatsapp`

## 💰 Cost Estimation

### Monthly Cost Breakdown by Message Volume

| Messages/Month | Users | AWS Services | Twilio WhatsApp | Total Cost | Cost/User | Cost/Message |
|---------------|-------|--------------|-----------------|------------|-----------|--------------|
| 1K | 200 | $1.95 | $4.68 | **$6.63** | $0.033 | $0.0066 |
| 10K | 2K | $7.81 | $46.75 | **$54.56** | $0.027 | $0.0055 |
| 100K | 20K | $52.15 | $467.50 | **$519.65** | $0.026 | $0.0052 |
| 1M | 200K | $485.20 | $4,675.00 | **$5,160.20** | $0.026 | $0.0052 |

### AWS Services Breakdown (10K messages example)

| Service | Monthly Cost | Usage |
|---------|-------------|--------|
| **Lambda** | $0.86 | 40K invocations, 2.5s avg execution |
| **Step Functions** | $1.50 | 60K state transitions |
| **Bedrock AI** | $2.91 | Spam detection + AI responses |
| **DynamoDB** | $2.20 | Read/write operations + storage |
| **API Gateway** | $0.03 | 10K webhook requests |
| **S3 Storage** | $0.003 | Knowledge base storage |
| **CloudWatch** | $0.31 | Logging and monitoring |

### Key Cost Factors

- **Twilio WhatsApp**: $0.0055 per outbound message (85% of total cost)
- **Bedrock AI**: $0.00025-$0.00125 per 1K tokens (varies by model)
- **DynamoDB**: ~$0.22 per 10K messages (reads/writes)
- **Lambda**: Very low cost due to efficient execution times

### Cost Optimization Tips

1. **Reduce Twilio costs**: Use message templates, batch notifications
2. **Optimize AI prompts**: Shorter prompts = lower Bedrock costs  
3. **Cache responses**: Store common answers to reduce AI calls
4. **Monitor usage**: Set up CloudWatch alarms for cost thresholds

### Scaling Economics

- **Under 10K messages**: Fixed infrastructure costs dominate
- **10K-100K messages**: Linear scaling with good efficiency  
- **100K+ messages**: Excellent cost per message due to economies of scale
- **1M+ messages**: Consider reserved capacity for additional savings

*Note: Costs based on AWS US-East-1 pricing as of 2025. Actual costs may vary by region and usage patterns.*

## 🔧 Configuration

### DynamoDB Setup

DynamoDB tables are created automatically during deployment with the following structure:

### AWS Bedrock Access

Ensure your AWS account has access to:
- `anthropic.claude-3-haiku-20240307-v1:0`
- `anthropic.claude-3-sonnet-20240229-v1:0`

### Twilio WhatsApp Setup

1. Set up Twilio WhatsApp sandbox or approved number
2. Configure webhook URL pointing to your API Gateway endpoint
3. Test with sample messages

## 📊 Database Schema

The project uses the following DynamoDB tables:

- **leads**: Core lead information
- **contact_methods**: Phone numbers, emails, etc.
- **contact_method_settings**: Contact preferences
- **activities**: All interactions (WhatsApp, calls, etc.)
- **activity_content**: Message content and responses
- **spam_activities**: Spam detection results

## 🔄 Message Flow

1. **Webhook Receives Message** → Validates content
2. **Phone Check** → Creates lead if new, checks spammer status
3. **Spam Detection** → AI analysis using Bedrock
4. **Message Processing**:
   - **If Spam**: Store spam record, send warning/block
   - **If Normal**: Generate AI response, store conversation
5. **Response** → Send WhatsApp message via Twilio

## 🧠 AI Components

### Spam Detection
- Uses Claude Haiku for fast, cost-effective spam analysis
- Considers message patterns, content quality, and context
- Automatic blocking after 5 spam messages

### Sales Agent
- Powered by Claude with company knowledge base
- Maintains conversation history for context
- Focuses on lead qualification and meeting scheduling
- Loads system prompt from S3 for easy updates

## 📈 Monitoring

### CloudWatch Metrics
- Lambda execution times and errors
- Step Functions execution status
- API Gateway request metrics

### Logging
- Structured logging in all Lambda functions
- Message processing traceability
- Error tracking and debugging

## 🔐 Security

- **Environment Variables**: Stored in AWS Systems Manager
- **Database Access**: Supabase RLS and API keys
- **API Security**: AWS IAM roles and policies
- **Message Encryption**: In transit and at rest

## 💰 Cost Optimization

- **Lambda**: Pay per execution, optimized memory allocation
- **Step Functions**: Minimal state machine transitions
- **Bedrock**: Efficient model selection (Haiku for spam, Sonnet for complex tasks)
- **S3**: Standard storage for knowledge base

## 🚨 Troubleshooting

### Common Issues

1. **Webhook not receiving messages**
   - Check Twilio webhook URL configuration
   - Verify API Gateway deployment

2. **Database connection errors**
   - Check AWS credentials and permissions
   - Verify DynamoDB table names

3. **Bedrock access denied**
   - Ensure model access is enabled in AWS console
   - Check IAM permissions

4. **Step Functions failures**
   - Review CloudWatch logs for specific Lambda errors
   - Check input/output format between functions

### Debug Commands

```bash
# View logs
npm run logs webhook-handler
npm run logs check-content

# Test individual functions
npm run invoke webhook-handler --data '{"body": "test"}'

# Check Step Functions execution
aws stepfunctions list-executions --state-machine-arn <your-state-machine-arn>
```

## 📝 Development

### Adding New Features

1. Create new Lambda function in `src/handlers/`
2. Update `serverless.yml` with function definition
3. Add to Step Functions state machine if needed
4. Update database schema if required

### Testing

```bash
# Local testing (requires additional setup)
serverless invoke local -f checkContent --data '{"body": {"Body": "test message"}}'
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.

## 🔗 Links

- [Supabase Documentation](https://supabase.com/docs)
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Twilio WhatsApp API](https://www.twilio.com/docs/whatsapp)
- [Serverless Framework](https://www.serverless.com/framework/docs/)
