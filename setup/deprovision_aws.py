"""
Deletes every AWS resource created by provision_aws.py, so you don't get
billed for leftovers. Reads ../aws_resources.json for identifiers.

Run: python setup/deprovision_aws.py
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_FILE = os.path.join(ROOT, "aws_resources.json")


def log(msg):
    print(f"[cleanup] {msg}", flush=True)


def main():
    if not os.path.exists(RESOURCES_FILE):
        log("aws_resources.json not found - nothing to clean up.")
        return

    with open(RESOURCES_FILE) as f:
        r = json.load(f)

    region = r["region"]
    s3 = boto3.client("s3", region_name=region)
    dynamodb = boto3.client("dynamodb", region_name=region)
    iam = boto3.client("iam", region_name=region)
    lambda_client = boto3.client("lambda", region_name=region)
    sns = boto3.client("sns", region_name=region)
    sqs = boto3.client("sqs", region_name=region)
    apigw = boto3.client("apigatewayv2", region_name=region)

    # API Gateway
    try:
        apis = apigw.get_apis().get("Items", [])
        for api in apis:
            if api["Name"] == "KidsStoryApp-HttpApi":
                apigw.delete_api(ApiId=api["ApiId"])
                log("Deleted API Gateway HTTP API")
    except ClientError as e:
        log(f"API Gateway cleanup skipped: {e}")

    # Lambda functions
    for fn in (r.get("process_story_function"), r.get("api_handler_function")):
        if not fn:
            continue
        try:
            lambda_client.delete_function(FunctionName=fn)
            log(f"Deleted Lambda function {fn}")
        except ClientError as e:
            log(f"Lambda cleanup skipped for {fn}: {e}")

    # IAM role
    role_name = "KidsStoryApp-LambdaExecutionRole"
    try:
        iam.detach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )
    except ClientError:
        pass
    try:
        iam.delete_role_policy(RoleName=role_name, PolicyName=f"{role_name}-inline-policy")
    except ClientError:
        pass
    try:
        iam.delete_role(RoleName=role_name)
        log("Deleted IAM role")
    except ClientError as e:
        log(f"IAM role cleanup skipped: {e}")

    # SQS
    try:
        sqs.delete_queue(QueueUrl=r["sqs_queue_url"])
        log("Deleted SQS queue")
    except ClientError as e:
        log(f"SQS cleanup skipped: {e}")

    # SNS
    try:
        sns.delete_topic(TopicArn=r["sns_topic_arn"])
        log("Deleted SNS topic")
    except ClientError as e:
        log(f"SNS cleanup skipped: {e}")

    # DynamoDB tables
    for table in (r.get("users_table"), r.get("stories_table")):
        if not table:
            continue
        try:
            dynamodb.delete_table(TableName=table)
            log(f"Deleted DynamoDB table {table}")
        except ClientError as e:
            log(f"DynamoDB cleanup skipped for {table}: {e}")

    # S3 bucket (must be emptied first)
    bucket_name = r.get("bucket_name")
    if bucket_name:
        try:
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name):
                objects = page.get("Contents", [])
                if objects:
                    s3.delete_objects(
                        Bucket=bucket_name,
                        Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                    )
            s3.delete_bucket(Bucket=bucket_name)
            log(f"Deleted S3 bucket {bucket_name}")
        except ClientError as e:
            log(f"S3 cleanup skipped: {e}")

    log("Cleanup complete.")


if __name__ == "__main__":
    main()
