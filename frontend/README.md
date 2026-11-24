# Inksight Frontend

Functional, responsive React + TypeScript + Vite frontend for Inksight Diagnostic Workspace.

## Tech Stack
- **Framework**: React 18 + TypeScript + Vite
- **Styling**: Vanilla CSS design system with CSS custom properties, responsive cards, accessible status indicators, and clean dark/light contrast
- **Testing**: Vitest for frontend contract and API client tests
- **Authentication**: JWT Bearer tokens with client-side RBAC session management

## Implemented Workflows
1. **Authentication & Role-Aware Navigation**:
   - Seamless sign in and registration (`student`, `teacher`, `admin`)
   - Persistent session storage in `localStorage`
   - Role-gated tabs (students see practice delivery; teachers/admins see curriculum, submissions, review, evaluations, and remediations)
2. **Teacher — Curriculum & Assessments**:
   - Create and browse learning topics
   - Create assessments
   - Add assessment questions with prompts, question types (`short_answer`, `mcq`, `explain_reasoning`), point values, and expected answers
3. **Teacher — Submissions & Answer Sheet OCR**:
   - View student submissions for any assessment
   - Upload scanned answer sheet files (`.pdf`, `.png`, `.jpg`, `.jpeg`)
   - Trigger automated OCR extraction (using backend's mock OCR adapter) and inspect extracted text
4. **Teacher — Answer Matching & Review**:
   - Inspect OCR segment proposals matched to assessment questions
   - Approve, correct (edit text/reassign question), or reject proposals with audit logging
   - View unmatched segments and unanswered questions
5. **Teacher — AI Assessment & Misconceptions**:
   - Trigger AI evaluation runs against authoritative approved answers
   - Review diagnostic findings (misconception type, confidence score, evidence quote, explanation)
   - Accept, flag, or reject findings with teacher notes
6. **Teacher — Remediation Generation & Approval**:
   - Generate targeted follow-up practice items for accepted findings
   - Review generated practice questions (MCQ, short answer, reasoning)
   - Approve items for delivery, edit items, or reject items
7. **Student — Safe Practice Delivery & Formative Feedback**:
   - Start or resume an active practice session
   - Strictly student-safe delivery: **zero** exposure of teacher keys, rationales, internal review notes, or confidence scores
   - Interactive answering: radio options for MCQ, textarea for short answer and reasoning
   - Instant formative scoring feedback and correctness indicators
   - Comprehensive performance summary with accuracy percentage, concept evidence breakdown, and transparent non-mastery disclaimer
8. **Admin — Overview**:
   - Platform health, registered topic and assessment counts, and subsystem status

---

## Setup & Run Commands

### 1. Environment Configuration
Create or update `.env` in `frontend/`:
```bash
cp .env.example .env
```
Default contents:
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 2. Install Dependencies
```bash
npm install
```

### 3. Run Development Server
```bash
npm run dev
```
The app will be accessible at `http://localhost:5173`.

### 4. Run Frontend Tests
```bash
npm test
```

### 5. Type-Check and Build Production Bundle
```bash
npm run build
```
