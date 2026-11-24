#!/usr/bin/env python3
"""
LearnGraph End-to-End Verification Script
Simulates full user workflows against the running backend server at http://127.0.0.1:8000.
Tests:
1. Teacher registration and login
2. Topic creation
3. Assessment creation
4. Question creation
5. Student registration and login
6. Student submission creation
7. Teacher answer-sheet upload (PDF)
8. Background OCR processing triggering and extraction inspection
9. Answer-to-question matching proposals retrieval
10. Teacher approval of proposed answer (authoritative QuestionAnswer write)
11. Teacher AI diagnostic evaluation run execution
12. Inspection and acceptance of misconception finding
13. Targeted remediation generation for accepted finding
14. Teacher review and approval of generated practice item
15. Student practice session initiation (verifying strict privacy invariants)
16. Student response submission and instant formative feedback
17. Student summary retrieval (checking accuracy %, concept evidence, and non-mastery disclaimer)
18. Student session completion
19. RBAC & Privacy Invariant verification:
    - Student forbidden from accessing teacher endpoints (403)
    - Student practice responses strictly exclude teacher keys, rationales, notes, and confidence
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000"


def request(method, path, body=None, token=None, is_multipart=False, headers=None):
    url = f"{BASE_URL}{path}"
    req_headers = headers or {}
    if token:
        req_headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None and not is_multipart:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    elif is_multipart:
        data = body  # already encoded bytes with boundary

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content = resp.read()
            if not content:
                return status, None
            return status, json.loads(content.decode("utf-8"))
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            parsed = json.loads(content.decode("utf-8"))
        except Exception:
            parsed = content.decode("utf-8")
        return e.code, parsed


def make_multipart(filename, file_bytes, field_name="file"):
    boundary = "----LearnGraphBoundary" + str(int(time.time()))
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return body, headers


def run_e2e_verification():
    print("=" * 60)
    print("LEARNGRAPH FULL END-TO-END VERIFICATION")
    print("=" * 60)

    ts = int(time.time())
    teacher_email = f"prof_{ts}@learngraph.edu"
    student_email = f"student_{ts}@learngraph.edu"
    password = "SecurePassword123!"

    # 1. Register & Login Teacher
    print("\n[Step 1] Registering and authenticating Teacher...")
    s, resp = request(
        "POST",
        "/api/v1/auth/register",
        {"full_name": "Prof. E2E", "email": teacher_email, "password": password, "role": "teacher"},
    )
    assert s == 201, f"Teacher registration failed: {s} {resp}"
    teacher_id = resp["id"]
    print(f"  ✓ Teacher registered: ID {teacher_id} ({teacher_email})")

    s, resp = request("POST", "/api/v1/auth/login", {"email": teacher_email, "password": password})
    assert s == 200, f"Teacher login failed: {s} {resp}"
    teacher_token = resp["access_token"]
    print("  ✓ Teacher authenticated, received JWT Bearer token")

    # 2. Create Learning Topic
    print("\n[Step 2] Teacher creating Learning Topic...")
    s, resp = request(
        "POST",
        "/api/v1/topics",
        {"name": f"Calculus Limits {ts}", "description": "Limits and Continuity"},
        token=teacher_token,
    )
    assert s == 201, f"Topic creation failed: {s} {resp}"
    topic_id = resp["id"]
    print(f"  ✓ Topic created: ID {topic_id} ('{resp['name']}')")

    # 3. Create Assessment
    print("\n[Step 3] Teacher creating Diagnostic Assessment...")
    s, resp = request(
        "POST",
        "/api/v1/assessments",
        {"title": f"Midterm Limits Exam {ts}", "description": "Limits Evaluation Assessment"},
        token=teacher_token,
    )
    assert s == 201, f"Assessment creation failed: {s} {resp}"
    assessment_id = resp["id"]
    print(f"  ✓ Assessment created: ID {assessment_id} ('{resp['title']}')")

    # 4. Create Question for Assessment
    print("\n[Step 4] Teacher creating Question within Assessment...")
    s, resp = request(
        "POST",
        f"/api/v1/assessments/{assessment_id}/questions",
        {
            "topic_id": topic_id,
            "prompt": "Differentiate the product function h(x) = f(x)*g(x).",
            "question_type": "short_answer",
            "marks": 5.0,
            "rubric": "Requires product rule: (fg)' = f'g + fg'. Distributing derivatives as f'*g' is a misconception.",
            "expected_answer": "(fg)' = f'g + fg'",
        },
        token=teacher_token,
    )
    assert s == 201, f"Question creation failed: {s} {resp}"
    question_id = resp["id"]
    print(f"  ✓ Question created: ID {question_id} (Expected: '{resp['expected_answer']}', Marks: {resp['marks']})")

    # 5. Register & Login Student
    print("\n[Step 5] Registering and authenticating Student...")
    s, resp = request(
        "POST",
        "/api/v1/auth/register",
        {"full_name": "Alice Student", "email": student_email, "password": password, "role": "student"},
    )
    assert s == 201, f"Student registration failed: {s} {resp}"
    student_id = resp["id"]
    print(f"  ✓ Student registered: ID {student_id} ({student_email})")

    s, resp = request("POST", "/api/v1/auth/login", {"email": student_email, "password": password})
    assert s == 200, f"Student login failed: {s} {resp}"
    student_token = resp["access_token"]
    print("  ✓ Student authenticated, received JWT Bearer token")

    # 6. Student creates Submission for Assessment
    print("\n[Step 6] Student creating Submission for Assessment...")
    s, resp = request(
        "POST",
        f"/api/v1/assessments/{assessment_id}/submissions",
        {"status": "submitted"},
        token=student_token,
    )
    assert s == 201, f"Submission creation failed: {s} {resp}"
    submission_id = resp["id"]
    print(f"  ✓ Submission created: ID {submission_id} (Status: '{resp['status']}')")

    # 7. Teacher Uploads Scanned Answer Sheet
    print("\n[Step 7] Teacher uploading scanned answer-sheet PDF...")
    with open("sample_answersheet.pdf", "rb") as f:
        pdf_bytes = f.read()
    body, headers = make_multipart("student_sheet.pdf", pdf_bytes)
    s, resp = request(
        "POST",
        f"/api/v1/submissions/{submission_id}/answer-sheets",
        body=body,
        token=teacher_token,
        is_multipart=True,
        headers=headers,
    )
    assert s == 201, f"Answer sheet upload failed: {s} {resp}"
    upload_id = resp["id"]
    print(f"  ✓ Answer sheet uploaded: Upload ID {upload_id} (File: '{resp['original_filename']}', Size: {resp['file_size_bytes']}B)")

    # 8. Trigger Background OCR Processing
    print("\n[Step 8] Triggering background OCR processing...")
    s, resp = request(
        "POST",
        f"/api/v1/answer-sheets/{upload_id}/process",
        token=teacher_token,
    )
    assert s == 202, f"OCR processing trigger failed: {s} {resp}"
    print(f"  ✓ OCR triggered: {resp['message']}")

    # Poll OCR processing status until terminal state (extracted or needs_review)
    print("  ... polling OCR status until completion ...")
    terminal_status = None
    for attempt in range(60):
        time.sleep(1.0)
        s, st_resp = request("GET", f"/api/v1/answer-sheets/{upload_id}/status", token=teacher_token)
        if s == 200 and st_resp.get("upload_status") in ["extracted", "needs_review", "failed"]:
            terminal_status = st_resp.get("upload_status")
            print(f"  ✓ Terminal status reached: '{terminal_status}' after {attempt + 1}s")
            break

    assert terminal_status in ["extracted", "needs_review"], f"OCR failed to complete: {terminal_status}"
    s, resp = request("GET", f"/api/v1/answer-sheets/{upload_id}/extraction", token=teacher_token)
    assert s == 200, f"OCR extraction retrieval failed: {s} {resp}"
    print(f"  ✓ OCR extraction retrieved: Provider '{resp['provider_name']}', Confidence {resp['confidence']}")

    # 9. Retrieve Proposed Answers (Matching)
    print("\n[Step 9] Retrieving answer-to-question matching proposals...")
    s, resp = request(
        "GET",
        f"/api/v1/submissions/{submission_id}/proposed-answers",
        token=teacher_token,
    )
    assert s == 200, f"Proposed answers retrieval failed: {s} {resp}"
    assert len(resp["proposals"]) > 0, "No proposals returned by matching service"
    proposal = resp["proposals"][0]
    proposal_id = proposal["id"]
    print(f"  ✓ Matching proposal found: Proposal ID {proposal_id} -> Q{proposal['question_id']}, Proposed text: '{proposal['proposed_text']}'")

    # 10. Teacher Corrects and Approves Proposal
    print("\n[Step 10] Teacher correcting and approving proposed answer...")
    s, resp = request(
        "POST",
        f"/api/v1/proposed-answers/{proposal_id}/correct",
        {
            "corrected_text": "(f*g)' = f'*g' because derivative of product is product of derivatives.",
            "question_id": question_id,
            "review_notes": "Teacher corrected proposed segment to student's exact answer",
        },
        token=teacher_token,
    )
    assert s == 200, f"Proposal correction failed: {s} {resp}"
    print(f"  ✓ Proposal corrected and written to authoritative QuestionAnswer record (Status: {resp['proposal']['status']})")

    # 11. Run AI Evaluation on Approved Answers
    print("\n[Step 11] Running AI diagnostic evaluation...")
    s, resp = request(
        "POST",
        f"/api/v1/submissions/{submission_id}/evaluate",
        token=teacher_token,
    )
    assert s == 200, f"Evaluation execution failed: {s} {resp}"
    print(f"  ✓ Evaluation executed: {resp['total_runs']} evaluation run(s)")
    assert len(resp["runs"]) > 0, "No evaluation runs returned"
    eval_run = resp["runs"][0]
    assert len(eval_run["findings"]) > 0, "No findings returned in evaluation run"
    finding = eval_run["findings"][0]
    finding_id = finding["id"]
    category = finding.get("category") or finding.get("misconception_type")
    confidence = finding.get("confidence") or finding.get("confidence_score")
    print(f"  ✓ Diagnostic finding identified: Finding ID {finding_id} ('{category}', confidence: {confidence})")

    # 12. Teacher Reviews and Accepts Finding
    print("\n[Step 12] Teacher accepting misconception finding...")
    s, resp = request(
        "POST",
        f"/api/v1/evaluations/findings/{finding_id}/review",
        {"action": "accepted", "review_notes": "Confirmed student misconception during limits exam."},
        token=teacher_token,
    )
    assert s == 200, f"Finding review failed: {s} {resp}"
    assert resp["finding"]["review_status"] == "accepted"
    print(f"  ✓ Finding accepted by teacher with audit note: '{resp['audit']['review_notes']}'")

    # 13. Generate Targeted Remediation Items
    print("\n[Step 13] Generating targeted remediation follow-up questions...")
    s, resp = request(
        "POST",
        f"/api/v1/findings/{finding_id}/remediation/generate",
        token=teacher_token,
    )
    assert s == 200, f"Remediation generation failed: {s} {resp}"
    assert len(resp["items"]) > 0, "No remediation items generated"
    rem_item = resp["items"][0]
    rem_item_id = rem_item["id"]
    print(f"  ✓ Generated {len(resp['items'])} remediation practice items (Item ID {rem_item_id}: '{rem_item['question_text'][:50]}...')")

    # 14. Teacher Approves Remediation Item for Delivery
    print("\n[Step 14] Teacher approving practice item for student delivery...")
    s, resp = request(
        "POST",
        f"/api/v1/remediations/items/{rem_item_id}/review",
        {"action": "approve"},
        token=teacher_token,
    )
    assert s == 200, f"Remediation review failed: {s} {resp}"
    print(f"  ✓ Practice item #{rem_item_id} approved for delivery (Status: {resp['item']['review_status']})")

    # 15. Student Starts Practice Session & Verify Strict Privacy Invariants
    print("\n[Step 15] Student starting practice session & checking privacy invariants...")
    s, resp = request(
        "POST",
        f"/api/v1/submissions/{submission_id}/practice-sessions?resume_active=true",
        token=student_token,
    )
    assert s == 201, f"Student practice session start failed: {s} {resp}"
    session_id = resp["id"]
    items = resp["items"]
    assert len(items) > 0, "No practice items served to student"
    delivered_item = items[0]
    print(f"  ✓ Student practice session #{session_id} active with {len(items)} deliverable item(s)")

    # PRIVACY VERIFICATION: Confirm zero teacher answer keys, rationales, notes, or confidence
    assert "teacher_answer_key" not in delivered_item, "PRIVACY VIOLATION: teacher_answer_key leaked to student!"
    assert "teacher_rationale" not in delivered_item, "PRIVACY VIOLATION: teacher_rationale leaked to student!"
    assert "uncertainty_note" not in delivered_item, "PRIVACY VIOLATION: uncertainty_note leaked to student!"
    assert "review_notes" not in delivered_item, "PRIVACY VIOLATION: review_notes leaked to student!"
    assert "confidence_score" not in delivered_item, "PRIVACY VIOLATION: confidence_score leaked to student!"
    assert "expected_answer" not in delivered_item, "PRIVACY VIOLATION: expected_answer leaked to student!"
    assert "explanation" not in delivered_item, "PRIVACY VIOLATION: explanation leaked to student!"
    print("  ✓ PRIVACY INVARIANT VERIFIED: Delivered practice item contains zero teacher answer keys, rationales, notes, or confidence scores!")

    # 16. Student Submits Response
    print("\n[Step 16] Student submitting answer to practice item...")
    sample_answer = "0"
    if delivered_item["question_type"] == "mcq" and delivered_item.get("options"):
        sample_answer = delivered_item["options"][0].split(")")[0].strip()

    s, resp = request(
        "POST",
        f"/api/v1/practice-sessions/{session_id}/responses",
        {"remediation_item_id": delivered_item["id"], "student_answer": sample_answer},
        token=student_token,
    )
    assert s == 201, f"Response submission failed: {s} {resp}"
    print(f"  ✓ Response scored: Score {resp['score']}, Correct: {resp['is_correct']}, Feedback: '{resp['feedback']}'")

    # 17. Student Retrieves Formative Summary Report
    print("\n[Step 17] Student retrieving formative performance summary...")
    s, resp = request(
        "GET",
        f"/api/v1/practice-sessions/{session_id}/summary",
        token=student_token,
    )
    assert s == 200, f"Summary retrieval failed: {s} {resp}"
    assert resp["total_items"] >= 1
    assert resp["completed_items"] >= 1
    assert "pedagogical_disclaimer" in resp
    print(f"  ✓ Formative Summary: Accuracy {resp['accuracy_percentage']:.0f}%, Completed {resp['completed_items']}/{resp['total_items']}")
    print(f"  ✓ Non-mastery Disclaimer Present: '{resp['pedagogical_disclaimer']}'")

    # 18. Student Practice Session Completion
    print("\n[Step 18] Verifying practice session completion state...")
    s, resp = request(
        "GET",
        f"/api/v1/practice-sessions/{session_id}",
        token=student_token,
    )
    assert s == 200, f"Session retrieval failed: {s} {resp}"
    if resp["status"] == "active":
        s, resp = request(
            "POST",
            f"/api/v1/practice-sessions/{session_id}/complete",
            token=student_token,
        )
        assert s == 200, f"Session completion failed: {s} {resp}"
    assert resp["status"] == "completed"
    print(f"  ✓ Practice session #{session_id} state successfully finalized as '{resp['status']}'")

    # 19. RBAC Verification: Student cannot access teacher endpoints
    print("\n[Step 19] Verifying Role-Based Access Control (RBAC)...")
    s, resp = request(
        "POST",
        f"/api/v1/submissions/{submission_id}/evaluate",
        token=student_token,
    )
    assert s == 403, f"RBAC failed: Student was able to trigger evaluation! {s} {resp}"
    print("  ✓ RBAC VERIFIED: Student correctly forbidden (HTTP 403) from teacher evaluation endpoint")

    s, resp = request(
        "POST",
        "/api/v1/topics",
        {"name": "Hacker Topic"},
        token=student_token,
    )
    assert s == 403, f"RBAC failed: Student was able to create topic! {s} {resp}"
    print("  ✓ RBAC VERIFIED: Student correctly forbidden (HTTP 403) from topic creation endpoint")

    # 20. Intervention Outcomes Verification (Teacher)
    print("\n[Step 20] Teacher verifying Intervention Outcomes (Learning Loop verification)...")
    s, resp = request(
        "GET",
        f"/api/v1/submissions/{submission_id}/intervention-outcomes",
        token=teacher_token,
    )
    assert s == 200, f"Intervention outcomes failed: {s} {resp}"
    assert resp["total_interventions"] >= 1
    outcomes = resp["outcomes"]
    assert len(outcomes) >= 1
    o = outcomes[0]
    print(f"  ✓ Intervention outcome recorded: Concept '{o['concept_name']}', Outcome: '{o['outcome_label']}'")
    print(f"  ✓ Uncertainty Level: '{o['uncertainty_level']}', Note: '{o['uncertainty_rationale']}'")
    print(f"  ✓ Follow-up evidence count: {o['evidence_count']}, Accuracy: {o['accuracy_percentage']:.0f}%")
    print(f"  ✓ Recommended teacher action: '{o['recommended_action']}'")

    # 21. Student Progress Report Verification (Student View with Strict Privacy)
    print("\n[Step 21] Student retrieving topic progress report & verifying privacy invariants...")
    s, resp = request(
        "GET",
        f"/api/v1/submissions/{submission_id}/student-progress",
        token=student_token,
    )
    assert s == 200, f"Student progress report failed: {s} {resp}"
    assert resp["total_concepts_tracked"] >= 1
    c = resp["concepts"][0]
    print(f"  ✓ Student concept tracked: '{c['concept_name']}', Status: '{c['status_label']}'")
    print(f"  ✓ Single-response uncertainty policy: '{c['uncertainty_rationale']}'")
    print(f"  ✓ Student next step: '{c['recommended_next_step']}'")

    # Strict Privacy assertions on raw student progress json
    raw_json = json.dumps(resp)
    assert "teacher_answer_key" not in raw_json, "PRIVACY VIOLATION: teacher_answer_key in student report!"
    assert "teacher_rationale" not in raw_json, "PRIVACY VIOLATION: teacher_rationale in student report!"
    assert "review_notes" not in raw_json, "PRIVACY VIOLATION: review_notes in student report!"
    print("  ✓ PRIVACY INVARIANT VERIFIED: Student progress report contains zero teacher keys, rationales, or notes!")

    # 22. Providers Status Health Check
    print("\n[Step 22] Inspecting system providers status (/api/v1/providers)...")
    s, resp = request("GET", "/api/v1/providers")
    assert s == 200, f"Providers check failed: {s} {resp}"
    print(f"  ✓ OCR Provider: '{resp['ocr_provider']}' (Real: {resp['ocr_real']})")
    print(f"  ✓ Evaluator Provider: '{resp['evaluator_provider']}' (Real: {resp['evaluator_real']})")
    print(f"  ✓ VLLM Base URL: '{resp['vllm_base_url']}' (Model: '{resp['vllm_model']}')")
    print(f"  ✓ VLLM Status: {resp.get('vllm_status_message')}")

    print("\n" + "=" * 60)
    print("ALL 22 END-TO-END VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_e2e_verification()
