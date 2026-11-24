# Inksight Backend

Inksight backend foundation built with FastAPI, Pydantic, and SQLAlchemy (with SQLite for local development, modular for PostgreSQL).

## Project Structure

```
backend/
├── .env.example              # Environment variables template
├── .env                      # Local environment settings (git-ignored)
├── alembic.ini               # Alembic configuration
├── requirements.txt          # Python dependencies
├── README.md                 # Setup, run, migrations, API reference, and test instructions
├── alembic/                  # Database migration management
│   ├── env.py                # Alembic runtime environment (dynamically loads settings)
│   ├── script.py.mako        # Migration template
│   └── versions/             # Versioned migration scripts
│       ├── c85ef8e6b44a_create_initial_domain_tables.py
│       ├── fc16293183a9_create_submission_and_question_answer_.py
│       ├── 36a1f23df920_create_answer_sheet_uploads_table.py
│       ├── 4b144eb7b676_create_ocr_extractions_table.py
│       ├── 44b1db2314cc_create_proposed_answers_and_teacher_.py
│       ├── 4daf25c04f36_create_evaluation_runs_and_findings.py
│       ├── d6c760e82d63_create_remediation_runs_and_items.py
│       └── a15dcc263571_add_hashed_password_to_users.py
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI entrypoint, middleware & error handling
│   ├── core/                 # Configurations, logging, database engine, security
│   │   ├── config.py         # Pydantic Settings with JWT secrets, token expiry, upload normalization
│   │   ├── database.py       # SQLAlchemy engine & session dependency (SQLite PRAGMA FKs)
│   │   ├── logging.py        # Request & app logging
│   │   └── security.py       # Bcrypt password hashing, verification & JWT creation/decoding
│   ├── api/
│   │   ├── deps.py           # Authentication and RBAC dependencies (get_current_user, require_teacher, require_student, etc.)
│   │   └── v1/               # API version 1 routers
│   │       ├── api.py        # Router aggregator
│   │       └── endpoints/
│   │           ├── auth.py        # /api/v1/auth (/register, /login, /token, /me)
│   │           ├── health.py      # /api/v1/health endpoint
│   │           ├── topics.py      # /api/v1/topics endpoints
│   │           ├── assessments.py # /api/v1/assessments, nested questions & submissions
│   │           ├── questions.py   # /api/v1/questions endpoints
│   │           ├── submissions.py # /api/v1/submissions & question answers endpoints
│   │           ├── uploads.py     # /api/v1/submissions/{id}/answer-sheets, /api/v1/answer-sheets & OCR processing
│   │           ├── matching.py    # Answer matching proposals & teacher review/correction endpoints
│   │           ├── evaluations.py # Evaluation runs, findings & teacher review endpoints
│   │           └── remediation.py # Remediation generation & teacher practice review endpoints
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── enums.py          # Enums for roles, questions, submission, upload, review, evaluation, remediation
│   │   ├── user.py           # User model with hashed_password
│   │   ├── topic.py          # LearningTopic model
│   │   ├── assessment.py     # Assessment and Question models
│   │   ├── submission.py     # Submission, QuestionAnswer, and AnswerSheetUpload models
│   │   ├── ocr.py            # OCRExtraction model
│   │   ├── matching.py       # ProposedAnswer and TeacherReview models
│   │   ├── evaluation.py     # EvaluationRun, EvaluationFinding, and FindingReviewAudit models
│   │   └── remediation.py    # RemediationRun, RemediationItem, and RemediationItemAudit models
│   ├── schemas/              # Pydantic schemas for requests/responses
│   │   ├── common.py         # Generic PaginatedResponse schema
│   │   ├── health.py         # Health schemas
│   │   ├── user.py           # User, UserRegister, Token, LoginRequest schemas
│   │   ├── topic.py          # LearningTopic schemas
│   │   ├── assessment.py     # Assessment schemas (caller created_by removed)
│   │   ├── question.py       # Question schemas
│   │   ├── submission.py     # Submission schemas (caller student_id removed)
│   │   ├── upload.py         # AnswerSheetUpload schemas
│   │   ├── ocr.py            # OCRExtractionRead & ProcessingStatusRead schemas
│   │   ├── matching.py       # ProposedAnswerRead, AnswerMatchingResponse & TeacherReview (reviewer_id removed)
│   │   ├── evaluation.py     # EvaluationRunRead, EvaluationFindingRead & FindingReview (reviewer_id removed)
│   │   └── remediation.py    # RemediationRunRead, RemediationItem schemas & PracticeItemReview (reviewer_id removed)
│   ├── repositories/         # Database query repositories
│   │   ├── user_repository.py
│   │   ├── topic_repository.py
│   │   ├── assessment_repository.py
│   │   ├── question_repository.py
│   │   ├── submission_repository.py
│   │   ├── upload_repository.py
│   │   ├── ocr_repository.py
│   │   ├── matching_repository.py
│   │   ├── evaluation_repository.py
│   │   └── remediation_repository.py
│   └── services/             # Business logic & adapters
│       ├── __init__.py
│       ├── storage_service.py # Filesystem storage, magic-byte check & size limit streaming
│       ├── ocr_service.py     # Orchestrates background OCR task, validation & state transitions
│       ├── matching_service.py # Deterministic answer-to-question matching & teacher review audit
│       ├── evaluation_service.py # AI evaluation orchestration, answer hash snapshots & review audits
│       ├── remediation_service.py # Practice generation, grounding, and teacher practice item review
│       ├── ocr/               # Provider-independent OCR adapter system
│       │   ├── base.py        # BaseOCRAdapter abstract interface & data types
│       │   ├── mock_adapter.py # Deterministic mock OCR adapter for local development/testing
│       │   └── factory.py     # OCR adapter factory (reads OCR_PROVIDER setting)
│       ├── evaluator/         # Provider-independent Evaluation adapter system
│       │   ├── base.py        # BaseEvaluator abstract interface & data types
│       │   ├── mock_evaluator.py # Deterministic mock evaluator for local development/testing
│       │   └── factory.py     # Evaluator factory (reads EVALUATION_PROVIDER setting)
│       └── remediation_generator/ # Provider-independent Remediation generator system
│           ├── base.py        # BaseRemediationGenerator abstract interface & data types
│           ├── mock_generator.py # Deterministic mock generator for local development/testing
│           └── factory.py     # Remediation generator factory (reads REMEDIATION_PROVIDER setting)
└── tests/                    # Automated pytest test suite
    ├── conftest.py           # Test fixtures (isolated SQLite test DB, TestClient, auth_headers_for_user)
    ├── test_health.py        # Health & error handling tests
    ├── test_models.py        # Model relations, FKs, uniqueness & migration tests
    ├── test_api_crud.py      # Complete API CRUD, pagination, and error tests
    ├── test_submissions.py   # Student submission & answer workflow tests
    ├── test_file_upload.py   # Answer sheet upload, validation, download & security tests
    ├── test_ocr_pipeline.py  # OCR pipeline, mock adapter, state machine & background processing tests
    ├── test_matching_and_review.py # Answer matching & teacher review/correction test suite
    ├── test_evaluation_engine.py   # AI evaluation engine, snapshot hash & finding review tests
    ├── test_remediation_service.py # Targeted remediation generation, grounding & practice review tests
    ├── test_audit_and_consistency.py # Cross-record validation, identity boundary, privacy & e2e audit tests
    ├── test_auth_and_rbac.py # JWT authentication, password hashing, token validation, and RBAC ownership tests
    ├── test_practice_sessions.py # Student practice delivery, session lifecycle & response scoring tests
    ├── test_scoring_edge_cases.py # Rigorous scoring edge cases (MCQ, short answer, explain-reasoning, negations, non-answers)
    └── test_concurrency_and_integrity.py # Concurrency race conditions, idempotency, provenance & cascade integrity tests
```

---

## Prerequisites

- Python 3.11+
- Virtual environment support (`python3 -m venv`)

---

## Setup Instructions

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```

2. **Create and activate the virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   *(Update `.env` values as needed for your local environment).*

5. **Apply database migrations**:
   ```bash
   alembic upgrade head
   ```

---

## Database Migrations (Alembic)

All migrations read the active database URL directly from the application configuration (`app.core.config.settings.DATABASE_URL` / `.env`), ensuring consistency across environments without hardcoding database credentials.

Execute these commands from the `backend/` directory with the virtual environment activated:

### 1. Inspect Current Migration Status
```bash
# Show current database revision
alembic current

# Show latest available revision in versions directory
alembic heads

# View revision history
alembic history --verbose
```

### 2. Apply Migrations
```bash
# Upgrade database schema to the latest revision
alembic upgrade head

# Upgrade by one revision
alembic upgrade +1
```

### 3. Create a New Migration
```bash
# Generate a new migration automatically based on model changes
alembic revision --autogenerate -m "add_new_table_or_field"
```

### 4. Rollback Migrations
```bash
# Revert the last applied migration
alembic downgrade -1

# Revert all migrations back to base
alembic downgrade base
```

---

## Running the Development Server

From the `backend` directory (with virtual environment activated):

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or from project root:
```bash
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Interactive API Documentation

- **Swagger UI**: [http://127.0.0.1:8000/api/v1/docs](http://127.0.0.1:8000/api/v1/docs)
- **ReDoc**: [http://127.0.0.1:8000/api/v1/redoc](http://127.0.0.1:8000/api/v1/redoc)
- **OpenAPI Schema**: [http://127.0.0.1:8000/api/v1/openapi.json](http://127.0.0.1:8000/api/v1/openapi.json)

---

## API Reference & Endpoints

> **Note on Security**: These endpoints are designed for local development and testing. Authentication and role-based authorization will be layered in subsequent phases.

### 1. Health Checks
| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service Liveness | `200 OK` |
| `GET` | `/api/v1/health` | API v1 Status & Version | `200 OK` |

### 2. Learning Topics (`/api/v1/topics`)
| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/topics` | Create a new learning topic | `201 Created` |
| `GET` | `/api/v1/topics?limit=20&offset=0` | List learning topics (paginated) | `200 OK` |
| `GET` | `/api/v1/topics/{topic_id}` | Retrieve learning topic by ID | `200 OK` / `404 Not Found` |
| `PATCH` | `/api/v1/topics/{topic_id}` | Partially update learning topic | `200 OK` / `404 Not Found` |
| `DELETE` | `/api/v1/topics/{topic_id}` | Delete learning topic (blocked if referenced) | `204 No Content` / `409 Conflict` |

### 3. Assessments (`/api/v1/assessments`)
| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/assessments` | Create assessment (validates creator exists) | `201 Created` / `404 Not Found` |
| `GET` | `/api/v1/assessments?limit=20&offset=0` | List assessments (paginated) | `200 OK` |
| `GET` | `/api/v1/assessments/{assessment_id}` | Retrieve assessment by ID | `200 OK` / `404 Not Found` |
| `PATCH` | `/api/v1/assessments/{assessment_id}` | Partially update assessment | `200 OK` / `404 Not Found` |
| `DELETE` | `/api/v1/assessments/{assessment_id}` | Delete assessment (cascades to questions & submissions) | `204 No Content` / `404 Not Found` |

### 4. Questions
| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/assessments/{assessment_id}/questions` | Add question under assessment | `201 Created` / `404 Not Found` |
| `GET` | `/api/v1/assessments/{assessment_id}/questions` | List questions for assessment (paginated) | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/questions/{question_id}` | Retrieve single question by ID | `200 OK` / `404 Not Found` |
| `PATCH` | `/api/v1/questions/{question_id}` | Partially update question prompt, marks, etc. | `200 OK` / `404 Not Found` |
| `DELETE` | `/api/v1/questions/{question_id}` | Delete question | `204 No Content` / `404 Not Found` |

### 5. Student Submissions & Answers
| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/assessments/{assessment_id}/submissions` | Create a student submission (`draft`, `submitted`, etc.) | `201 Created` / `404 Not Found` |
| `GET` | `/api/v1/assessments/{assessment_id}/submissions` | List submissions for assessment (paginated) | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/submissions/{submission_id}` | Retrieve single submission by ID | `200 OK` / `404 Not Found` |
| `PATCH` | `/api/v1/submissions/{submission_id}` | Update submission status or submission timestamp | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/submissions/{submission_id}/answers` | Add student answer (validates question & marks bounds) | `201 Created` / `409 Conflict` / `422 Unprocessable` |
| `PATCH` | `/api/v1/submissions/{submission_id}/answers/{answer_id}` | Update answer text or awarded marks | `200 OK` / `404 Not Found` / `422 Unprocessable` |
| `GET` | `/api/v1/submissions/{submission_id}/answers` | List answers for submission (paginated) | `200 OK` / `404 Not Found` |

### 6. Scanned Answer Sheet Uploads & Downloads
| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/submissions/{submission_id}/answer-sheets` | Upload scanned answer sheet (`multipart/form-data`) | `201 Created` / `404 Not Found` / `413 Payload Too Large` / `415 Unsupported Media Type` |
| `GET` | `/api/v1/submissions/{submission_id}/answer-sheets?limit=20&offset=0` | List uploaded answer sheet metadata for a submission (paginated) | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/answer-sheets/{upload_id}` | Retrieve metadata for an uploaded answer sheet | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/answer-sheets/{upload_id}/file` | Download the stored answer sheet file | `200 OK` / `404 Not Found` |

#### File Validation & Security Safeguards
- **Supported Formats**: PDF (`application/pdf`), JPEG (`image/jpeg`), and PNG (`image/png`).
- **Signature & Magic Byte Verification**: Validates initial file bytes (`%PDF-`, `\xff\xd8\xff`, `\x89PNG\r\n\x1a\n`) against the declared MIME type. Rejecting files where the extension, Content-Type, or byte signatures mismatch (`415 Unsupported Media Type`).
- **Size Limit Enforcement**: Configurable max upload size (default 15 MB via `MAX_UPLOAD_SIZE_BYTES`). Checked on chunks during streaming to prevent loading entire large files into memory. Excess files trigger `413 Content Too Large` and are cleaned up immediately.
- **Path Traversal & Arbitrary Overwrite Protection**: The user-supplied filename is never used as the storage path. Server generates random UUIDv4 filenames stored inside the configured `UPLOAD_DIR`. Target paths are checked with `.is_relative_to(upload_dir)`.
- **Database Consistency & Rollback**: Metadata is stored in the database (`answer_sheet_uploads` table), keeping binary content off the database. If database persistence fails after writing the file, the stored file is automatically removed from disk.
- **Data Privacy**: Internal filesystem paths are never exposed in API response schemas or public error messages. Raw file contents and sensitive student answers are never logged.

#### Local Storage Limitations
- **Single-Host Bound**: Local filesystem storage stores files on the local disk. It does not synchronize across multi-instance or horizontal auto-scaling clusters without a distributed or mounted volume.
- **Container Ephemerality**: In containerized deployments (Docker/Kubernetes), local uploads will be lost upon container restart unless mapped to a persistent volume (e.g. PV/PVC) or migrated to object storage (e.g. Google Cloud Storage or AWS S3).
- **Backup & Disaster Recovery**: Requires host-level backup scripts or volume snapshots.

#### Example Upload & Download Requests
```bash
# 1. Upload a scanned answer sheet to submission 1
curl -X POST http://127.0.0.1:8000/api/v1/submissions/1/answer-sheets \
  -F "file=@/path/to/student_sheet.pdf;type=application/pdf"

# 2. List answer sheets for submission 1
curl -X GET http://127.0.0.1:8000/api/v1/submissions/1/answer-sheets

# 3. Retrieve metadata for upload 1
curl -X GET http://127.0.0.1:8000/api/v1/answer-sheets/1

# 4. Download the stored file
curl -X GET http://127.0.0.1:8000/api/v1/answer-sheets/1/file -o downloaded_sheet.pdf
```

### 7. OCR Processing Pipeline
| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/answer-sheets/{upload_id}/process` | Trigger asynchronous OCR processing | `202 Accepted` / `404 Not Found` / `409 Conflict` |
| `GET` | `/api/v1/answer-sheets/{upload_id}/processing-status` | Get current processing status and error codes | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/answer-sheets/{upload_id}/extraction` | Retrieve extracted text and structured segments | `200 OK` / `404 Not Found` |

#### Pipeline Architecture & State Machine
The OCR processing pipeline foundation decouples raw file storage from OCR/VLM text extraction:
1. **Processing States**:
   - `uploaded`: File has been validated and saved to disk.
   - `queued`: Background extraction task scheduled.
   - `processing`: OCR adapter actively reading and extracting content.
   - `extracted`: Extraction succeeded with sufficient confidence.
   - `needs_review`: Extraction completed but resulted in low confidence (< threshold) or empty text.
   - `failed`: File was inaccessible or adapter execution failed.
2. **Valid State Transitions**:
   - `uploaded` → `queued`, `processing`, `failed`
   - `queued` → `processing`, `failed`
   - `processing` → `extracted`, `needs_review`, `failed`
   - `extracted` → `queued`, `needs_review`
   - `needs_review` → `queued`, `extracted`
   - `failed` → `queued`
   - Illegal state jumps (e.g. `processing` → `uploaded` or `uploaded` → `extracted`) are rejected with `InvalidStateTransitionError`.
3. **Concurrency Guard**:
   - Triggering processing on an upload currently in `queued` or `processing` status returns `409 Conflict` to prevent duplicate concurrent runs.
4. **Provider-Independent Adapter System**:
   - Abstract base class `BaseOCRAdapter` defines `extract(file_path: Path) -> OCRExtractionData`.
   - `PaddleOCRAdapter` (`OCR_PROVIDER="paddleocr"`): Real OCR engine utilizing PaddleOCR with CPU support for physical printed and handwritten documents. Multi-page PDFs are rendered to high-resolution images via `pypdfium2`, scanned per page, and compiled with page numbers, bounding boxes, and per-segment confidence scores.
   - `MockOCRAdapter` (`OCR_PROVIDER="mock"`): Deterministic adapter for local unit testing and CI without downloading heavy weights. Supports synthetic triggers (`MOCK_TRIGGER_EMPTY`, `MOCK_TRIGGER_LOW_CONFIDENCE`, `MOCK_TRIGGER_ERROR`).
   - Provider factory selected dynamically via `OCR_PROVIDER` (`paddleocr` | `mock`). Failures in real OCR never silently fall back to mock output.
5. **Quality Review Routing**:
   - If extracted text is empty or confidence falls below `OCR_LOW_CONFIDENCE_THRESHOLD` (default 0.6), the status transitions to `needs_review` with an explicit `error_code` (`EMPTY_EXTRACTION` or `LOW_CONFIDENCE`).
6. **Task Execution Note**:
   - For local development, processing runs via FastAPI `BackgroundTasks` (in-process asynchronous worker).
   - *Limitation*: In-process background tasks are volatile and will be interrupted if the server process restarts. For high-volume production deployments, replace with a durable distributed broker/queue (e.g., Celery with Redis/RabbitMQ or Google Cloud Tasks).

#### Example OCR Processing Requests
```bash
# 1. Trigger OCR processing
curl -X POST http://127.0.0.1:8000/api/v1/answer-sheets/1/process

# 2. Check processing status
curl -X GET http://127.0.0.1:8000/api/v1/answer-sheets/1/processing-status

# 3. Retrieve extraction results
curl -X GET http://127.0.0.1:8000/api/v1/answer-sheets/1/extraction
```

---

## 8. Answer Matching & Teacher Review Workflow

The backend provides a deterministic, provider-independent Answer Matching Service and a Teacher Review/Correction workflow for digitizing scanned handwritten student answer sheets.

### Architecture & Non-Destructive Principles

1. **Non-Destructive Matching**:
   - `OCRExtraction` records and structured OCR segments are preserved verbatim and never mutated.
   - Matching never directly modifies or overwrites an existing `QuestionAnswer.answer_text` that was manually entered or previously reviewed.
   - Proposals are persisted in a separate `proposed_answers` table with foreign key linkage to the source upload, OCR extraction, submission, and assessment question.
2. **Deterministic Matching Rules**:
   - **Label Extraction**: Scans segments for explicit question number keys (`question_number`) or standard numbering patterns (`"Question 1:"`, `"Q1."`, `"1."`, `"1)"`, `"Ans 1:"`).
   - **Order Reconciliation**: Sequenced numbers `1..N` map strictly to assessment questions ordered deterministically by question ID (`Question.id.asc()`).
   - **Duplicate Handling**: If multiple segments claim the same question number, all segments are flagged with `needs_review` (`rejection_reason="DUPLICATE_QUESTION_NUMBER"`).
   - **Out-of-Bounds Rejection**: If a detected question number `k` is less than 1 or exceeds total assessment questions `N`, it is flagged with `unmatched` (`rejection_reason="QUESTION_NUMBER_OUT_OF_BOUNDS"`).
   - **Missing Numbers**: Segments without any detected number are marked `unmatched` (`rejection_reason="NO_QUESTION_NUMBER_DETECTED"`).
   - **Existing Answer Protection**: If an authoritative `QuestionAnswer` already has non-empty text, the proposal status becomes `needs_review` (`rejection_reason="EXISTING_ANSWER_PRESENT"`) to prevent silent overwrites.
   - **Low OCR Confidence**: Segments with OCR confidence below threshold are flagged `needs_review` (`rejection_reason="LOW_OCR_CONFIDENCE"`).
   - **Foreign Question Prevention**: Validates that target questions strictly belong to the submission's assessment. Cross-assessment mappings are rejected with HTTP 422.
3. **Explicit Uncertainty & Unanswered Visibility**:
   - The matching response explicitly separates cleanly matched proposals, items requiring human review (`needs_review`), unmapped segments (`unmatched_segments`), and questions not covered by the answer sheet (`unanswered_questions`).
4. **Teacher Review & Audit Trail**:
   - **Approval** (`POST /api/v1/proposed-answers/{id}/approve`): Writes proposed answer text to authoritative `QuestionAnswer.answer_text` and logs a `teacher_reviews` audit record.
   - **Correction** (`POST /api/v1/proposed-answers/{id}/correct`): Sets `proposed_answers.corrected_text`, preserves original OCR text in `proposed_answers.proposed_text`, updates authoritative `QuestionAnswer.answer_text` with corrected text, and records both original and final text in `teacher_reviews`.
   - **Rejection** (`POST /api/v1/proposed-answers/{id}/reject`): Sets status to `rejected`. Authoritative `QuestionAnswer` is not modified.
   - **Audit Record**: Every action records `reviewer_id`, `action`, `original_text`, `final_text`, `review_notes`, and UTC timestamp.
5. **Temporary Reviewer Identity Notice**:
   - Authentication is not yet implemented. Review endpoints currently accept an explicit `reviewer_id` in request payloads, validating that the user exists and holds the `teacher` role.
   - *Temporary limitation*: This is an unauthenticated development mechanism and must be replaced with secure JWT/OAuth2 token claims before production deployment.

### Proposal Status Transitions

```
[ proposed ] ──────┬───> [ approved ]
                   ├───> [ corrected ]
                   └───> [ rejected ]

[ needs_review ] ──┬───> [ approved ]
                   ├───> [ corrected ]
                   └───> [ rejected ]

[ unmatched ] ─────┬───> [ approved ] (with explicit question assignment)
                   ├───> [ corrected ] (with explicit question assignment)
                   └───> [ rejected ]
```

### Example Matching & Review Requests

```bash
# 1. Trigger matching for a submission
curl -X POST http://127.0.0.1:8000/api/v1/submissions/1/match-answers

# 2. Trigger matching directly for an answer sheet upload
curl -X POST http://127.0.0.1:8000/api/v1/answer-sheets/1/match-answers

# 3. Retrieve proposed answers, unmatched segments, and unanswered questions
curl -X GET http://127.0.0.1:8000/api/v1/submissions/1/proposed-answers

# 4. Teacher approves a proposed answer
curl -X POST http://127.0.0.1:8000/api/v1/proposed-answers/1/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewer_id": 1, "review_notes": "Clean answer matching Q1"}'

# 5. Teacher corrects answer text and approves
curl -X POST http://127.0.0.1:8000/api/v1/proposed-answers/2/correct \
  -H "Content-Type: application/json" \
  -d '{"reviewer_id": 1, "corrected_text": "f'\''(x) = 2x by the power rule", "review_notes": "Fixed notation"}'

# 6. Teacher rejects a proposed answer
curl -X POST http://127.0.0.1:8000/api/v1/proposed-answers/3/reject \
  -H "Content-Type: application/json" \
  -d '{"reviewer_id": 1, "rejection_reason": "Irrelevant scratch notes"}'
```

---

## 9. AI Assessment & Misconception Evaluation Engine

The backend provides a provider-independent AI Assessment and Misconception Evaluation Engine designed to analyze teacher-approved student answers, identify conceptual grasp, detect evidence-based misconceptions, and support human-in-the-loop teacher review.

### Core Safety and Architectural Principles

1. **Strict Authoritative Answer Precondition**:
   - The engine **only** analyzes authoritative `QuestionAnswer.answer_text` records that have been explicitly approved or corrected by a teacher (`TeacherReview` audit trail or approved `ProposedAnswer`).
   - Unreviewed or pending proposals are strictly barred from evaluation (HTTP 422). Student work is never evaluated in an unverified state.
2. **Non-Destructive Invariant**:
   - The evaluation engine is purely observational. It **never mutates** `QuestionAnswer.answer_text`, `OCRExtraction`, `ProposedAnswer`, or `TeacherReview` records.
3. **Evidence-Based Findings (Hypotheses, Not Diagnoses)**:
   - Misconception findings are treated as evidence-backed hypotheses, never definitive diagnoses.
   - Every finding requires a verbatim `evidence_excerpt` from the student's answer (or `None` for insufficient evidence) and a pedagogical `rationale` explaining how that excerpt demonstrates the concept or misconception.
   - Psychological, demographic, or personal assumptions about the student are strictly prohibited.
4. **Anti-Hallucination & Fabricated Standards Prevention**:
   - If a question lacks a teacher-provided `rubric` or `expected_answer`, the evaluator refuses to fabricate standards and returns `insufficient_evidence` with an explanation.
   - If the student answer is blank or purely whitespace, the evaluator returns `insufficient_evidence`.
5. **Exact Answer-Version Provenance & Immutability**:
   - Every evaluation run records `answer_text_hash` (SHA-256) and an immutable `answer_text_snapshot`.
   - If a teacher later corrects an answer text, the new text has a different SHA-256 hash. Re-evaluating generates a distinct versioned `EvaluationRun`, preserving the original run and audit history for complete provenance.
   - Re-triggering evaluation for an unchanged answer text version is idempotent (returns existing run without duplicate work).
6. **Finding Categories**:
   - `correct_understanding`: Student's answer demonstrates solid grasp matching the expected rubric criteria.
   - `partially_correct_understanding`: Student demonstrates partial conceptual grasp but misses necessary components or misapplies minor rules.
   - `likely_misconception`: Student makes a systematic conceptual error with concrete evidence (e.g. confusing product rule with sum rule in differentiation).
   - `insufficient_evidence`: Student answer is missing/empty, or the question lacks teacher rubric/expected answer context.
7. **Bounded Confidence & Uncertainty**:
   - Every finding includes a bounded confidence score `[0.0, 1.0]` accompanied by an explicit `uncertainty_rationale` explaining why confidence was assigned.
8. **Evaluator Providers (VLLM & Mock)**:
   - **VLLM Evaluator** (`EVALUATOR_PROVIDER=vllm`): OpenAI-compatible HTTP adapter connecting to a local VLLM server (e.g. running `vllm serve Qwen/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 8000`). Sends minimal question, rubric, and student answer context with strict structured JSON schema validation. Enforces evidence-quote grounding by verifying cited excerpts verbatim in submitted student text; hallucinated quotes are rejected and flagged.
   - **Mock Evaluator** (`EVALUATOR_PROVIDER=mock`): Deterministic pattern fixtures for local development and CI testing without running external LLM processes.
   - Evaluator factory strictly selects configured providers; errors in VLLM never silently fall back to mock findings.

### Teacher Finding Review & Audit Trail

Teachers can accept, reject, or request revision on any individual conceptual finding:
- **Accepted** (`FindingReviewAction.ACCEPT`): Confirms the finding and marks it accepted with teacher notes.
- **Rejected** (`FindingReviewAction.REJECT`): Rejects the finding (cannot transition directly to accepted; must go through `needs_revision` first).
- **Needs Revision** (`FindingReviewAction.REQUEST_REVISION`): Flags the finding for further teacher or AI refinement.
- **Audit Logging**: Every action writes an immutable record to `finding_review_audits` capturing `reviewer_id`, `action`, `review_notes`, and UTC timestamp.
- **Temporary Reviewer Identity**: Currently accepts `reviewer_id` in payload, validating that the user exists and holds the `teacher` role. (Temporary unauthenticated pattern; will be replaced with JWT tokens in future authentication work).

### Evaluation Endpoints

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/submissions/{submission_id}/evaluate` | Batch evaluate all teacher-approved answers for submission | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/submissions/{submission_id}/questions/{question_id}/evaluate` | Evaluate single teacher-approved question answer (idempotent) | `200 OK` / `404 Not Found` / `422 Unprocessable` |
| `GET` | `/api/v1/submissions/{submission_id}/evaluations` | List all evaluation runs and findings for submission | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/submissions/{submission_id}/questions/{question_id}/evaluations` | List evaluation runs for specific question | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/evaluations/runs/{run_id}` | Retrieve specific evaluation run with findings and provenance | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/evaluations/findings/{finding_id}/review` | Teacher review of a finding (`accepted`, `rejected`, `needs_revision`) | `200 OK` / `404 Not Found` / `422 Unprocessable` |

### Example Evaluation Requests

```bash
# 1. Trigger evaluation for a single question answer
curl -X POST http://127.0.0.1:8000/api/v1/submissions/1/questions/1/evaluate

# 2. Trigger batch evaluation for entire submission
curl -X POST http://127.0.0.1:8000/api/v1/submissions/1/evaluate

# 3. Retrieve evaluation runs and findings for a submission
curl -X GET http://127.0.0.1:8000/api/v1/submissions/1/evaluations

# 4. Retrieve single run details
curl -X GET http://127.0.0.1:8000/api/v1/evaluations/runs/1

# 5. Teacher reviews and accepts a conceptual finding
curl -X POST http://127.0.0.1:8000/api/v1/evaluations/findings/1/review \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_id": 1,
    "action": "accepted",
    "review_notes": "Confirmed student confused product rule with sum rule."
  }'

# 6. Teacher requests revision on a finding
curl -X POST http://127.0.0.1:8000/api/v1/evaluations/findings/1/review \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_id": 1,
    "action": "needs_revision",
    "review_notes": "Check if student applied product rule correctly in part b."
  }'
```

---

## 10. Targeted Follow-up Question & Remediation Generation Service

The backend provides a provider-independent Targeted Follow-up Question & Remediation Generation Service. It consumes teacher-approved misconception evaluation findings to synthesize grounded practice items for remediation while enforcing human-in-the-loop review.

### Architecture & Learning Safety Principles

1. **Strict Finding Eligibility Precondition**:
   - Practice items can **only** be generated from evaluation findings that have been explicitly accepted by a teacher (`review_status='accepted'`).
   - Findings in `pending_review`, `rejected`, or `needs_revision` status are blocked with HTTP 422.
   - Findings categorized as `insufficient_evidence` are strictly blocked from generating practice, even if reviewed.
2. **Practice Items, Not Replacements**:
   - Generated questions are formative practice items designed to remediate specific conceptual gaps. They never replace, overwrite, or mutate original assessment questions or student answers.
3. **Anti-Hallucination & Grounding**:
   - Practice questions must be grounded in the question prompt, teacher rubric, and expected answer.
   - If rubric/expected answer or prompt context is missing, the generator refuses to fabricate standards and returns status `insufficient_context` with 0 practice items.
4. **Answer Key Separation & Student-Facing Boundary**:
   - Student prompts never leak the expected answer or solution steps.
   - `teacher_answer_key` and pedagogical `teacher_rationale` are stored in separate fields and strictly withheld from student-facing responses (`RemediationItemStudentRead`).
5. **Supported Practice Formats**:
   - `multiple_choice`: Includes options list (`["A) ...", "B) ..."]`) targeting common distractors.
   - `short_answer`: Standard open-ended question targeting a formula or application.
   - `explain_reasoning`: Counterexample or conceptual analysis prompting students to explain why an erroneous rule fails.
6. **Provenance & Idempotency**:
   - Every `RemediationRun` and `RemediationItem` links directly to `finding_id` and `evaluation_run_id`.
   - Generation is idempotent: triggering generation for a finding that already has an active run returns the existing completed run without duplicate database records.
7. **Teacher Review & Edit Invariant**:
   - All generated items are `pending_review` by default and must be approved before student delivery.
   - Teachers can `approve`, `reject`, or `edit` practice items (`POST /api/v1/remediations/items/{id}/review`).
   - When a teacher edits an item, the original generated text in `question_text` is preserved untouched; teacher edits are saved in `edited_question_text` and `edited_answer_key`.
   - Every review action records an immutable audit entry in `remediation_item_audits`.
8. **Deterministic Mock Generator Notice**:
   - **MOCK PROVIDER NOTICE**: Local development and testing uses `MockRemediationGenerator` (`REMEDIATION_PROVIDER=mock`). It utilizes deterministic pattern fixtures and does **not** perform real AI/LLM generation. Real external LLM providers will implement `BaseRemediationGenerator` in future development.

### Remediation Endpoints

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/findings/{finding_id}/remediation/generate` | Trigger practice item generation for an accepted finding (idempotent) | `200 OK` / `404 Not Found` / `422 Unprocessable` |
| `GET` | `/api/v1/findings/{finding_id}/remediations` | List generated practice items for an evaluation finding | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/submissions/{submission_id}/remediations` | List generated practice items across all findings for a submission | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/remediations/runs/{run_id}` | Retrieve a generation run with items and audit provenance | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/remediations/items/{item_id}` | Retrieve a single practice item (teacher view) | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/remediations/items/{item_id}/review` | Teacher review of a practice item (`approve`, `reject`, `edit`) | `200 OK` / `404 Not Found` / `422 Unprocessable` |

### Example Remediation Requests

```bash
# 1. Trigger remediation generation for an accepted finding
curl -X POST http://127.0.0.1:8000/api/v1/findings/1/remediation/generate

# 2. List generated practice items for a finding
curl -X GET http://127.0.0.1:8000/api/v1/findings/1/remediations

# 3. Retrieve run details with provenance
curl -X GET http://127.0.0.1:8000/api/v1/remediations/runs/1

# 4. Teacher edits a generated practice item
curl -X POST http://127.0.0.1:8000/api/v1/remediations/items/1/review \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_id": 1,
    "action": "edit",
    "edited_question_text": "What is the derivative of h(x) = sin(x) * cos(x) under the product rule?",
    "edited_answer_key": "cos^2(x) - sin^2(x)",
    "review_notes": "Added trigonometric context."
  }'

# 5. Teacher approves the edited practice item
curl -X POST http://127.0.0.1:8000/api/v1/remediations/items/1/review \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_id": 1,
    "action": "approve",
    "review_notes": "Approved for student practice."
  }'
```

---

## Running Automated Tests

Run pytest with the virtual environment:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -v
```

Or from the project root:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -v
```

---

## 11. Backend Integration & Provenance Audit Summary

### Verified End-to-End Workflow Status
The LearnGraph backend pipeline consists of 8 interconnected stages. Each stage strictly relies on authoritative parent data and maintains cryptographic hashes, snapshots, and foreign-key provenance across database records:

1. **Upload**: Scanned student answer sheets are accepted via `POST /api/v1/submissions/{id}/answer-sheets`, undergoing magic-byte content validation, maximum size bounds checking, unique storage filename generation, and SHA-256 checksum persistence.
2. **OCR Extraction**: Provider-independent OCR adapter extracting raw text and structured segments into `ocr_extractions`. (Currently runs offline `mock_ocr_provider`).
3. **Answer-to-Question Matching**: Deterministic matching parses numbered segments (e.g. `Question 1:`, `2.`, `3)`) into `proposed_answers` with OCR and matching confidence scores. Rejects cross-assessment question matching (HTTP 422).
4. **Teacher Review & Approval**: Teachers explicitly approve or correct proposed answers via `POST /api/v1/proposed-answers/{id}/approve` or `/correct`. Only approved/corrected text is written into authoritative `question_answers.answer_text`, while original OCR proposed text is preserved in immutable `teacher_reviews` audit records.
5. **AI Assessment & Misconception Evaluation**: Triggered via `POST /api/v1/submissions/{id}/questions/{qid}/evaluate`. Only teacher-reviewed authoritative answers are evaluated. Computes SHA-256 hash and snapshot of `answer_text` to guarantee idempotency and provenance. (Currently runs offline `mock_evaluator`).
6. **Finding Review**: Teachers review conceptual findings via `POST /api/v1/evaluations/findings/{id}/review` (`accept`, `reject`, `needs_revision`), maintaining an immutable audit log in `finding_review_audits`.
7. **Targeted Follow-up Question & Remediation Generation**: Triggered via `POST /api/v1/findings/{id}/remediation/generate`. Strictly requires teacher-accepted findings (`review_status='accepted'`) and rejects `insufficient_evidence` findings. Enforces anti-hallucination standards requiring prompt and teacher rubric context. Generates formative practice items without mutating authoritative answers or evaluation records. (Currently runs offline `mock_remediation_generator`).
8. **Remediation Practice Item Review**: Teachers approve, edit, or reject practice items via `POST /api/v1/remediations/items/{id}/review`. Preserves original generated text in `question_text` and records teacher edits in `edited_question_text` and `edited_answer_key` with immutable audit logging in `remediation_item_audits`.

---

## 12. Step 11: JWT Authentication & Role-Based Access Control (RBAC)

LearnGraph now implements a production-grade authentication and Role-Based Access Control (RBAC) system using signed JSON Web Tokens (JWT) and `bcrypt` password hashing.

### Authentication & Secrets Configuration
Environment variables configure secrets, hashing, and token lifetimes in `.env`:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `JWT_SECRET_KEY` | *(Configured in .env)* | 256-bit cryptographically secure signing secret. Never hardcoded or logged. |
| `JWT_ALGORITHM` | `HS256` | Digital signature algorithm used for token signing and verification. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT token validity window in minutes. |

### Password Storage Security
- Passwords are encrypted before database insertion using `bcrypt` (`bcrypt>=4.0.0`) with automatic salt generation.
- Passwords and password hashes are **never** logged or returned in user responses (`UserRead` strictly omits `password` and `hashed_password`).

### Authentication API Endpoints

| Method | Endpoint | Description | Auth Required | Status Code |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Register a new user (`student`, `teacher`, or `admin`) | None | `201 Created` / `400 Bad Request` |
| `POST` | `/api/v1/auth/login` | Authenticate with JSON credentials (`email`, `password`) | None | `200 OK` / `401 Unauthorized` / `403 Forbidden` |
| `POST` | `/api/v1/auth/token` | Standard OAuth2 Password Form flow (`username`, `password`) | None | `200 OK` / `401 Unauthorized` |
| `GET` | `/api/v1/auth/me` | Retrieve current authenticated user profile and roles | Bearer Token | `200 OK` / `401 Unauthorized` |

#### Token Flow Example:
```bash
# 1. Register a teacher
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Prof. Turing", "email": "turing@learngraph.edu", "password": "SecretPassword123!", "role": "teacher"}'

# 2. Login to obtain JWT Bearer token
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "turing@learngraph.edu", "password": "SecretPassword123!"}'

# 3. Use token in Authorization header for authenticated requests
curl -X GET http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### Elimination of Caller-Supplied Identity
In Step 11, all vulnerable caller-supplied identity parameters were completely removed from schemas and API contracts:
- **Assessment Creation (`POST /api/v1/assessments`)**: `created_by` removed from request schema. Assessment creator is derived strictly from the authenticated teacher token (`current_user.id`).
- **Submission Creation (`POST /api/v1/assessments/{id}/submissions`)**: `student_id` removed from request schema. Submission student is derived strictly from the authenticated student token (`current_user.id`). Teachers and admins cannot create student submissions (HTTP 403).
- **Teacher Review Actions (`/approve`, `/correct`, `/reject`, `/findings/{id}/review`, `/remediations/items/{id}/review`)**: `reviewer_id` removed from all review request schemas. Reviewer identity recorded in audit trails is derived strictly from the authenticated teacher token (`current_user.id`).
- Any spoofed `created_by`, `student_id`, or `reviewer_id` in request payloads is ignored by FastAPI Pydantic parsing and never trusted.

### Role-Based Access Control (RBAC) & Ownership Rules

| Resource & Operation | Role Allowed | Ownership & Access Rule |
| :--- | :--- | :--- |
| **Topics** (`POST`, `PUT`, `DELETE`) | Teacher, Admin | Teachers and admins manage curriculum topics. Students cannot modify topics (403). |
| **Assessments** (`POST`) | Teacher, Admin | Creates assessment with `created_by = current_user.id`. Students denied (403). |
| **Assessments** (`PATCH`, `DELETE`) | Teacher, Admin | Only the creator teacher or an admin can update or delete an assessment (403 for other teachers). |
| **Questions** (`POST`, `PUT`, `DELETE`) | Teacher, Admin | Only the assessment creator teacher or an admin can add/edit questions (403 for other teachers). |
| **Submissions** (`POST`) | Student | Only students can create exam submissions for themselves. |
| **Submissions & Answers** (`GET`) | Student, Teacher, Admin | Students can only access their own submissions (403 for other students' submissions). Teachers and admins can view any. |
| **Uploads & Answer Sheets** (`POST`, `GET`, `/file`) | Student, Teacher, Admin | Students can only upload, list, or download files for their own submissions (403 for other students). |
| **OCR Processing & Extraction** (`/process`, `/extraction`) | Student, Teacher, Admin | Students can only trigger OCR and view extraction for their own submissions. |
| **Answer Matching Proposals** (`/match-answers`, proposals) | Teacher, Admin | Teacher-only operation (403 for students). |
| **Answer Review & Approval** (`/approve`, `/correct`, `/reject`) | Teacher, Admin | Teacher-only operation. Reviewer identity derived from token. |
| **AI Evaluations** (`/evaluate`, findings review) | Teacher, Admin | Evaluating answers and reviewing findings are strictly teacher-only. |
| **Remediation Practice Items** (`/generate`, `/remediations`, `/review`) | Teacher, Admin | Strictly teacher-only to protect confidential answer keys and rationales. |

### Data Privacy Protections (Teacher Answer Keys & Rationales)
- Remediation routes (`GET /api/v1/remediations/runs/{id}`, `GET /api/v1/findings/{id}/remediations`, `GET /api/v1/submissions/{id}/remediations`, and `GET /api/v1/remediations/items/{id}`) contain `teacher_answer_key`, `teacher_rationale`, and teacher review notes.
- In Step 11, these endpoints are gated behind `require_teacher` dependencies. Student attempts to access remediation items are rejected with HTTP 403 Forbidden.
- Unauthenticated requests to any evaluation or remediation endpoints return HTTP 401 Unauthorized.

### Automated Test Coverage
The backend test suite comprises **105 automated tests** (all passing):
- `test_api_crud.py` (6 tests): Learning topics, assessments, and questions CRUD with teacher authorization.
- `test_audit_and_consistency.py` (5 tests): Non-destructive provenance chain, cross-record integrity, error sanitization, and caller-identity boundary resolution.
- `test_auth_and_rbac.py` (12 tests): Bcrypt hashing, registration, login success/failure, OAuth2 form flow, `/auth/me`, invalid/expired tokens, student role denial, teacher submission denial, cross-student ownership denial, cross-teacher assessment ownership denial, spoofed identity ignoring, and teacher answer-key privacy.
- `test_evaluation_engine.py` (11 tests): Evaluation pipeline, answer snapshot hashing, idempotency, and teacher finding review.
- `test_file_upload.py` (12 tests): Answer sheet uploads, size limits, magic bytes, secure storage paths, and download security.
- `test_health.py` (3 tests): Health check and database connectivity.
- `test_matching_and_review.py` (12 tests): OCR segment matching, confidence metrics, and teacher approval/correction.
- `test_models.py` (6 tests): ORM models, relationships, foreign keys, cascades, and migration schema validation.
- `test_ocr_pipeline.py` (10 tests): OCR state transitions, mock adapter, and background task execution.
- `test_practice_sessions.py` (12 tests): Approved item delivery filtering, student data privacy before and after submission, deterministic scoring, full provenance persistence, duplicate answer rejection (409), cross-session foreign item rejection (422), ownership authorization (403), explicit state transitions, auto-completion, formative summary with non-mastery disclaimer, and non-destructive behavior.
- `test_remediation_service.py` (10 tests): Remediation generation, grounding in teacher rubrics, and practice item review.
- `test_submissions.py` (6 tests): Student submission lifecycles, answers, and awarded marks.

---

## 13. Step 12: Student Practice Session & Safe Delivery

LearnGraph provides an authenticated student practice session engine delivering teacher-approved remediation items with strict data privacy boundaries, deterministic scoring, full audit provenance, and explicit state management.

### Architecture & Delivery Invariants

1. **Teacher-Approved Delivery Guarantee**:
   - Practice items can **only** be delivered if their review status is explicitly `approved` (`review_status == 'approved'`) and their originating finding was accepted by a teacher (`review_status == 'accepted'`).
   - Items with status `pending_review`, `rejected`, or `edited` (edited by a teacher but not yet approved) are strictly excluded from delivery.
   - If a teacher has edited an approved item, the effective student prompt (`edited_question_text or question_text`) and effective grading key (`edited_answer_key or teacher_answer_key`) are automatically resolved.

2. **Strict Identity Context & Ownership**:
   - Student identity is derived exclusively from the authenticated JWT bearer token (`current_user.id`).
   - The API **never** accepts a client-supplied `student_id` in request payloads.
   - Students can only initiate, view, and respond to practice sessions tied to their own exam submissions. Any attempt to access another student's session returns HTTP 403 Forbidden.
   - Only the student who owns the practice session can submit responses (teachers/admins and other students are denied with HTTP 403).

3. **Data Privacy Boundary (Confidential Teacher Data Protection)**:
   - **Before Submission**: Delivered practice items (`PracticeSessionItemRead`) strictly suppress `teacher_answer_key`, `teacher_rationale`, `uncertainty_note`, `review_notes`, and reviewer details.
   - **After Submission**: Response objects (`PracticeResponseRead`) return student answer, score, correctness, and pedagogical guidance (`feedback`), but **never** reveal internal teacher notes, uncertainty notes, or raw teacher rationales.

4. **Deterministic Scoring & Safe Feedback**:
   - Scoring is deterministic and transparent:
     - `multiple_choice`: Normalized option matching (e.g. "A" vs "A) ...").
     - `short_answer`: Normalized text and key substring matching.
     - `explain_reasoning`: Non-trivial length requirement combined with conceptual terminology matching.
   - Feedback strings provide pedagogical guidance tailored to the target concept without exposing sensitive teacher notes.

5. **Single-Submission Invariant & Duplicate Prevention**:
   - Within a practice session, a student can submit an answer to each remediation item exactly once.
   - Resubmitting an answer for an already answered item in the session is rejected with HTTP 409 Conflict via database unique constraint `uq_practice_session_item_response(session_id, remediation_item_id)`.
   - Submitting an item from a different submission or an unapproved item is rejected with HTTP 422 Unprocessable Content.

6. **Audit Provenance**:
   - Every `PracticeResponse` maintains full provenance links to:
     - `session_id`: Practice session context.
     - `remediation_item_id`: Specific practice question.
     - `finding_id`: Root diagnostic misconception finding.
     - `evaluation_run_id`: AI evaluation execution.
     - `student_answer`: Exact text entered by the student.
     - `score`, `is_correct`, `feedback`, `submitted_at`: Deterministic evaluation audit.

7. **Explicit State Transitions & Auto-Completion**:
   - Allowed session statuses: `active`, `completed`, `abandoned`.
   - Transitions are explicitly validated (`VALID_PRACTICE_SESSION_TRANSITIONS`):
     - `active` → `completed` (explicit or automatic upon answering all items).
     - `active` → `abandoned`.
     - `completed` → no transitions permitted.
     - `abandoned` → no transitions permitted.
   - Submitting answers to a session that is `completed` or `abandoned` is rejected with HTTP 422.
   - When all deliverable items in a session have been answered, the session automatically records `completed_at` and transitions status to `completed`.

8. **Transparent Formative Progress & Non-Mastery Disclaimer**:
   - `GET /api/v1/practice-sessions/{session_id}/summary` returns total items, completed items, correct count, accuracy percentage, and concept-level evidence breakdowns.
   - **Pedagogical Disclaimer**: Scores represent formative practice exercise evidence and do **not** make unsupported claims of certified concept mastery or adaptive learning from a single response.

### Practice Session Endpoints

| Method | Endpoint | Description | Auth Required | Status Code |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/submissions/{submission_id}/practice-sessions` | Start or resume an active practice session for a submission | Student Owner, Teacher, Admin | `201 Created` / `403 Forbidden` / `404 Not Found` / `422 Unprocessable` |
| `GET` | `/api/v1/submissions/{submission_id}/practice-sessions` | List practice sessions for a submission | Student Owner, Teacher, Admin | `200 OK` / `403 Forbidden` / `404 Not Found` |
| `GET` | `/api/v1/practice-sessions/{session_id}` | Retrieve practice session details with items and safe responses | Student Owner, Teacher, Admin | `200 OK` / `403 Forbidden` / `404 Not Found` |
| `POST` | `/api/v1/practice-sessions/{session_id}/responses` | Submit an answer to an approved remediation practice item | Student Owner Only | `201 Created` / `403 Forbidden` / `404 Not Found` / `409 Conflict` / `422 Unprocessable` |
| `GET` | `/api/v1/practice-sessions/{session_id}/summary` | Retrieve formative scoring summary and concept progress | Student Owner, Teacher, Admin | `200 OK` / `403 Forbidden` / `404 Not Found` |
| `POST` | `/api/v1/practice-sessions/{session_id}/complete` | Mark practice session as completed | Student Owner, Teacher, Admin | `200 OK` / `403 Forbidden` / `404 Not Found` / `422 Unprocessable` |
| `POST` | `/api/v1/practice-sessions/{session_id}/abandon` | Mark practice session as abandoned | Student Owner, Teacher, Admin | `200 OK` / `403 Forbidden` / `404 Not Found` / `422 Unprocessable` |

#### Example Practice Flow:
```bash
# 1. Student initiates practice session for their submission
curl -X POST http://127.0.0.1:8000/api/v1/submissions/1/practice-sessions \
  -H "Authorization: Bearer <STUDENT_TOKEN>"

# 2. View session items (strictly excludes teacher answer keys and rationales)
curl -X GET http://127.0.0.1:8000/api/v1/practice-sessions/1 \
  -H "Authorization: Bearer <STUDENT_TOKEN>"

# 3. Submit answer to an approved practice item
curl -X POST http://127.0.0.1:8000/api/v1/practice-sessions/1/responses \
  -H "Authorization: Bearer <STUDENT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "remediation_item_id": 1,
    "student_answer": "A"
  }'

# 4. View formative summary report with non-mastery disclaimer
curl -X GET http://127.0.0.1:8000/api/v1/practice-sessions/1/summary \
  -H "Authorization: Bearer <STUDENT_TOKEN>"
```

### Current Development State vs Production Readiness
| Capability | Current Verified State | Production Requirement |
| :--- | :--- | :--- |
| **Authentication** | Secure JWT Bearer tokens + Bcrypt password hashing (`app/core/security.py`) | Production-ready (Add refresh token rotation & revocation blacklist if needed) |
| **Authorization & Ownership** | Strict RBAC (`app/api/deps.py`) & entity ownership validation | Production-ready |
| **Student Identity** | Identity derived strictly from token claims (`current_user.id`) | Production-ready |
| **Practice Delivery** | Approved-only items delivered; teacher keys & notes strictly suppressed | Production-ready |
| **Response Provenance** | Full DB linkages to items, findings, and evaluation runs | Production-ready |
| **Scoring Engine** | Deterministic grading for MCQ, short answer, and reasoning | Production-ready (Can augment with LLM semantic evaluation for complex explanations) |
| **OCR Extraction** | Deterministic mock adapter (`MockOCRAdapter`) | External VLM / OCR cloud service or self-hosted OCR engine |
| **Evaluation Engine** | Deterministic rule-based mock (`MockEvaluator`) | Production LLM / AI evaluation provider with latency & error handling |
| **Remediation Engine** | Deterministic template generator (`MockRemediationGenerator`) | Production LLM with few-shot pedagogical alignment |
| **Database** | Local SQLite with foreign key pragmas & Alembic migrations | PostgreSQL database with connection pooling and SSL |
| **Student & Teacher UI** | React 18 + TypeScript + Vite frontend implemented (`frontend/`) | Production-ready MVP interface for all core workflows |

---

## 14. Step 13 Audit: API Contracts, Scoring Edge-Cases & Concurrency Verification

During Step 13, a full architectural audit was conducted across all API routes, authentication/authorization boundaries, scoring algorithms, idempotency mechanisms, and data integrity guarantees.

### 1. API Contract Consistency & Error Sanitization
- **Strict Schema Adherence**: All endpoints conform to declared Pydantic response models. Deprecated `HTTP_422_UNPROCESSABLE_ENTITY` status codes have been modernized to `HTTP_422_UNPROCESSABLE_CONTENT`.
- **Missing & Malformed IDs**:
  - Missing numeric IDs return standard `404 Not Found` with clean user-facing error details.
  - Non-integer or malformed path variables return standard FastAPI `422 Unprocessable Content` validation errors.
  - Cross-resource mismatches (e.g., submitting an answer sheet or practice item belonging to submission A to session B) are rigorously caught and rejected with `422 Unprocessable Content`.
- **Zero Information Leakage**: Exception handlers across all routes sanitize internal database errors, tracebacks, provider configurations, local file system paths, and secrets. Attack surfaces receive standardized RFC 7807/FastAPI error envelopes without revealing environment internals.

### 2. Authorization & Student Privacy Invariants
- **Identity Derivation**: In no endpoint is caller identity trusted from request bodies or parameters. Authenticated identities are strictly extracted from signed JWT Bearer claims via `get_current_user`.
- **Role-Based Access Control (RBAC)**: All administrative, diagnostic, and teacher endpoints enforce `require_teacher` or `require_admin`. Students attempting access receive `403 Forbidden`.
- **Cross-Student Isolation**: Students can query and submit responses only to sessions belonging to their own submissions. Attempting to query another student's session returns `404 Not Found` (to prevent ID enumeration).
- **Teacher Data Suppression**: Response payloads served to students (`StudentPracticeItemRead` and `PracticeResponseRead`) strictly omit teacher answer keys, rationales, diagnostic internal notes, and confidence scores.

### 3. Hardened Practice Scoring Rules & Pedagogical Limitations
The practice scoring engine (`app/services/practice_service.py`) was audited and hardened against subtle false positives and false negatives:
- **MCQ Hardening**:
  - Normalized case, stripped excess whitespace, and removed common prefixes (`"Option "`, `"Choice "`).
  - Isolated option letters to prevent false positives where descriptive answers starting with 'A' (e.g., `"apple"`, `"all of the above"`) incorrectly match expected answer `"A"`.
- **Short Answer Hardening**:
  - Implemented regex word-boundary matching `rf"(?:^|\s){escaped_expected}(?:$|\s)"`, ensuring that `"four"` does not match `"fourteen"` or `"twenty-four"`.
  - Prefix negation detection: If words like `"not"`, `"cannot"`, `"never"`, or `"isn't"` precede the keyword match (e.g., `"not 4"`, `"cannot be 4"`), the answer is marked incorrect.
  - Length ratio ceiling: Short answers exceeding 6x the expected length with irrelevant padding are flagged and marked incorrect.
- **Explain Reasoning Hardening**:
  - Minimum boundary check: Answers shorter than 15 characters are immediately rejected.
  - Non-answer refusal filtering: Regular expressions filter out admissions of ignorance (e.g., `"I don't know"`, `"no idea"`, `"cannot explain"`, `"not sure"`, `"idk"`).
  - Stopword stripping: Common grammatical words (`the`, `is`, `and`, `because`, etc.) cannot satisfy domain keyword requirements.
  - Whole-word set intersection: Requires distinct whole keywords to match (`target_words.intersection(student_words)`), preventing substring confusion (e.g., `"term"` matching `"intermediate"`) and word-repetition attacks (`"rule rule rule"`).
- **Pedagogical Disclaimer**:
  > **Important Limitation**: Deterministic heuristic keyword matching is an educational aid, **not** genuine semantic comprehension or certified mastery. A student can craft grammatically disjointed keywords or conversely explain a concept correctly using unlisted synonyms. The API summary explicitly tags scoring as formative practice evidence.

### 4. Idempotency & Concurrency Verification
- **Session Resumption Idempotency**: Calling `POST /api/v1/submissions/{id}/practice-sessions` repeatedly returns the existing active session rather than generating redundant duplicate sessions.
- **Duplicate Response Submission Protection**:
  - Database unique constraint `uq_practice_session_item_response(session_id, remediation_item_id)` prevents concurrent double-submissions.
  - The service catches SQLAlchemy `IntegrityError`, rolls back the session transaction, and deterministically returns `HTTP 409 Conflict`.
- **Evaluation & Remediation Deduplication**:
  - Re-running an evaluation against an unchanged answer snapshot returns the existing `EvaluationRun` (`is_cached=True`).
  - Generating remediation items against already-grounded findings reuses the current `RemediationRun` rather than re-creating duplicate items.
- **SQLite Concurrency Limitation vs Production**:
  - Tests verify transactional integrity under SQLite's process-level file lock.
  - **Unverified Production Risk**: SQLite does not simulate PostgreSQL multi-process MVCC row-level write races under high connection pool loads. In production, row-level locking (`SELECT ... FOR UPDATE`) or advisory locks must be utilized when transitioning session completion states.

### 5. Data Integrity & Provenance Lifecycle
- **Unbroken Provenance Chain**:
  `PracticeResponse` ➔ `PracticeSession` ➔ `RemediationItem` ➔ `RemediationRun` ➔ `EvaluationFinding` ➔ `EvaluationRun` ➔ `QuestionAnswer` ➔ `TeacherReview` ➔ `ProposedAnswer` ➔ `OCRExtraction` ➔ `AnswerSheetUpload` ➔ `Submission`.
- **Cascade Deletion Behavior**: Deleting a parent `Submission` cascades through SQLite foreign keys (`PRAGMA foreign_keys=ON`) and removes all associated uploads, extractions, reviews, evaluations, remediations, practice sessions, and student responses without orphaned records.
- **Non-Destructive Invariant**: Practice sessions and student responses write strictly to their own operational tables (`practice_sessions`, `practice_responses`) and never mutate historical submissions, question answers, or teacher review records.

---

### Test Suite Execution
Run the full test suite across all 14 test modules (126 tests):
```bash
source .venv/bin/activate
pytest
```
Expected output:
```
126 passed, 18 warnings in ~32s
```




