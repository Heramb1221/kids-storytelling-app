"""
ProcessStoryLambda
Triggered by: S3 ObjectCreated events on the "stories/" prefix (.txt files)
Does: reads the story text, converts it to speech with Amazon Polly,
      stores the MP3 back in S3 under "audio/", updates the DynamoDB
      story record, and publishes a "story ready" notification to SNS.
"""

import base64
import json
import os
import urllib.parse
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
polly = boto3.client("polly")
dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

STORIES_TABLE = os.environ["STORIES_TABLE"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
VOICE_ID = os.environ.get("POLLY_VOICE_ID", "Ivy")  # Ivy = friendly, kid-appropriate voice

stories_table = dynamodb.Table(STORIES_TABLE)

# Polly synchronous SynthesizeSpeech supports up to 3000 billed characters per call
MAX_CHARS = 2900


def lambda_handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        if not key.startswith("stories/") or not key.lower().endswith(".txt"):
            continue

        story_id = key.split("/")[-1].rsplit(".", 1)[0]

        try:
            process_one(bucket, key, story_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Failed processing {key}: {exc}")
            mark_error(story_id, str(exc))

    return {"statusCode": 200, "body": "ok"}


def process_one(bucket, key, story_id):
    obj = s3.get_object(Bucket=bucket, Key=key)
    text = obj["Body"].read().decode("utf-8").strip()

    if not text:
        raise ValueError("Story text file is empty")

    text_for_speech = text[:MAX_CHARS]
    audio_bytes = synthesize(text_for_speech)

    audio_key = f"audio/{story_id}.mp3"
    s3.put_object(Bucket=bucket, Key=audio_key, Body=audio_bytes, ContentType="audio/mpeg")

    now = datetime.now(timezone.utc).isoformat()
    stories_table.update_item(
        Key={"story_id": story_id},
        UpdateExpression="SET #s = :ready, audio_key = :ak, updated_at = :ua",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":ready": "ready", ":ak": audio_key, ":ua": now},
    )

    item = stories_table.get_item(Key={"story_id": story_id}).get("Item", {})

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject="Story Ready",
        Message=json.dumps(
            {
                "story_id": story_id,
                "title": item.get("title", "Untitled Story"),
                "teacher_username": item.get("teacher_username", ""),
                "status": "ready",
            }
        ),
    )


def synthesize(text):
    """Try the higher-quality neural engine first, fall back to standard."""
    for engine in ("neural", "standard"):
        try:
            response = polly.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId=VOICE_ID,
                Engine=engine,
            )
            return response["AudioStream"].read()
        except ClientError as exc:
            print(f"[WARN] Polly engine={engine} failed: {exc}")
            continue
    raise RuntimeError("Polly synthesis failed for both neural and standard engines")


def mark_error(story_id, error_message):
    try:
        stories_table.update_item(
            Key={"story_id": story_id},
            UpdateExpression="SET #s = :err, error_message = :em, updated_at = :ua",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":err": "error",
                ":em": error_message[:500],
                ":ua": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Could not mark story {story_id} as error: {exc}")
