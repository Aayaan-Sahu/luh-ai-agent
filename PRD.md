Here is the comprehensive Product Requirements Document (PRD) and Technical Implementation Guide for Project AcademicAgent. This document bridges the gap between high-level product goals and low-level engineering execution, specifically designed for a Senior Engineering team.

Part 1: Product Requirements Document (PRD)
1. Executive Summary
Project Name: AcademicAgent
Problem: Students manage academic lives across fragmented platforms (LMS, static PDF syllabi, manual calendar entry), leading to missed deadlines and poor time management. Solution: An Agentic AI application that ingests raw academic documents (PDFs), intelligently extracts deliverables, negotiates schedule conflicts via natural language, and autonomously manages a Google Calendar. Primary Goal: To build a robust, containerized AI agent capable of multi-turn reasoning to automate academic scheduling and information retrieval.

2. User Stories & Functional Requirements
ID	User Story	Acceptance Criteria
US-1	As a student, I want to upload a PDF syllabus so that its deadlines are automatically extracted.	Agent parses PDF, identifies 100% of dates, and presents a structured list for confirmation.
US-2	As a student, I want the agent to check my availability before booking.	Agent queries Google Calendar API for conflicts before creating events.
US-3	As a student, I want to query specific course policies (e.g., "Late policy?").	Agent performs RAG (Retrieval Augmented Generation) on stored syllabus vectors to answer accurately.
US-4	As a user, I want automated reminders for upcoming exams.	System triggers a background notification 24h and 1h before high-priority events.
3. Technical Stack Justification
Docker & Docker Compose: Ensures identical dev/prod environments. Orchestrates the API, Worker, and Redis services.
Redis: Acts as the Message Broker for the asynchronous task queue (Celery) and a high-speed store for LangGraph conversation state.
Supabase (PostgreSQL): Essential for persisting User Auth (OAuth tokens), User Profiles, and structured Course Metadata. It replaces local SQLite to allow for multi-user scaling.
Pydantic: Enforces strict data validation. If the LLM returns a malformed date or missing field, Pydantic catches it before it corrupts the database.
Celery: Distributed task queue. Decouples heavy AI processing (PDF parsing) and background reminders from the main API thread.
4. Success Metrics (MVP)
Extraction Accuracy: >90% of dates correctly identified from standard syllabi.
Latency: Calendar queries return within <2 seconds; PDF processing completes within <15 seconds.
Reliability: Background reminders fire within ±1 minute of scheduled time.
Part 2: Technical Implementation Guide
This guide assumes a Linux/Mac terminal environment.

1. Environment & Secrets Management
Create a .env file in the project root. Do not commit this to Git.

Bash
# General
PROJECT_NAME="AcademicAgent"
ENV="development"

# OpenAI / LLM
OPENAI_API_KEY="sk-..."

# Google Cloud (OAuth)
GOOGLE_CLIENT_ID="<your-client-id>.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="<your-client-secret>"
GOOGLE_REDIRECT_URI="http://localhost:8000/auth/callback"

# Supabase
SUPABASE_URL="https://<project-ref>.supabase.co"
SUPABASE_KEY="<your-anon-key>"
SUPABASE_DB_URI="postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres"

# Redis
REDIS_URL="redis://redis:6379/0"
2. Docker Infrastructure
We need a containerized environment running the FastAPI Application, a Celery Worker (for reminders/heavy lifting), and Redis.

File: docker-compose.yml

YAML
version: '3.8'

services:
  # The Main API / Agent Service
  api:
    build: .
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  # Background Worker (Celery)
  worker:
    build: .
    command: celery -A app.worker.celery_app worker --loglevel=info
    volumes:
      - .:/app
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  # Message Broker & Cache
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
File: Dockerfile

Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (needed for some Python packages)
RUN apt-get update && apt-get install -y gcc libpq-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
3. Pydantic Data Schemas
Define strict types to govern data flowing into the system.

File: app/schemas.py

Python
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime

# Settings / Config Model
class Settings(BaseModel):
    openai_api_key: str
    redis_url: str

# Google Calendar Event Model
class CalendarEvent(BaseModel):
    summary: str = Field(..., description="Title of the event")
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "summary": "CS101 Midterm",
                "start_time": "2023-10-25T14:00:00",
                "end_time": "2023-10-25T15:30:00"
            }
        }

# User Profile (synced with Supabase)
class UserProfile(BaseModel):
    id: str
    email: str
    google_refresh_token: Optional[str] = None # ENCYYPT THIS IN DB
4. Supabase Setup (Database & Auth)
Evaluation: Supabase is necessary here. Storing Google OAuth Refresh Tokens locally (JSON file) is insecure and fails in Docker containers (containers are ephemeral). Supabase provides a hosted Postgres DB to securely store user state and tokens.

SQL Schema Initialization: Run this in the Supabase SQL Editor:

SQL
-- Users table to extend Supabase Auth
create table public.profiles (
  id uuid references auth.users not null,
  email text not null,
  google_refresh_token text, -- Store encrypted
  preferences jsonb,
  primary key (id)
);

-- Tasks table for the Agent
create table public.academic_events (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references public.profiles(id),
  title text not null,
  start_at timestamptz not null,
  end_at timestamptz not null,
  is_synced_to_gcal boolean default false
);
5. Google Calendar Integration (OAuth2)
The critical path is handling the OAuth handshake to get the refresh_token.

Step 1: Create Credentials in Google Cloud Console. Step 2: Implement the Auth Flow (app/auth.py).

Python
from google_auth_oauthlib.flow import Flow
from app.config import settings

def create_google_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/drive.readonly"],
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )

# Use this wrapper to build the Agent Tool
def build_calendar_service(credentials):
    from googleapiclient.discovery import build
    return build('calendar', 'v3', credentials=credentials)
6. Scheduling Engine (Celery)
We use Celery to handle background reminders so the Agent doesn't have to "wait" for the event time.

File: app/worker.py

Python
from celery import Celery
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("academic_agent", broker=redis_url, backend=redis_url)

@celery_app.task
def schedule_reminder_notification(email: str, event_title: str):
    # Logic to send email/slack notification
    print(f"REMINDER: {event_title} is coming up for {email}!")
    # Integration point: SendGrid or Twilio
Triggering the Task (from Agent Logic):

Python
from app.worker import schedule_reminder_notification
from datetime import timedelta

# When agent creates an event:
reminder_time = event.start_time - timedelta(hours=1)
schedule_reminder_notification.apply_async(
    args=[user_email, event.summary], 
    eta=reminder_time # Celery handles the specific execution time
)
Part 3: Operational Requirements
1. Security & Token Management
Encryption: Never store google_refresh_token as plain text in Supabase. Use a library like cryptography (Fernet) to encrypt the token before writing to SQL and decrypt it only when initializing the Google Client.
Scope Minimization: Start with calendar.events (read/write). Do not request calendar (full account access) unless absolutely necessary.
2. Error Handling Strategy
Rate Limits: Wrap all Google API calls with a retry decorator (e.g., tenacity) with exponential backoff.
Policy: If HTTP 429 is received, wait 2s, 4s, 8s, then fail gracefully.
Token Expiry: The system must check if the Access Token is expired before every tool call. If expired, use the Refresh Token to fetch a new one silently.
3. Deployment Checklist
[ ] Set up Supabase Project & Run SQL Schema.
[ ] Configure Google Cloud OAuth Consent Screen.
[ ] Populate .env file.
[ ] Run docker-compose up --build.
[ ] Verify Redis connection (docker exec -it <container_id> redis-cli ping).
Technology Decisions

**Frontend**: Streamlit Dashboard
- Streamlit will serve as the user-facing interface
- Provides rapid prototyping with Python-native components
- No CORS configuration needed when running on same origin; if separate, FastAPI middleware will allow Streamlit's origin

**Notification Channel**: ntfy.sh Push Notifications
- Lightweight, self-hostable push notification service
- No account required for basic usage
- Simple HTTP POST to send notifications

```python
# Example ntfy.sh integration
import httpx

async def send_reminder(topic: str, title: str, message: str):
    await httpx.post(
        f"https://ntfy.sh/{topic}",
        headers={"Title": title},
        content=message
    )
```

**PDF Processing**: Dual-Mode (Text + OCR)
- **Standard Text PDFs**: Use `PyMuPDF` (fitz) for fast, direct text extraction
- **Scanned Image PDFs**: Use `pytesseract` + `pdf2image` for OCR processing
- Auto-detection: If text extraction yields minimal content, fallback to OCR

```python
# Example PDF processing logic
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract

def extract_text(pdf_path: str) -> str:
    # Try direct text extraction first
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    
    # Fallback to OCR if text is sparse
    if len(text.strip()) < 100:
        images = convert_from_path(pdf_path)
        text = "\n".join(pytesseract.image_to_string(img) for img in images)
    
    return text
```

**Additional Dependencies** (add to requirements.txt):
```
streamlit
httpx
PyMuPDF
pytesseract
pdf2image
pillow
```

**System Dependencies** (add to Dockerfile):
```dockerfile
RUN apt-get update && apt-get install -y \
    gcc libpq-dev \
    tesseract-ocr \
    poppler-utils
```