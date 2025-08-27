import os
import re
import json
import time
import uuid
import boto3
from datetime import datetime, timezone

# --- env ---
TABLE_NAME     = os.environ["TABLE_NAME"]           # e.g., Leads
SES_FROM       = os.environ["SES_FROM"]             # verified SES sender (you@domain or your inbox)
SES_OWNER_TO   = os.getenv("SES_OWNER_TO", SES_FROM)  # who gets notifications (comma-separated ok)
ALLOWED_ORIGINS = {o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()}
TTL_DAYS       = int(os.getenv("TTL_DAYS", "0"))    # optional DynamoDB TTL in days (0 = disabled)

AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)
ses = boto3.client("ses", region_name=AWS_REGION)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def _cors_headers(origin: str | None):
    # Return CORS headers only if origin is explicitly allowed
    if origin and (origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS):
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
            "Vary": "Origin",
        }
    # Safe default: no CORS (client will see a CORS error if origin not allowed)
    return {"Vary": "Origin"}

def _ok(body: dict, origin: str | None):
    return {
        "statusCode": 200,
        "headers": _cors_headers(origin) | {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }

def _bad_request(message: str, origin: str | None):
    return {
        "statusCode": 400,
        "headers": _cors_headers(origin) | {"Content-Type": "application/json"},
        "body": json.dumps({"message": message}),
    }

def _error(message: str, origin: str | None):
    return {
        "statusCode": 500,
        "headers": _cors_headers(origin) | {"Content-Type": "application/json"},
        "body": json.dumps({"message": message}),
    }

def _parse_body(event):
    if "body" not in event or event["body"] is None:
        return {}
    if event.get("isBase64Encoded"):
        import base64
        raw = base64.b64decode(event["body"] or b"").decode("utf-8", errors="replace")
    else:
        raw = event["body"]
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}

def _get_origin(event):
    hdrs = event.get("headers") or {}
    # headers can differ in casing with HTTP API
    return hdrs.get("origin") or hdrs.get("Origin")

def _client_ip(event):
    try:
        return event["requestContext"]["http"]["sourceIp"]
    except Exception:
        # Fallback to X-Forwarded-For
        hdrs = event.get("headers") or {}
        xff = hdrs.get("x-forwarded-for") or hdrs.get("X-Forwarded-For")
        return xff.split(",")[0].strip() if xff else None

def _validate(name: str, email: str, message: str):
    if not name or len(name.strip()) < 2:
        return "Please provide your full name."
    if not email or not EMAIL_RE.match(email):
        return "Please provide a valid email address."
    if not message or len(message.strip()) < 10:
        return "Please provide a bit more detail (≥ 10 characters)."
    return None

def _send_emails(visitor_email: str, name: str, msg: str, lead_id: str):
    # Confirmation to the visitor
    ses.send_email(
        Source=SES_FROM,
        Destination={"ToAddresses": [visitor_email]},
        Message={
            "Subject": {"Data": "Thanks — we received your inquiry"},
            "Body": {
                "Text": {"Data": f"Hi {name},\n\nThanks for reaching out! We received your message.\n\nRef: {lead_id}\n"},
                "Html": {"Data": f"<p>Hi {name},</p><p>Thanks for reaching out! We received your message.</p><p><b>Ref:</b> {lead_id}</p>"},
            },
        },
    )
    # Notification to owner(s)
    owners = [e.strip() for e in SES_OWNER_TO.split(",") if e.strip()]
    if owners:
        ses.send_email(
            Source=SES_FROM,
            Destination={"ToAddresses": owners},
            Message={
                "Subject": {"Data": f"[Lead] {name} <{visitor_email}>"},
                "Body": {
                    "Text": {"Data": f"LeadID: {lead_id}\nFrom: {name} <{visitor_email}>\n\nMessage:\n{msg}\n"},
                    "Html": {"Data": f"<p><b>LeadID:</b> {lead_id}</p><p><b>From:</b> {name} &lt;{visitor_email}&gt;</p><p><b>Message</b>:</p><pre>{msg}</pre>"},
                },
            },
        )

def lambda_handler(event, context):
    # Handle OPTIONS quickly (if not using API Gateway managed CORS)
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(_get_origin(event))}

    origin = _get_origin(event)
    body = _parse_body(event)

    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip()
    message = (body.get("message") or "").strip()
    utm = body.get("utm") or {}
    user_agent = body.get("userAgent") or (event.get("headers") or {}).get("user-agent")
    referer = body.get("referer") or (event.get("headers") or {}).get("referer") or (event.get("headers") or {}).get("Referer")
    ip = _client_ip(event)

    err = _validate(name, email, message)
    if err:
        return _bad_request(err, origin)

    now = datetime.now(timezone.utc)
    lead_id = str(uuid.uuid4())
    item = {
        "id": lead_id,
        "name": name,
        "email": email,
        "message": message,
        "ts": int(now.timestamp()),
        "ts_iso": now.isoformat(),
        "ip": ip,
        "userAgent": user_agent,
        "referer": referer,
        "utm": utm,
    }
    if TTL_DAYS > 0:
        item["ttl"] = int(time.time()) + (TTL_DAYS * 86400)

    try:
        table.put_item(Item=item)
        _send_emails(email, name, message, lead_id)
        return _ok({"status": "ok", "id": lead_id}, origin)
    except Exception as e:
        # Logged in CloudWatch automatically via Lambda service; print() adds context
        print(f"ERROR saving/sending: {e}")
        return _error("Internal error. Please try again later.", origin)
