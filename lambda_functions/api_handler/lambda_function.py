"""
ApiHandlerLambda
Sits behind API Gateway (HTTP API, single ANY /{proxy+} route) and handles
all app business logic: signup/login, listing & fetching stories, generating
S3 presigned upload URLs, accepting pasted story text, and polling SQS for
"story is ready" notifications.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

BUCKET_NAME = os.environ["BUCKET_NAME"]
USERS_TABLE = os.environ["USERS_TABLE"]
STORIES_TABLE = os.environ["STORIES_TABLE"]
SQS_QUEUE_URL = os.environ["SQS_QUEUE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]

users_table = dynamodb.Table(USERS_TABLE)
stories_table = dynamodb.Table(STORIES_TABLE)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


class AuthError(Exception):
    pass


def response(status, body):
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body, default=str)}


def lambda_handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath", "/")
    qs = event.get("queryStringParameters") or {}
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    if method == "OPTIONS":
        return response(200, {"ok": True})

    body = {}
    if event.get("body"):
        raw = event["body"]
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {}

    try:
        if path == "/signup" and method == "POST":
            return handle_signup(body)
        if path == "/login" and method == "POST":
            return handle_login(body)
        if path == "/stories" and method == "GET":
            return handle_list_stories(qs)
        if path == "/stories/upload-url" and method == "POST":
            return handle_upload_url(body, headers)
        if path == "/stories/paste" and method == "POST":
            return handle_paste_story(body, headers)
        if path.startswith("/stories/") and method == "GET":
            story_id = path.rsplit("/", 1)[-1]
            return handle_get_story(story_id)
        if path == "/notifications" and method == "GET":
            return handle_notifications(headers)

        return response(404, {"error": "Not found"})
    except AuthError as exc:
        return response(401, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Unhandled exception: {exc}")
        return response(500, {"error": "Internal server error"})


def get_s3_client():
    region = os.environ.get("AWS_REGION", "ap-south-1")
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4")
    )

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def hash_password(password, salt=None):
    if salt is None:
        salt = base64.b64encode(os.urandom(16)).decode()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${base64.b64encode(digest).decode()}"


def verify_password(password, stored):
    try:
        salt, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def make_token(username, role):
    expiry = int(time.time()) + 60 * 60 * 12  # 12 hour session
    payload = f"{username}:{role}:{expiry}"
    sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def verify_token(token):
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        username, role, expiry, sig = decoded.split(":")
        payload = f"{username}:{role}:{expiry}"
        expected_sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise AuthError("Invalid token")
        if int(expiry) < int(time.time()):
            raise AuthError("Session expired, please log in again")
        return username, role
    except AuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Invalid token") from exc


def require_auth(headers, role_required=None):
    auth_header = headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthError("Missing authorization token")
    username, role = verify_token(auth_header[7:])
    if role_required and role != role_required:
        raise AuthError(f"{role_required.capitalize()} access required")
    return username, role


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def handle_signup(body):
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    role = body.get("role")
    name = (body.get("name") or username).strip()

    if not username or not password or role not in ("teacher", "student"):
        return response(400, {"error": "Username, password, and a valid role are required"})
    if len(password) < 4:
        return response(400, {"error": "Password must be at least 4 characters"})

    if users_table.get_item(Key={"username": username}).get("Item"):
        return response(409, {"error": "That username is already taken"})

    users_table.put_item(
        Item={
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    token = make_token(username, role)
    return response(201, {"token": token, "username": username, "role": role, "name": name})


def handle_login(body):
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    role = body.get("role")

    item = users_table.get_item(Key={"username": username}).get("Item")
    if not item or item.get("role") != role or not verify_password(password, item.get("password_hash", "")):
        return response(401, {"error": "Invalid username, password, or role"})

    token = make_token(username, role)
    return response(200, {"token": token, "username": username, "role": role, "name": item.get("name", username)})


def handle_list_stories(qs):
    teacher = (qs or {}).get("teacher")
    items = stories_table.scan().get("Items", [])

    if teacher:
        items = [i for i in items if i.get("teacher_username") == teacher]
    else:
        items = [i for i in items if i.get("status") == "ready"]

    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    slim = [
        {
            "story_id": i["story_id"],
            "title": i.get("title"),
            "teacher_username": i.get("teacher_username"),
            "status": i.get("status"),
            "created_at": i.get("created_at"),
        }
        for i in items
    ]
    return response(200, {"stories": slim})


def handle_get_story(story_id):
    item = stories_table.get_item(Key={"story_id": story_id}).get("Item")
    if not item:
        return response(404, {"error": "Story not found"})

    result = {
        "story_id": story_id,
        "title": item.get("title"),
        "status": item.get("status"),
        "teacher_username": item.get("teacher_username"),
        "created_at": item.get("created_at"),
    }

    if item.get("status") == "ready":
        s3 = get_s3_client()
        text_obj = s3.get_object(Bucket=BUCKET_NAME, Key=item["text_key"])
        result["text"] = text_obj["Body"].read().decode("utf-8")
        result["audio_url"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": item["audio_key"]},
            ExpiresIn=3600,
        )
    elif item.get("status") == "error":
        result["error_message"] = item.get("error_message", "Something went wrong processing this story.")

    return response(200, result)


def handle_upload_url(body, headers):
    username, _ = require_auth(headers, role_required="teacher")
    title = (body.get("title") or "").strip()
    if not title:
        return response(400, {"error": "Title is required"})

    story_id = str(uuid.uuid4())
    text_key = f"stories/{story_id}.txt"

    stories_table.put_item(
        Item={
            "story_id": story_id,
            "title": title,
            "teacher_username": username,
            "text_key": text_key,
            "audio_key": "",
            "status": "processing",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    s3 = get_s3_client()
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET_NAME, "Key": text_key, "ContentType": "text/plain"},
        ExpiresIn=300,
    )

    return response(200, {"story_id": story_id, "upload_url": upload_url})


def handle_paste_story(body, headers):
    username, _ = require_auth(headers, role_required="teacher")
    title = (body.get("title") or "").strip()
    text = (body.get("text") or "").strip()

    if not title or not text:
        return response(400, {"error": "Title and story text are required"})

    story_id = str(uuid.uuid4())
    text_key = f"stories/{story_id}.txt"

    stories_table.put_item(
        Item={
            "story_id": story_id,
            "title": title,
            "teacher_username": username,
            "text_key": text_key,
            "audio_key": "",
            "status": "processing",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Writing this object triggers ProcessStoryLambda via the S3 event notification
    s3 = get_s3_client()
    s3.put_object(Bucket=BUCKET_NAME, Key=text_key, Body=text.encode("utf-8"), ContentType="text/plain")

    return response(201, {"story_id": story_id})


def handle_notifications(headers):
    username, _ = require_auth(headers, role_required="teacher")

    messages = sqs.receive_message(
        QueueUrl=SQS_QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=1,
    ).get("Messages", [])

    results = []
    for m in messages:
        try:
            payload = json.loads(m["Body"])
        except Exception:  # noqa: BLE001
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
            continue

        if payload.get("teacher_username") == username:
            results.append(payload)
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
        # Messages for other teachers are left on the queue to become visible
        # again after the visibility timeout, so they aren't lost.

    return response(200, {"notifications": results})
