# Snap & Cook — AI-Powered Recipe Generator

Upload a photo of ingredients. Get step-by-step recipes in seconds.

Snap & Cook uses Amazon Rekognition to detect ingredients in your photo, lets you verify and edit the list, then calls Amazon Bedrock (Nova Lite) to generate custom recipes based on your prep-time and dietary preferences. The entire backend is serverless and deployed via Terraform.

---

## Architecture

```
Browser / S3 Static Frontend
        │
        ▼
POST /analyze  ──────────────────────────────────────────────────────────┐
  API Gateway (HTTP API v2, throttled 100 rps / 200 burst)              │
        │                                                                │
        ▼                                                                │
Lambda: ingest_handler                                                   │
  • Parses multipart/form-data, stores raw image → S3 (images bucket)   │
  • Writes DynamoDB: { requestId, status: PROCESSING }                  │
  • Publishes SQS: { requestId, s3_key, phase: "detect" }               │
  • Returns 202 { requestId }  ───────────────────────────────────────► │
                                                                         │
SQS Job Queue ──► Lambda: processor_handler (phase = detect)            │
  • Fetches image from S3                                                │
  • Rekognition DetectLabels → filters food labels                      │
  • DynamoDB: status = AWAITING_CONFIRMATION, ingredients = [...]        │
                                                                         │
Frontend polls GET /recipes/{id}                                         │
  • Shows ingredient verification UI (add / remove labels)              │
  • User sets preferences: recipe count (1–5), max prep time, dietary   │
                                                                         │
POST /recipes/{id}/confirm                                               │
  • Lambda: confirm_handler                                              │
  • DynamoDB: status = GENERATING, confirmed_ingredients, preferences   │
  • Publishes SQS: { requestId, phase: "generate" }                     │
                                                                         │
SQS Job Queue ──► Lambda: processor_handler (phase = generate)          │
  • Reads confirmed_ingredients + preferences from DynamoDB             │
  • Bedrock Nova Lite → generates N recipes with instructions           │
  • DynamoDB: status = COMPLETE, recipes = [...]                         │
                                                                         │
Frontend polls GET /recipes/{id}                                         │
  • Renders recipe cards (name, ingredients, numbered steps, time badge)│
  • Shareable link via ?id= query parameter                             │
```

### Status flow

```
PROCESSING → AWAITING_CONFIRMATION → GENERATING → COMPLETE | FAILED
```

### AWS services

| Service | Role |
|---|---|
| API Gateway (HTTP v2) | POST /analyze, GET /recipes/{id}, POST /recipes/{id}/confirm |
| Lambda (×4) | ingest, processor, query, confirm |
| S3 (×2) | uploaded images (private) + static frontend (public) |
| SQS + DLQ | async job queue — decouples ingest from ML processing |
| Rekognition | food label detection |
| Bedrock (Nova Lite) | recipe generation |
| DynamoDB | request results (on-demand, TTL 7 days) |
| CloudWatch | Lambda/API logs, metric alarms |
| SNS | alarm notification topic |

---

## Repository layout

```
.
├── .github/workflows/deploy.yml   # CI/CD — lint → test → tf-plan → tf-apply
├── infra/
│   ├── bootstrap/                 # One-time: S3 state bucket + DynamoDB lock table
│   ├── modules/
│   │   ├── api/                   # API Gateway HTTP API + routes + CORS + throttle
│   │   ├── frontend/              # S3 static site bucket + website config + upload script
│   │   ├── lambdas/               # ingest, processor, query, confirm — IAM + zip packaging
│   │   ├── messaging/             # SQS job queue + DLQ + redrive policy
│   │   ├── monitoring/            # CloudWatch alarms + SNS topic
│   │   └── storage/               # S3 image bucket + DynamoDB results table
│   ├── main.tf                    # Root module — wires all modules together
│   ├── variables.tf
│   ├── outputs.tf
│   └── versions.tf                # Terraform + provider pins + S3 backend config
├── lambdas/
│   ├── confirm/handler.py
│   ├── ingest/handler.py
│   ├── processor/handler.py
│   └── query/handler.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── tests/
    ├── unit/                      # Moto-mocked unit tests (no real AWS calls)
    ├── fixtures/                  # Food photo fixtures for integration testing
    └── requirements-dev.txt
```

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Terraform | ≥ 1.6 | `brew install terraform` |
| Python | 3.12 | `brew install python@3.12` |
| AWS CLI | v2 | [docs.aws.amazon.com/cli](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| ruff (optional) | latest | `pip install ruff` |

**AWS prerequisites:**

1. An AWS account with programmatic credentials configured (`aws configure`).
2. Bedrock model access enabled — AWS Console → Bedrock → Model access → enable **Amazon Nova Lite** (`amazon.nova-lite-v1:0`). Access is usually instant on personal accounts.

---

## Deployment

### Step 1 — Bootstrap Terraform state (one-time only)

```bash
cd infra/bootstrap
terraform init
terraform apply
# Note the outputs: tfstate_bucket and tflock_table
```

This creates the S3 bucket and DynamoDB table that store Terraform state for the main stack.

### Step 2 — Deploy the main stack

```bash
cd infra
terraform init
terraform apply
```

After apply, Terraform prints the key outputs:

```
api_endpoint  = "https://<id>.execute-api.us-east-1.amazonaws.com"
website_url   = "http://snap-and-cook-frontend-<account>.s3-website-us-east-1.amazonaws.com"
```

### Step 3 — Upload the frontend

The frontend references the API endpoint at runtime. The frontend module's `null_resource` (or manual step below) uploads and sets the correct `API_BASE_URL`:

```bash
# Retrieve outputs
API_URL=$(cd infra && terraform output -raw api_endpoint)
BUCKET=$(cd infra && terraform output -raw image_bucket_name)   # frontend bucket name varies

# Upload frontend files to the S3 frontend bucket
aws s3 sync frontend/ s3://snap-and-cook-frontend-<account-id>/ \
  --content-type "text/html" --exclude "*" --include "*.html"
aws s3 sync frontend/ s3://snap-and-cook-frontend-<account-id>/ \
  --content-type "application/javascript" --exclude "*" --include "*.js"
aws s3 sync frontend/ s3://snap-and-cook-frontend-<account-id>/ \
  --content-type "text/css" --exclude "*" --include "*.css"
```

> The frontend stores the API URL in `localStorage` via the settings gear icon (top-right corner). Open the site, click the gear, paste the `api_endpoint` URL, and save.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `aws_region` | `us-east-1` | AWS region for all resources |
| `project_name` | `snap-and-cook` | Prefix used for all resource names |
| `bedrock_model_id` | `amazon.nova-lite-v1:0` | Bedrock model for recipe generation |
| `alarm_email` | `""` | Email to subscribe to CloudWatch alarms (leave empty to skip) |

Set via `terraform.tfvars` or `-var` flags:

```hcl
# infra/terraform.tfvars  (do not commit secrets)
alarm_email = "you@example.com"
```

---

## CI/CD

The `.github/workflows/deploy.yml` pipeline runs automatically:

| Trigger | Jobs |
|---|---|
| Pull request to `main` | lint + test + terraform plan (plan posted as PR comment) |
| Push to `main` | lint + test + terraform plan + **terraform apply** |

**Required GitHub secrets** (Settings → Secrets → Actions):

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

**Optional**: create a `production` GitHub environment with a required reviewer to gate `terraform apply`.

---

## Testing

### Unit tests (no AWS credentials required)

```bash
pip install -r tests/requirements-dev.txt
pytest tests/unit/ -v --tb=short
```

### End-to-end API test (requires deployed stack)

```bash
API=<paste api_endpoint from terraform output>

# 1. Upload a food photo
REQUEST_ID=$(curl -s -X POST "$API/analyze" \
  -F "image=@tests/fixtures/food.jpg" \
  | jq -r '.requestId')

echo "requestId: $REQUEST_ID"

# 2. Poll until AWAITING_CONFIRMATION (Rekognition usually finishes in 3–8 s)
while true; do
  STATUS=$(curl -s "$API/recipes/$REQUEST_ID" | jq -r '.status')
  echo "status: $STATUS"
  [ "$STATUS" = "AWAITING_CONFIRMATION" ] && break
  [ "$STATUS" = "FAILED" ] && echo "ERROR" && break
  sleep 2
done

# 3. Confirm ingredients and set preferences
curl -s -X POST "$API/recipes/$REQUEST_ID/confirm" \
  -H "Content-Type: application/json" \
  -d '{
    "confirmed_ingredients": ["tomato", "onion", "garlic"],
    "preferences": { "recipe_count": 2, "max_prep_time": 30, "dietary": [] }
  }' | jq .

# 4. Poll until COMPLETE (Bedrock usually finishes in 5–15 s)
while true; do
  RESP=$(curl -s "$API/recipes/$REQUEST_ID")
  STATUS=$(echo "$RESP" | jq -r '.status')
  echo "status: $STATUS"
  [ "$STATUS" = "COMPLETE" ] && echo "$RESP" | jq '.recipes[].name' && break
  [ "$STATUS" = "FAILED" ] && echo "ERROR" && break
  sleep 3
done
```

### Browser test

1. Open `website_url` from Terraform output.
2. Click the gear icon → paste `api_endpoint` → Save.
3. Upload a food photo and click **Snap & Cook**.
4. Review detected ingredients, adjust if needed, set preferences, confirm.
5. Wait for recipe cards to appear.
6. Copy the URL — the `?id=` parameter makes it shareable.

---

## Monitoring

CloudWatch alarms are provisioned in `infra/modules/monitoring/`:

| Alarm | Condition |
|---|---|
| `snap-and-cook-ingest-errors` | ≥ 1 Lambda error per minute |
| `snap-and-cook-processor-errors` | ≥ 1 Lambda error per minute |
| `snap-and-cook-query-errors` | ≥ 1 Lambda error per minute |
| `snap-and-cook-confirm-errors` | ≥ 1 Lambda error per minute |
| `snap-and-cook-dlq-depth` | ≥ 1 message in the dead-letter queue |
| `snap-and-cook-processor-duration` | p95 duration ≥ 110 s (≈ 92% of timeout) |
| `snap-and-cook-processor-throttles` | Any concurrency throttle event |

All alarms publish to the `snap-and-cook-alarms` SNS topic. Set `alarm_email` in `terraform.tfvars` to receive email notifications.

**View logs:**

```bash
# Ingest Lambda logs (last 30 min)
aws logs tail /aws/lambda/snap-and-cook-ingest --since 30m --follow

# Processor Lambda logs
aws logs tail /aws/lambda/snap-and-cook-processor --since 30m --follow

# API Gateway access logs
aws logs tail /aws/apigateway/snap-and-cook-api --since 30m --follow
```

---

## Teardown

```bash
cd infra
terraform destroy
```

> The bootstrap stack (S3 state bucket + DynamoDB lock) is intentionally not destroyed by this command — it holds the Terraform state. To remove it, empty the S3 bucket first, then run `terraform destroy` inside `infra/bootstrap/`.

---

## Well-Architected alignment

| Pillar | Implementation |
|---|---|
| **Operational Excellence** | CloudWatch alarms, structured JSON logging, CI/CD on every merge |
| **Security** | IAM least-privilege per Lambda, S3 public-access block + AES-256, API Gateway throttling (100 rps / 200 burst) |
| **Reliability** | SQS DLQ (max 3 retries), Lambda auto-retry, DynamoDB on-demand (no throttle), DLQ depth alarm |
| **Performance Efficiency** | Async SQS decoupling avoids API Gateway 29 s timeout; Lambda auto-scaling |
| **Cost Optimization** | Serverless pay-per-use, DynamoDB on-demand, S3 image TTL (7 days), no idle compute |
| **Sustainability** | Zero idle compute, right-sized Lambda memory (256–512 MB) |
