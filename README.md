# 📖✨ Storytime Stars — Kids Storytelling App

Teachers upload or paste a story. AWS turns it into a read-aloud with Amazon
Polly. Students log in, pick a story card, and it "opens like a book" with
the text on one page and narrated audio on the other.

## Architecture

```
Teacher browser
   |  (1) POST /stories/paste  or  POST /stories/upload-url -> PUT file to S3
   v
API Gateway (HTTP API)  --------->  ApiHandlerLambda
                                       - signup / login (DynamoDB Users)
                                       - list / get stories (DynamoDB Stories, S3)
                                       - presigned S3 upload URLs
                                       - polls SQS for "story ready" notifications
   |
   v
S3 bucket  stories/<id>.txt  ----(ObjectCreated event)---->  ProcessStoryLambda
                                       - reads story.txt from S3
                                       - Amazon Polly -> MP3
                                       - writes audio/<id>.mp3 to S3
                                       - updates DynamoDB Stories item
                                       - publishes to SNS topic
                                                |
                                                v
                                          SQS queue  <--  ApiHandlerLambda polls this
                                                            to notify the teacher

Student browser
   |  GET /stories  ->  GET /stories/{id}  ->  presigned audio URL + story text
   v
Flask app (local) just serves the HTML/CSS/JS. All data logic lives in AWS.
```

**Services used:** S3, Lambda, API Gateway (HTTP API), DynamoDB, Polly, SNS, SQS, IAM.
**Region:** `ap-south-1` (Mumbai)

## Project layout

```
kids-storytelling-app/
├── setup/
│   ├── provision_aws.py     # creates every AWS resource (run this first)
│   └── deprovision_aws.py   # tears everything down when you're done
├── lambda_functions/
│   ├── process_story/       # S3-triggered: text -> Polly -> MP3 -> DynamoDB -> SNS
│   └── api_handler/         # API Gateway-triggered: auth, stories, notifications
├── app/
│   ├── app.py                # local Flask server (serves the frontend only)
│   ├── requirements.txt
│   ├── templates/            # landing, login, signup, teacher & student dashboards
│   └── static/{css,js}/
├── sample_story.txt          # a short story to test uploads with
├── requirements.txt           # boto3 + Flask, for the setup scripts
└── aws_resources.json         # created automatically by provision_aws.py
```

## Prerequisites

- Python 3.10+
- An AWS account with credentials configured (`aws configure` or environment
  variables) that has permission to create S3 buckets, DynamoDB tables,
  Lambda functions, IAM roles, API Gateway APIs, SNS topics, and SQS queues.
- Amazon Polly and the other services used here are all pay-as-you-go; this
  project's usage will be tiny, but you're responsible for any AWS charges.

## Setup steps

### 1. Install dependencies

```bash
cd kids-storytelling-app
pip install -r requirements.txt --break-system-packages   # or use a venv
```

### 2. Provision AWS resources

This single script creates the S3 bucket, DynamoDB tables, IAM role, both
Lambda functions, the S3 → Lambda trigger, the SNS topic, the SQS queue (and
its subscription), and the API Gateway HTTP API — all in `ap-south-1`.

```bash
python setup/provision_aws.py
```

It's safe to re-run — it reuses resources that already exist and re-deploys
the latest Lambda code. When it finishes it writes `aws_resources.json` with
everything the Flask app needs (nothing to fill in by hand).

You should see a summary like:

```
Provisioning complete! Resource summary written to aws_resources.json
  S3 bucket:        kidsstoryapp-123456789012
  DynamoDB tables:  KidsStoryApp_Users, KidsStoryApp_Stories
  SNS topic:        arn:aws:sns:ap-south-1:...
  SQS queue:        https://sqs.ap-south-1.amazonaws.com/...
  API endpoint:     https://abc123xyz.execute-api.ap-south-1.amazonaws.com
```

### 3. Run the app locally

```bash
cd app
pip install -r requirements.txt --break-system-packages
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

### 4. Try it out

1. Click **"I'm a Teacher" → Sign Up**, create an account.
2. On the Teacher Dashboard, either:
   - paste a title + story text and click **Publish Story**, or
   - upload the included `sample_story.txt` (give it a title, choose the file,
     click **Upload Story**).
3. The story card shows **⏳ Processing** — behind the scenes S3 has
   triggered `ProcessStoryLambda`, which calls Polly and writes the MP3.
   Within a few seconds it flips to **✅ Ready**, and a toast notification
   pops up (that's the SNS → SQS pipeline being polled).
4. Open a new browser tab (or log out), click **"I'm a Student" → Sign Up**.
5. On the Story Circle dashboard, click the story card — it opens like a
   book, showing the text on the left page and playing the narrated audio
   automatically on the right page.

### 5. Tear down (optional, avoids ongoing AWS costs)

```bash
python setup/deprovision_aws.py
```

## Notes & design choices

- **Auth** is intentionally simple: usernames/passwords are hashed
  (PBKDF2-HMAC-SHA256, stdlib only) and stored in a DynamoDB `Users` table.
  Login returns a signed, expiring token (HMAC, 12-hour lifetime) that the
  browser stores in `localStorage` and sends as a `Bearer` token — no AWS
  Cognito, no server-side sessions, easy to run and reason about locally.
- **Flask's only job** is serving the HTML/CSS/JS. Every real operation
  (auth, uploads, listing stories, notifications) goes straight from the
  browser to API Gateway → Lambda, which is what the architecture asked for.
- **Uploads** use S3 presigned URLs so files go directly from the browser to
  S3 — this keeps Lambda payload sizes small and avoids routing file bytes
  through API Gateway.
- **Notifications**: all teachers currently share one SQS queue; the API
  Lambda only deletes messages addressed to the requesting teacher and
  leaves others for their next poll. Fine for a classroom-scale demo; for
  many concurrent teachers you'd want one queue (or filter) per teacher.
- **Polly voice**: defaults to `Ivy` (a cheerful, kid-friendly voice) with
  the neural engine, falling back to the standard engine automatically if
  neural isn't available for some reason.
- Story text is capped at ~2,900 characters per Polly call (its synchronous
  API limit) — plenty for short children's stories.

## Troubleshooting

- **"App is not configured yet"** in the browser → `aws_resources.json` is
  missing; run `python setup/provision_aws.py` from the project root.
- **AccessDenied errors during provisioning** → your AWS credentials need
  permissions for S3, DynamoDB, Lambda, IAM, API Gateway, SNS, and SQS.
- **Story stuck on "Processing"** → check the `KidsStoryApp-ProcessStory`
  Lambda's CloudWatch Logs in the AWS Console for the actual error (e.g. an
  empty file, or a Polly service limit).
- **CORS errors in the browser console** → re-run `provision_aws.py`; it
  configures CORS on both the S3 bucket and the API Gateway API.
