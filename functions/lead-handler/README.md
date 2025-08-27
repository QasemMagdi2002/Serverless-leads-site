# lead-handler (AWS Lambda)

Handles POST /lead from API Gateway (HTTP API). Validates input, writes to DynamoDB, and sends emails via SES.

## Environment variables
- `TABLE_NAME` (e.g., `Leads`)
- `SES_FROM` (verified address in SES, same region)
- `SES_OWNER_TO` (comma-separated list; defaults to `SES_FROM`)
- `ALLOWED_ORIGINS` (e.g., `https://dxxxx.cloudfront.net,http://localhost:5500`)
- `TTL_DAYS` (optional; e.g., `180` to auto-expire items after ~6 months)

## Expected API Gateway config (HTTP API)
- **Integration:** Lambda proxy (payload v2.0)
- **Route:** `POST /lead`
- **CORS:** Allow your CloudFront origin and `Content-Type` header  
  (You can also rely on the Lambda to return CORS headers; API-managed CORS is simpler.)

## DynamoDB table
- Name: `Leads`
- Partition key: `id` (String)  
- (Optional) TTL attribute: `ttl` (Number)

## SES
- Verify `SES_FROM` (and your test recipient if your account is in SES sandbox).
- Region should be the same as Lambda (eu-central-1).

## Test event (HTTP API v2)
{
"version":"2.0",
"routeKey":"POST /lead",
"rawPath":"/lead",
"headers":{"content-type":"application/json","origin":"https://dxxxx.cloudfront.net","user-agent":"curl/8.0"}
,
"requestContext":{"http":{"method":"POST","sourceIp":"1.2.3.4"}},
"body":"{"name":"Jane","email":"jane@example.com
","message":"Hello!","utm":{"utm_source":"linkedin"}}",
"isBase64Encoded":false
}