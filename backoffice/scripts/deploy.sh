#!/bin/bash

# Backoffice Deployment Script
set -e

STAGE=${1:-dev}
echo "🐼 Deploying PandasDB CRM Backoffice - Stage: $STAGE"
echo "=================================================="

# Check if main stack exists
MAIN_STACK_NAME="pandasdb-crm-comm-$STAGE"
echo "📋 Checking if main stack exists: $MAIN_STACK_NAME"

aws cloudformation describe-stacks --stack-name $MAIN_STACK_NAME > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "❌ Main stack '$MAIN_STACK_NAME' not found!"
    echo "   Please deploy the main CRM stack first:"
    echo "   cd .. && npm run deploy:$STAGE"
    exit 1
fi

echo "✅ Main stack found, proceeding with backoffice deployment"

# Deploy backoffice infrastructure
echo ""
echo "🏗️ Deploying backoffice infrastructure..."
npx serverless deploy --stage $STAGE

# Get deployment outputs
echo ""
echo "📤 Getting deployment outputs..."
BACKOFFICE_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "pandasdb-crm-comm-backoffice-$STAGE" \
    --query 'Stacks[0].Outputs[?OutputKey==`BackofficeBucket`].OutputValue' \
    --output text)

BACKOFFICE_URL=$(aws cloudformation describe-stacks \
    --stack-name "pandasdb-crm-comm-backoffice-$STAGE" \
    --query 'Stacks[0].Outputs[?OutputKey==`BackofficeUrl`].OutputValue' \
    --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
    --stack-name "pandasdb-crm-comm-backoffice-$STAGE" \
    --query 'Stacks[0].Outputs[?OutputKey==`BackofficeDistributionId`].OutputValue' \
    --output text)

API_URL=$(aws cloudformation describe-stacks \
    --stack-name "pandasdb-crm-comm-$STAGE" \
    --query 'Stacks[0].Outputs[?OutputKey==`BackofficeApiUrl`].OutputValue' \
    --output text)

echo "📁 S3 Bucket: $BACKOFFICE_BUCKET"
echo "🌍 Backoffice URL: $BACKOFFICE_URL"
echo "🔗 API URL: $API_URL"

# Update frontend config with API URL
echo ""
echo "⚙️ Updating frontend configuration..."
sed -i.bak "s|https://your-api-gateway-id.execute-api.us-east-1.amazonaws.com/dev|$API_URL|g" frontend/script.js
rm frontend/script.js.bak 2>/dev/null || true

# Deploy frontend files
echo ""
echo "📁 Deploying frontend files to S3..."
aws s3 sync frontend/ s3://$BACKOFFICE_BUCKET --delete

# Invalidate CloudFront cache
echo ""
echo "🔄 Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
    --distribution-id $DISTRIBUTION_ID \
    --paths "/*" > /dev/null

echo ""
echo "🎉 Backoffice deployment completed successfully!"
echo "=============================================="
echo ""
echo "📋 Access Information:"
echo "🌍 Backoffice URL: $BACKOFFICE_URL"
echo "🔗 API Endpoint: $API_URL"
echo ""
echo "📊 Features Available:"
echo "• Dashboard analytics and statistics"
echo "• Lead lookup and conversation history"  
echo "• Spam monitoring and user management"
echo "• System health and performance metrics"
echo ""
echo "⏰ Note: CloudFront may take 5-15 minutes to fully propagate changes."

# Restore original script.js
echo ""
echo "🔄 Restoring original frontend configuration..."
git checkout frontend/script.js 2>/dev/null || echo "⚠️ Could not restore script.js (not in git repo)"

echo ""
echo "✨ Backoffice deployment script completed!"
