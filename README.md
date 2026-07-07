# Storytime Stars — Kids Storytelling App

> A cloud-native kids storytelling platform where teachers publish stories, AWS converts them into narrated read-aloud experiences with Amazon Polly, and students open interactive story cards like books with text on one page and audio on the other.

![AWS](https://img.shields.io/badge/AWS-ap--south--1-FF9900?style=flat-square&logo=amazonwebservices&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Frontend_Server-000000?style=flat-square&logo=flask&logoColor=white)
![Amazon Polly](https://img.shields.io/badge/Amazon-Polly-FF9900?style=flat-square&logo=amazonaws&logoColor=white)
![DynamoDB](https://img.shields.io/badge/Amazon-DynamoDB-4053D6?style=flat-square&logo=amazondynamodb&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active_Development-success?style=flat-square)

---

## About The Project

Storytime Stars is a cloud-native storytelling application designed for classroom-scale use. Teachers can paste a story directly into the application or upload a text file. AWS processes the story asynchronously, converts it into narrated speech with Amazon Polly, stores the generated audio privately in Amazon S3, updates story state in DynamoDB, and publishes a completion notification through an SNS-to-SQS pipeline.

Students create an account, browse available story cards, and open a story through a book-inspired interface. The story text appears on one page while narrated audio plays from the other, creating a simple read-aloud experience.

The local Flask application intentionally handles only frontend delivery. Authentication, story publishing, uploads, story retrieval, processing state, and notifications all flow directly from the browser to Amazon API Gateway and AWS Lambda.

The project demonstrates serverless API design, event-driven processing, direct-to-S3 uploads, presigned URLs, custom token-based authentication, password hashing, DynamoDB persistence, text-to-speech generation, SNS fan-out, SQS notification delivery, and automated AWS provisioning.

---

## Project Type

**Cloud / Serverless / Full-Stack / EdTech Application** — Event-driven AWS application combining teacher publishing workflows, student story consumption, Amazon Polly narration, S3 object events, DynamoDB persistence, custom authentication, SNS/SQS notifications, and a locally served Flask frontend.

---

## Project Status

**Active Development** — Core teacher publishing, student story browsing, authentication, asynchronous narration, processing-state updates, and notification workflows are implemented.

The application currently uses:

- AWS backend infrastructure in `ap-south-1`
- Flask frontend served locally
- Classroom-scale notification semantics
- Short-story Polly processing

Production hardening and multi-tenant notification isolation remain future work.

---

## Why I Built This

The goal was to build an educational application where cloud services participate in a meaningful user workflow instead of simply hosting a CRUD backend.

The technical objectives were:

- Build separate teacher and student experiences
- Convert teacher-authored text into narrated audio
- Learn event-driven processing with S3 object creation events
- Use direct browser-to-S3 uploads through presigned URLs
- Keep Flask limited to frontend delivery
- Build authentication without relying on Amazon Cognito
- Store users and stories in DynamoDB
- Design asynchronous story processing with explicit status transitions
- Use SNS and SQS together for completion notifications
- Implement polling for teacher-facing readiness updates
- Provision AWS resources programmatically
- Make provisioning safe to re-run
- Provide automated teardown to control cloud costs

---

## Features

### Teacher Experience

- **Teacher signup and login** — Role-aware account workflow
- **Paste story text** — Publish a title and story directly
- **Upload text stories** — Direct browser-to-S3 upload using presigned URLs
- **Processing state** — Story cards display processing readiness
- **Ready notifications** — Teacher receives a UI notification when narration completes
- **Teacher dashboard** — View published stories and their state

### Student Experience

- **Student signup and login** — Separate role-aware flow
- **Story Circle dashboard** — Browse available story cards
- **Book-style reader** — Opens a selected story like a book
- **Text page** — Displays story content
- **Narration page** — Plays generated audio
- **Private audio access** — Uses temporary presigned S3 URLs

### Story Processing

- **S3-triggered workflow** — Uploading `stories/<id>.txt` invokes processing
- **Amazon Polly narration** — Converts story text into MP3 speech
- **Private S3 storage** — Stores source text and generated audio
- **DynamoDB state updates** — Tracks story readiness and metadata
- **SNS completion event** — Publishes story-ready notifications
- **SQS delivery** — Queues notifications for teacher polling

### Authentication

- **PBKDF2-HMAC-SHA256 password hashing**
- **No plaintext password storage**
- **Signed expiring tokens**
- **12-hour token lifetime**
- **Bearer token authentication**
- **Role-aware teacher/student accounts**

### Infrastructure

- **Automated AWS provisioning**
- **Safe re-runs**
- **Automatic Lambda redeployment**
- **Generated `aws_resources.json`**
- **Automated deprovisioning**
- **Regional deployment in `ap-south-1`**

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Cloud Platform | AWS | Managed compute, storage, APIs, messaging, persistence, and speech synthesis |
| Region | `ap-south-1` | Mumbai deployment target |
| Frontend Server | Flask | Serves HTML, CSS, and JavaScript only |
| API Layer | API Gateway HTTP API | Browser-facing serverless API |
| Compute | AWS Lambda | Handles API logic and asynchronous story processing |
| Object Storage | Amazon S3 | Stores source story files and generated MP3 audio |
| Database | Amazon DynamoDB | Stores users, stories, processing state, and metadata |
| Text-to-Speech | Amazon Polly | Converts story text into narrated audio |
| Notifications | Amazon SNS | Publishes story-ready events |
| Queue | Amazon SQS | Buffers notifications for teacher polling |
| Identity Logic | Custom HMAC tokens | Lightweight stateless authentication |
| Password Security | PBKDF2-HMAC-SHA256 | Password hashing with standard-library primitives |
| Provisioning | Python + `boto3` | Creates and removes AWS infrastructure |
| Frontend | HTML + CSS + JavaScript | Teacher/student dashboards and book-style UI |
| Language | Python 3.10+ | Shared backend, provisioning, and Flask language |

---

## Architecture

```text
 Teacher Browser
      │
      ├── POST /stories/paste
      │
      └── POST /stories/upload-url
                     │
                     ▼
          API Gateway (HTTP API)
                     │
                     ▼
             ApiHandlerLambda
             ├── signup / login
             │     └──► DynamoDB Users
             ├── list / get stories
             │     └──► DynamoDB Stories + S3
             ├── presigned upload URLs
             └── polls SQS for notifications
                     │
                     ▼
          Presigned S3 upload URL
                     │
 Teacher Browser     │
      │               │
      └── PUT file ───┘
                     ▼
          S3: stories/<id>.txt
                     │
                     │ ObjectCreated
                     ▼
          ProcessStoryLambda
          ├──► Read story text from S3
          ├──► Amazon Polly → MP3
          ├──► S3: audio/<id>.mp3
          ├──► Update DynamoDB Stories
          └──► Publish SNS event
                         │
                         ▼
                    SNS Topic
                         │
                         ▼
                    SQS Queue
                         │
                         └──► ApiHandlerLambda polls
                              for teacher notification


 Student Browser
      │
      ├── GET /stories
      └── GET /stories/{id}
                     │
                     ▼
          API Gateway → ApiHandlerLambda
                     │
                     ├──► DynamoDB Stories
                     ├──► S3 story text
                     └──► Presigned audio URL


 Local Flask App
      │
      └── serves HTML / CSS / JS only
          no application data logic
```

---

## Request & Processing Flow

### Teacher Paste Flow

1. Teacher authenticates.
2. Browser sends `POST /stories/paste`.
3. API Gateway invokes `ApiHandlerLambda`.
4. The API validates the teacher token.
5. Story metadata is created.
6. Story content enters the processing workflow.
7. The story is marked as processing.
8. `ProcessStoryLambda` generates narration.
9. DynamoDB is updated to a ready state.
10. SNS publishes completion.
11. SQS receives the notification.
12. Teacher polling surfaces a toast.

### Teacher Upload Flow

1. Teacher requests `POST /stories/upload-url`.
2. API Lambda generates a story ID and presigned S3 PUT URL.
3. Browser uploads the text file directly to `stories/<id>.txt`.
4. S3 emits an `ObjectCreated` event.
5. `ProcessStoryLambda` reads the file.
6. Polly synthesizes narration.
7. MP3 is written to `audio/<id>.mp3`.
8. DynamoDB story metadata is updated.
9. SNS publishes story readiness.
10. SQS buffers the notification.

### Student Reading Flow

1. Student authenticates.
2. Browser requests `GET /stories`.
3. Student selects a story card.
4. Browser requests `GET /stories/{id}`.
5. API Lambda retrieves story metadata and text.
6. A temporary presigned audio URL is generated.
7. The book-style reader displays text and narrated audio.

---

## Why Flask Only Serves The Frontend

Flask intentionally does not own the application data path.

```text
Browser
   │
   ▼
API Gateway
   │
   ▼
Lambda
   ├── DynamoDB
   ├── S3
   ├── SQS
   └── other AWS services
```

Flask only serves:

- HTML
- CSS
- JavaScript
- Page routes

### Benefits

- No application AWS credentials are required by the Flask frontend server
- Application logic remains serverless
- Frontend hosting can later move to S3 + CloudFront
- API scaling is independent from Flask
- Local development remains simple

### Tradeoff

The browser must manage API endpoint configuration, Bearer tokens, CORS, and direct AWS-backed workflows.

---

## Why Presigned S3 Uploads

Uploaded story files go directly from the browser to S3.

```text
Browser
   │ request upload authorization
   ▼
ApiHandlerLambda
   │
   ▼
Presigned PUT URL
   │
   ▼
Browser ─────────► S3
```

### Benefits

- File bytes do not pass through Flask
- Lambda payload sizes remain small
- API Gateway is not used as a file proxy
- AWS credentials are not exposed
- S3 remains private
- Upload permissions expire automatically

### Tradeoff

The browser must perform a two-step request flow.

---

## Why SNS + SQS For Notifications

When processing completes:

```text
ProcessStoryLambda
        │
        ▼
      SNS
        │
        ▼
      SQS
        │
        ▼
ApiHandlerLambda polls
        │
        ▼
Teacher UI toast
```

SNS represents the published event:

> A story is ready.

SQS provides durable buffering so the notification does not depend on the teacher being online at the exact moment processing completes.

### Current Limitation

All teachers share one queue. The API Lambda deletes only messages addressed to the requesting teacher and leaves others for later polling.

This is acceptable for a classroom-scale demonstration but does not scale cleanly to many concurrent teachers.

Potential production alternatives include:

- One queue per teacher
- SNS subscription filter policies
- Per-tenant queues
- DynamoDB notification inbox
- WebSockets
- EventBridge-based routing

---

## Authentication Design

Authentication is intentionally implemented without Amazon Cognito.

### Password Storage

Passwords are hashed using:

```text
PBKDF2-HMAC-SHA256
```

The implementation uses Python standard-library cryptographic primitives.

### Login

Successful login returns a signed token containing authentication information.

The token:

- Is HMAC-signed
- Expires after 12 hours
- Is stored by the browser in `localStorage`
- Is sent as a Bearer token

```http
Authorization: Bearer <token>
```

### Why This Design

- Easy to understand
- Easy to run locally
- No Cognito configuration
- Stateless API authentication
- Suitable for a controlled educational demo

### Production Limitations

- `localStorage` tokens are exposed to successful XSS
- Custom authentication increases security responsibility
- Key rotation is not described
- Revocation is harder with stateless tokens
- Cognito or another mature identity provider is preferable for production

---

## AWS Services Used

| AWS Service | Responsibility |
|---|---|
| S3 | Stores story text files and generated MP3 narration |
| Lambda | Runs API logic and asynchronous story processing |
| API Gateway | Exposes HTTP API endpoints |
| DynamoDB | Stores users and story metadata |
| Polly | Synthesizes story narration |
| SNS | Publishes story-ready events |
| SQS | Buffers teacher notifications |
| IAM | Grants service permissions and Lambda execution access |
| CloudWatch | Provides Lambda logs for troubleshooting |

---

## Lambda Functions

### `ProcessStoryLambda`

**Trigger:** S3 `ObjectCreated`

Responsibilities:

- Read `stories/<id>.txt`
- Validate story content
- Call Amazon Polly
- Generate MP3 narration
- Write `audio/<id>.mp3`
- Update DynamoDB Stories
- Publish completion to SNS

### `ApiHandlerLambda`

**Trigger:** API Gateway HTTP API

Responsibilities:

- Teacher/student signup
- Teacher/student login
- Password verification
- Signed token generation
- Token validation
- Story listing
- Story retrieval
- Paste publishing
- Presigned S3 upload URL generation
- Presigned audio URL generation
- Notification polling
- SQS message handling

---

## Data Storage Design

### S3 Layout

```text
private-bucket/
├── stories/
│   ├── <story-id-1>.txt
│   └── <story-id-2>.txt
└── audio/
    ├── <story-id-1>.mp3
    └── <story-id-2>.mp3
```

### DynamoDB Tables

#### `KidsStoryApp_Users`

Conceptually stores:

```text
{
  username,
  password_hash,
  salt,
  role,
  created_at
}
```

#### `KidsStoryApp_Stories`

Conceptually stores:

```text
{
  story_id,
  title,
  teacher_id,
  status,
  story_key,
  audio_key,
  created_at,
  updated_at
}
```

The exact schema is defined by the repository implementation.

---

## Project Structure

```text
kids-storytelling-app/
├── setup/
│   ├── provision_aws.py
│   │   └── creates AWS resources
│   └── deprovision_aws.py
│       └── tears infrastructure down
│
├── lambda_functions/
│   ├── process_story/
│   │   └── S3 → Polly → MP3 → DynamoDB → SNS
│   └── api_handler/
│       └── auth, stories, uploads, notifications
│
├── app/
│   ├── app.py
│   │   └── local Flask frontend server
│   ├── requirements.txt
│   ├── templates/
│   │   ├── landing
│   │   ├── login
│   │   ├── signup
│   │   ├── teacher dashboard
│   │   └── student dashboard
│   └── static/
│       ├── css/
│       └── js/
│
├── sample_story.txt
├── requirements.txt
├── aws_resources.json
└── README.md
```

---

## Prerequisites

- Python 3.10+
- AWS account
- AWS credentials configured locally
- `pip`
- Permissions for S3, DynamoDB, Lambda, IAM, API Gateway, SNS, SQS, and Polly
- Region: `ap-south-1`

Configure AWS credentials:

```bash
aws configure
```

> AWS services are usage-based. You are responsible for charges generated by deployed resources.

---

## Installation

### 1. Clone The Repository

```bash
git clone <your-repository-url>
cd kids-storytelling-app
```

### 2. Install Root Dependencies

```bash
pip install -r requirements.txt --break-system-packages
```

Using a virtual environment is recommended:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Provision AWS Resources

Run from the project root:

```bash
python setup/provision_aws.py
```

The script creates:

- S3 bucket
- DynamoDB Users table
- DynamoDB Stories table
- IAM role
- `ProcessStoryLambda`
- `ApiHandlerLambda`
- S3 → Lambda trigger
- SNS topic
- SQS queue
- SNS → SQS subscription
- API Gateway HTTP API

The script is safe to re-run. Existing resources are reused where appropriate, and Lambda code is redeployed.

When complete, it writes:

```text
aws_resources.json
```

Example output:

```text
Provisioning complete! Resource summary written to aws_resources.json
  S3 bucket:        kidsstoryapp-123456789012
  DynamoDB tables:  KidsStoryApp_Users, KidsStoryApp_Stories
  SNS topic:        arn:aws:sns:ap-south-1:...
  SQS queue:        https://sqs.ap-south-1.amazonaws.com/...
  API endpoint:     https://abc123xyz.execute-api.ap-south-1.amazonaws.com
```

---

## Run The App Locally

```bash
cd app
pip install -r requirements.txt --break-system-packages
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

---

## Usage

### Teacher Flow

1. Click **I'm a Teacher**.
2. Sign up.
3. Log in.
4. Open the Teacher Dashboard.
5. Either paste a title and story text or upload `sample_story.txt`.
6. Publish the story.
7. The card displays **Processing**.
8. S3 triggers `ProcessStoryLambda`.
9. Polly generates narration.
10. DynamoDB changes the story to **Ready**.
11. SNS publishes completion.
12. SQS stores the notification.
13. Teacher polling displays a toast.

### Student Flow

1. Open a new browser tab or log out.
2. Click **I'm a Student**.
3. Sign up.
4. Log in.
5. Open the Story Circle dashboard.
6. Select a story card.
7. The story opens like a book.
8. Read text on one page.
9. Listen to narration on the other.

---

## API Responsibilities

The exact route implementation is defined by `ApiHandlerLambda`, but the API conceptually supports:

| Area | Responsibility |
|---|---|
| Authentication | Signup and login |
| Stories | List and retrieve stories |
| Paste Publishing | Publish story text |
| Uploads | Generate presigned S3 upload URLs |
| Audio | Generate temporary audio access |
| Notifications | Poll teacher story-ready messages |

Known routes include:

```text
POST /stories/paste
POST /stories/upload-url
GET  /stories
GET  /stories/{id}
```

---

## Polly Voice Strategy

The application defaults to:

```text
Ivy
```

with the neural engine when available.

If neural synthesis is unavailable, the implementation falls back to the standard engine.

### Why Ivy

- Friendly narration style
- Appropriate for a children's storytelling experience
- Clear spoken output

### Text Length Constraint

Story text is capped at approximately:

```text
2,900 characters
```

per synchronous Polly call.

This keeps stories within the application's short-form classroom use case.

---

## Screenshots

Add screenshots after capturing the application UI.

| Preview | Description |
|---|---|
| <img width="1917" height="867" alt="Screenshot 2026-07-07 100033" src="https://github.com/user-attachments/assets/b53d28aa-32f0-4653-9185-fbdc10e7ee28" /> | **Teacher / Student Landing Page** |
| <img width="1920" height="1211" alt="Teacher-Dashboard-—-Storytime-Stars" src="https://github.com/user-attachments/assets/75293a32-61c6-4dfe-8a82-2f7ddcf03453" /> | **Teacher Dashboard** |
| <img width="1917" height="867" alt="Screenshot 2026-07-07 100234" src="https://github.com/user-attachments/assets/1d989258-d259-4903-a605-10f50110a805" /> | **Student Dashboard** |
| <img width="1917" height="862" alt="Screenshot 2026-07-07 100227" src="https://github.com/user-attachments/assets/e1964dcf-b690-468d-bcdd-94acd3e51493" /> | **Interactive Book Reader** |

---

## Performance Considerations

**Direct S3 uploads** — Uploaded files bypass Flask, API Gateway payload forwarding, and Lambda request bodies.

**Asynchronous narration** — Polly synthesis runs after S3 object creation instead of blocking the publishing request.

**DynamoDB persistence** — User and story state use managed low-latency storage.

**Presigned audio URLs** — MP3 files are delivered directly from S3.

**Polling overhead** — Teacher notification polling creates repeated API Gateway, Lambda, SQS, and potentially DynamoDB operations.

**Synchronous Polly limit** — The current short-story cap simplifies processing but limits longer content.

**Single API Lambda** — Consolidating many API responsibilities simplifies deployment but increases handler complexity as features grow.

**Shared SQS queue** — Classroom-scale operation is acceptable, but message inspection and visibility behavior become problematic with many teachers.

---

## Known Issues

- All teachers currently share one SQS notification queue.
- Notification polling is designed for classroom-scale use, not high concurrency.
- Story text is capped at approximately 2,900 characters.
- Polly narration quality depends on voice and engine availability.
- The application uses custom authentication rather than Cognito.
- Browser tokens stored in `localStorage` increase XSS impact.
- The local Flask server is not a production frontend deployment.
- A story can remain in `Processing` if asynchronous Lambda execution fails.
- Public production use would require stronger child privacy and content-safety controls.

---

## Challenges Faced

### Designing Two User Roles

Teachers create content while students consume it. The API must distinguish permissions without duplicating the entire application.

### Asynchronous Story Processing

Narration is not available immediately after upload. The UI needs processing states and must transition to ready after Polly output is stored.

### SNS-To-SQS Notifications

The system separates event publication from teacher consumption. SNS broadcasts readiness while SQS buffers delivery.

The shared-queue design creates an important multi-tenant challenge: one teacher must not consume another teacher's notification.

### Direct Uploads

Presigned URLs keep file bytes away from Flask and Lambda, but require careful CORS and object-key handling.

### Custom Authentication

Implementing password hashing, signed tokens, expiration, role checks, and Bearer validation without Cognito creates significant security responsibility.

### Idempotent Provisioning

AWS resources have dependency ordering and may already exist after partial failures. The provisioning script must reuse resources and redeploy Lambda code without blindly duplicating infrastructure.

---

## What I Learned

- How to build separate teacher and student workflows
- How S3 events trigger asynchronous Lambda processing
- How Amazon Polly converts application text into MP3 narration
- How presigned URLs enable direct private uploads
- How DynamoDB stores users and asynchronous story state
- How SNS and SQS solve different messaging problems
- Why durable queues help disconnected consumers
- How polling bridges asynchronous backend processing to a browser UI
- How PBKDF2-HMAC-SHA256 password hashing works
- How signed expiring tokens enable stateless authentication
- The security tradeoffs of custom auth
- Why `localStorage` tokens increase XSS impact
- How idempotent provisioning improves recovery
- Why frontend-only Flask hosting keeps application logic independent
- How cloud architecture changes when multiple user roles are introduced

---

## Troubleshooting

### App Is Not Configured Yet

If the browser shows:

```text
App is not configured yet
```

then `aws_resources.json` is missing.

Run:

```bash
python setup/provision_aws.py
```

from the project root.

### AccessDenied During Provisioning

Ensure your AWS identity has required permissions for:

- S3
- DynamoDB
- Lambda
- IAM
- API Gateway
- SNS
- SQS

### Story Stuck On Processing

Check CloudWatch Logs for:

```text
KidsStoryApp-ProcessStory
```

Possible causes include:

- Empty story file
- Invalid content
- Polly service error
- IAM permission error
- S3 event failure
- DynamoDB update failure

### CORS Errors

Re-run:

```bash
python setup/provision_aws.py
```

The provisioning script configures CORS for S3 and API Gateway.

---

## Tear Down

To remove AWS resources:

```bash
python setup/deprovision_aws.py
```

Use teardown after testing to reduce the risk of ongoing charges.

After deprovisioning, inspect the AWS console and verify removal of resources created by the project.

---

## Contact

**Heramb Chaudhari**

[![GitHub](https://img.shields.io/badge/GitHub-Heramb1221-black?style=for-the-badge&logo=github)](https://github.com/Heramb1221)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Heramb%20Chaudhari-blue?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/heramb-chaudhari/)

[![Email](https://img.shields.io/badge/Email-hchaudhari1221%40gmail.com-red?style=for-the-badge&logo=gmail)](mailto:hchaudhari1221@gmail.com)

---

*Built with AWS Lambda, Amazon S3, DynamoDB, Polly, SNS, SQS, API Gateway, Python, and Flask.*
