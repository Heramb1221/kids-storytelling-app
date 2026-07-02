"""
Provisions every AWS resource the Kids Storytelling App needs, in ap-south-1:

  - S3 bucket            (stories/ and audio/ prefixes)
  - DynamoDB tables       Users, Stories
  - SNS topic             story-processed notifications
  - SQS queue             subscribed to the SNS topic
  - IAM role              shared by both Lambda functions
  - Lambda functions      ProcessStoryLambda, ApiHandlerLambda
  - S3 -> Lambda trigger  on stories/*.txt uploads
  - API Gateway HTTP API  fronting ApiHandlerLambda

Run once:   python setup/provision_aws.py
Tear down:  python setup/deprovision_aws.py

Writes ../aws_resources.json with everything the Flask app needs.
"""

import io
import json
import os
import secrets
import sys
import time
import zipfile

import boto3
from botocore.exceptions import ClientError

REGION = "ap-south-1"
PREFIX = "kidsstoryapp"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAMBDA_DIR = os.path.join(ROOT, "lambda_functions")
OUTPUT_FILE = os.path.join(ROOT, "aws_resources.json")

sts = boto3.client("sts", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
dynamodb = boto3.client("dynamodb", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
apigw = boto3.client("apigatewayv2", region_name=REGION)


def log(msg):
    print(f"[setup] {msg}", flush=True)


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------

def create_bucket(bucket_name):
    log(f"Creating S3 bucket: {bucket_name}")
    try:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou",):
            log("  bucket already exists (owned by you) - reusing it")
        else:
            raise

    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )

    s3.put_bucket_cors(
        Bucket=bucket_name,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": ["*"],
                    "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        },
    )
    return bucket_name


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------

def create_table(table_name, key_name):
    log(f"Creating DynamoDB table: {table_name}")
    try:
        dynamodb.create_table(
            TableName=table_name,
            AttributeDefinitions=[{"AttributeName": key_name, "AttributeType": "S"}],
            KeySchema=[{"AttributeName": key_name, "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            log("  table already exists - reusing it")
        else:
            raise
    dynamodb.get_waiter("table_exists").wait(TableName=table_name)
    return table_name


# ---------------------------------------------------------------------------
# SNS + SQS
# ---------------------------------------------------------------------------

def create_sns_topic(topic_name):
    log(f"Creating SNS topic: {topic_name}")
    resp = sns.create_topic(Name=topic_name)
    return resp["TopicArn"]


def create_sqs_queue(queue_name):
    log(f"Creating SQS queue: {queue_name}")
    resp = sqs.create_queue(QueueName=queue_name, Attributes={"VisibilityTimeout": "30"})
    queue_url = resp["QueueUrl"]
    attrs = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
    return queue_url, attrs["Attributes"]["QueueArn"]


def subscribe_queue_to_topic(topic_arn, queue_arn, queue_url):
    log("Subscribing SQS queue to SNS topic")
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowSNSPublish",
                "Effect": "Allow",
                "Principal": {"Service": "sns.amazonaws.com"},
                "Action": "sqs:SendMessage",
                "Resource": queue_arn,
                "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}},
            }
        ],
    }
    sqs.set_queue_attributes(QueueUrl=queue_url, Attributes={"Policy": json.dumps(policy)})
    sns.subscribe(
        TopicArn=topic_arn,
        Protocol="sqs",
        Endpoint=queue_arn,
        Attributes={"RawMessageDelivery": "true"},
    )


# ---------------------------------------------------------------------------
# IAM
# ---------------------------------------------------------------------------

def create_lambda_role(role_name, bucket_name, users_table, stories_table, topic_arn, queue_arn):
    log(f"Creating IAM role: {role_name}")
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }

    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for Kids Storytelling App Lambdas",
        )
        role_arn = resp["Role"]["Arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            log("  role already exists - reusing it")
            role_arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
        else:
            raise

    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )

    account_id = sts.get_caller_identity()["Account"]
    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3Access",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject"],
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
            },
            {
                "Sid": "DynamoDbAccess",
                "Effect": "Allow",
                "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Scan", "dynamodb:Query"],
                "Resource": [
                    f"arn:aws:dynamodb:{REGION}:{account_id}:table/{users_table}",
                    f"arn:aws:dynamodb:{REGION}:{account_id}:table/{stories_table}",
                ],
            },
            {
                "Sid": "PollyAccess",
                "Effect": "Allow",
                "Action": ["polly:SynthesizeSpeech"],
                "Resource": "*",
            },
            {
                "Sid": "SnsAccess",
                "Effect": "Allow",
                "Action": ["sns:Publish"],
                "Resource": topic_arn,
            },
            {
                "Sid": "SqsAccess",
                "Effect": "Allow",
                "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
                "Resource": queue_arn,
            },
        ],
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=f"{role_name}-inline-policy",
        PolicyDocument=json.dumps(inline_policy),
    )

    log("  waiting for IAM role to propagate...")
    time.sleep(10)
    return role_arn


# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------

def zip_lambda(function_dir):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(function_dir):
            if fname.endswith(".py"):
                zf.write(os.path.join(function_dir, fname), fname)
    buf.seek(0)
    return buf.read()


def create_or_update_lambda(function_name, function_dir, role_arn, env_vars, timeout=30, memory=256):
    log(f"Deploying Lambda function: {function_name}")
    zip_bytes = zip_lambda(function_dir)

    for attempt in range(5):
        try:
            lambda_client.create_function(
                FunctionName=function_name,
                Runtime="python3.12",
                Role=role_arn,
                Handler="lambda_function.lambda_handler",
                Code={"ZipFile": zip_bytes},
                Timeout=timeout,
                MemorySize=memory,
                Environment={"Variables": env_vars},
                Publish=True,
            )
            break
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ResourceConflictException":
                log("  function already exists - updating code and configuration")
                lambda_client.update_function_code(FunctionName=function_name, ZipFile=zip_bytes, Publish=True)
                waiter = lambda_client.get_waiter("function_updated")
                waiter.wait(FunctionName=function_name)
                lambda_client.update_function_configuration(
                    FunctionName=function_name,
                    Role=role_arn,
                    Timeout=timeout,
                    MemorySize=memory,
                    Environment={"Variables": env_vars},
                )
                break
            if code == "InvalidParameterValueException" and attempt < 4:
                log("  role not yet assumable, retrying in 5s...")
                time.sleep(5)
                continue
            raise

    waiter = lambda_client.get_waiter("function_active_v2")
    waiter.wait(FunctionName=function_name)
    resp = lambda_client.get_function(FunctionName=function_name)
    return resp["Configuration"]["FunctionArn"]


def add_s3_trigger(function_name, function_arn, bucket_name, account_id):
    log("Wiring S3 -> Lambda trigger for stories/*.txt uploads")
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId="AllowS3Invoke",
            Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com",
            SourceArn=f"arn:aws:s3:::{bucket_name}",
            SourceAccount=account_id,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceConflictException":
            raise

    s3.put_bucket_notification_configuration(
        Bucket=bucket_name,
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {
                    "LambdaFunctionArn": function_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {
                        "Key": {
                            "FilterRules": [
                                {"Name": "prefix", "Value": "stories/"},
                                {"Name": "suffix", "Value": ".txt"},
                            ]
                        }
                    },
                }
            ]
        },
    )


# ---------------------------------------------------------------------------
# API Gateway (HTTP API)
# ---------------------------------------------------------------------------

def create_http_api(api_name, lambda_arn, function_name, account_id):
    log(f"Creating API Gateway HTTP API: {api_name}")

    existing = apigw.get_apis().get("Items", [])
    api = next((a for a in existing if a["Name"] == api_name), None)
    if api:
        log("  API already exists - reusing it")
        api_id = api["ApiId"]
    else:
        resp = apigw.create_api(
            Name=api_name,
            ProtocolType="HTTP",
            CorsConfiguration={
                "AllowOrigins": ["*"],
                "AllowMethods": ["GET", "POST", "OPTIONS"],
                "AllowHeaders": ["Content-Type", "Authorization"],
                "MaxAge": 300,
            },
        )
        api_id = resp["ApiId"]

    integration = apigw.create_integration(
        ApiId=api_id,
        IntegrationType="AWS_PROXY",
        IntegrationUri=lambda_arn,
        PayloadFormatVersion="2.0",
        IntegrationMethod="POST",
    )
    integration_id = integration["IntegrationId"]
    target = f"integrations/{integration_id}"

    for route_key in ("ANY /{proxy+}", "ANY /"):
        try:
            apigw.create_route(ApiId=api_id, RouteKey=route_key, Target=target)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConflictException":
                raise

    try:
        apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConflictException":
            raise

    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId="AllowApiGatewayInvoke",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*/*",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceConflictException":
            raise

    api_endpoint = f"https://{api_id}.execute-api.{REGION}.amazonaws.com"
    return api_endpoint


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log(f"Starting provisioning in region {REGION}")
    account_id = sts.get_caller_identity()["Account"]

    bucket_name = f"{PREFIX}-{account_id}"
    users_table = "KidsStoryApp_Users"
    stories_table = "KidsStoryApp_Stories"
    topic_name = "KidsStoryApp-StoryProcessed"
    queue_name = "KidsStoryApp-StoryStatusQueue"
    role_name = "KidsStoryApp-LambdaExecutionRole"
    process_fn_name = "KidsStoryApp-ProcessStory"
    api_fn_name = "KidsStoryApp-ApiHandler"
    api_name = "KidsStoryApp-HttpApi"

    create_bucket(bucket_name)
    create_table(users_table, "username")
    create_table(stories_table, "story_id")

    topic_arn = create_sns_topic(topic_name)
    queue_url, queue_arn = create_sqs_queue(queue_name)
    subscribe_queue_to_topic(topic_arn, queue_arn, queue_url)

    role_arn = create_lambda_role(role_name, bucket_name, users_table, stories_table, topic_arn, queue_arn)

    jwt_secret = secrets.token_hex(32)

    process_fn_arn = create_or_update_lambda(
        process_fn_name,
        os.path.join(LAMBDA_DIR, "process_story"),
        role_arn,
        {"STORIES_TABLE": stories_table, "SNS_TOPIC_ARN": topic_arn, "POLLY_VOICE_ID": "Ivy"},
        timeout=60,
    )
    add_s3_trigger(process_fn_name, process_fn_arn, bucket_name, account_id)

    api_fn_arn = create_or_update_lambda(
        api_fn_name,
        os.path.join(LAMBDA_DIR, "api_handler"),
        role_arn,
        {
            "BUCKET_NAME": bucket_name,
            "USERS_TABLE": users_table,
            "STORIES_TABLE": stories_table,
            "SQS_QUEUE_URL": queue_url,
            "JWT_SECRET": jwt_secret,
        },
        timeout=15,
    )
    api_endpoint = create_http_api(api_name, api_fn_arn, api_fn_name, account_id)

    resources = {
        "region": REGION,
        "account_id": account_id,
        "bucket_name": bucket_name,
        "users_table": users_table,
        "stories_table": stories_table,
        "sns_topic_arn": topic_arn,
        "sqs_queue_url": queue_url,
        "lambda_role_arn": role_arn,
        "process_story_function": process_fn_name,
        "api_handler_function": api_fn_name,
        "api_endpoint": api_endpoint,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(resources, f, indent=2)

    log("=" * 70)
    log("Provisioning complete! Resource summary written to aws_resources.json")
    log(f"  S3 bucket:        {bucket_name}")
    log(f"  DynamoDB tables:  {users_table}, {stories_table}")
    log(f"  SNS topic:        {topic_arn}")
    log(f"  SQS queue:        {queue_url}")
    log(f"  API endpoint:     {api_endpoint}")
    log("=" * 70)
    log("Next: cd app && pip install -r requirements.txt && python app.py")


if __name__ == "__main__":
    main()
