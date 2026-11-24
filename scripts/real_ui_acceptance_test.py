import asyncio
import json
import urllib.request
import websockets
import base64
import os
import sys
import time

SCREENSHOT_DIR = os.path.abspath("/home/suman/Desktop/TechFestProject/LearnGraph/scripts/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

MATH_IMAGE_PATH = os.path.abspath("/home/suman/Desktop/TechFestProject/LearnGraph/sample_engineering_math.jpg")

async def run_ui_acceptance():
    print("=" * 80)
    print("LEARNGRAPH: REAL UI BROWSER ACCEPTANCE TEST")
    print("=" * 80)
    
    # 1. Connect to Chrome DevTools Protocol
    try:
        req = urllib.request.urlopen("http://127.0.0.1:9222/json")
        targets = json.loads(req.read().decode())
    except Exception as e:
        print(f"Error connecting to Chrome on 9222: {e}")
        return False
        
    page_target = next((t for t in targets if t.get("type") == "page" and "127.0.0.1:5173" in t.get("url", "")), None)
    if not page_target:
        print("Page target for 127.0.0.1:5173 not found among targets:", [t.get("url") for t in targets])
        return False
        
    ws_url = page_target["webSocketDebuggerUrl"]
    print(f"[CDP] Connecting to Chrome tab: {ws_url}")
    
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        msg_id = 1
        
        async def call(method, params=None):
            nonlocal msg_id
            mid = msg_id
            msg_id += 1
            payload = {"id": mid, "method": method, "params": params or {}}
            await ws.send(json.dumps(payload))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == mid:
                    if "error" in resp:
                        raise RuntimeError(f"CDP call error for {method}: {resp['error']}")
                    return resp
        
        async def evaluate(expr):
            res = await call("Runtime.evaluate", {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": True
            })
            return res.get("result", {}).get("result", {}).get("value")
            
        async def take_screenshot(filename):
            snap = await call("Page.captureScreenshot", {"format": "png"})
            raw = base64.b64decode(snap["result"]["data"])
            path = os.path.join(SCREENSHOT_DIR, filename)
            with open(path, "wb") as f:
                f.write(raw)
            print(f"  [SCREENSHOT] Captured {filename} ({len(raw):,} bytes)")
            return path

        await call("Page.enable")
        await call("DOM.enable")
        await call("Runtime.enable")
        
        # Navigate to clean home
        await call("Page.navigate", {"url": "http://127.0.0.1:5173"})
        await asyncio.sleep(2)
        
        # STEP 1: Select Assessment #17 / #18 / #19 (Engineering Math Exam)
        print("\n--- STEP 1: Inspect & Select Assessment in Frontend ---")
        assessments_info = await evaluate("""
        (() => {
            const select = document.querySelector('select.form-select');
            return {
                selectedVal: select ? select.value : null,
                options: select ? Array.from(select.options).map(o => ({ value: o.value, text: o.text })) : []
            };
        })()
        """)
        print(f"Current select value: {assessments_info.get('selectedVal')}")
        options = assessments_info.get("options", [])
        target_opt = next((o for o in options if "Engineering Math Exam" in o["text"]), options[0] if options else {"value": "1", "text": "Default"})
            
        print(f"Selecting target assessment in UI: {target_opt}")
        await evaluate(f"""
        (() => {{
            const select = document.querySelector('select.form-select');
            select.value = '{target_opt["value"]}';
            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }})()
        """)
        await asyncio.sleep(1)
        await take_screenshot("01_assessment_selected.png")
        
        # STEP 2: Upload sample_engineering_math.jpg and process
        print("\n--- STEP 2: Upload Sample Answer Sheet & Process ---")
        input_res = await call("Runtime.evaluate", {"expression": "document.querySelector('input[type=\"file\"]')"})
        obj_id = input_res["result"]["result"]["objectId"]
        await call("DOM.setFileInputFiles", {"files": [MATH_IMAGE_PATH], "objectId": obj_id})
        
        # Trigger change event
        file_selected = await evaluate("""
        (() => {
            const input = document.querySelector('input[type="file"]');
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return document.querySelector('.file-name')?.innerText || 'No file selected';
        })()
        """)
        print(f"Selected file in UI: {file_selected}")
        assert "sample_engineering_math.jpg" in file_selected, f"Expected file selected, got: {file_selected}"
        await take_screenshot("02_file_selected.png")
        
        # Click "Scan & Analyze Document"
        print("Clicking 'Scan & Analyze Document' button in UI...")
        await evaluate("""
        (() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Scan & Analyze Document'));
            if (btn) btn.click();
        })()
        """)
        
        # Wait for processing to complete
        print("Waiting for PaddleOCR and initial matching pipeline in UI...")
        start_time = time.time()
        completed = False
        while time.time() - start_time < 90:
            status_info = await evaluate("""
            (() => {
                const stepLabel = document.querySelector('.current-step-label')?.innerText;
                const progressInfo = document.querySelector('.page-progress-info')?.innerText;
                const alertInfo = document.querySelector('.alert-info')?.innerText;
                const alertDanger = document.querySelector('.alert-danger')?.innerText;
                const hasResults = !!document.querySelector('.results-card');
                const tabs = Array.from(document.querySelectorAll('.tab-btn')).map(t => t.innerText);
                return { stepLabel, progressInfo, alertInfo, alertDanger, hasResults, tabs };
            })()
            """)
            if status_info.get("alertDanger"):
                print(f"Error during processing: {status_info['alertDanger']}")
                break
            if status_info.get("hasResults"):
                print(f"Pipeline finished! Results card present. Tabs: {status_info.get('tabs')}")
                completed = True
                break
            if status_info.get("stepLabel"):
                print(f"   [Processing] {status_info.get('stepLabel')} ({status_info.get('progressInfo') or ''})")
            await asyncio.sleep(2)
            
        assert completed, "Document processing pipeline timed out or failed"
        await take_screenshot("03_processing_complete.png")
        
        # STEP 3: Inspect OCR Output & Verify Math Advisory
        print("\n--- STEP 3: Inspect OCR Output & Mathematical Warning ---")
        review_notice = await evaluate("document.querySelector('.alert-info')?.innerText")
        print(f"Teacher review notice in UI: {review_notice}")
        assert "mathematical notation or layout-sensitive segments" in (review_notice or ""), (
            f"Expected math layout warning, got: {review_notice}"
        )
        
        # Click Tab 1 ("1. Raw OCR Extraction") to verify raw OCR
        await evaluate("""
        (() => {
            const tabs = Array.from(document.querySelectorAll('.tab-btn'));
            const ocrTab = tabs.find(t => t.innerText.includes('Raw OCR Extraction'));
            if (ocrTab) ocrTab.click();
        })()
        """)
        await asyncio.sleep(1)
        
        ocr_details = await evaluate("""
        (() => {
            const rawTextBox = document.querySelector('.extracted-text-box')?.innerText || '';
            const segments = Array.from(document.querySelectorAll('.segment-card')).map(s => ({
                page: s.querySelector('.segment-page')?.innerText,
                conf: s.querySelector('.segment-confidence')?.innerText,
                text: s.querySelector('.segment-text')?.innerText,
                bbox: s.querySelector('.segment-bbox')?.innerText
            }));
            const metaItems = Array.from(document.querySelectorAll('.meta-item')).map(m => m.innerText);
            return {
                rawTextPreview: rawTextBox.slice(0, 300),
                rawTextLength: rawTextBox.length,
                segmentsCount: segments.length,
                firstSegment: segments[0],
                metaItems
            };
        })()
        """)
        print(f"Raw OCR text length: {ocr_details.get('rawTextLength')} chars")
        print(f"Structured segments count: {ocr_details.get('segmentsCount')}")
        print(f"First segment: {ocr_details.get('firstSegment')}")
        print(f"Metadata items: {ocr_details.get('metaItems')}")
        print(f"Raw OCR preview:\n{ocr_details.get('rawTextPreview')[:180]}...")
        await take_screenshot("04_ocr_tab_inspection.png")
        
        # STEP 4: Tab 2: Answer Matching & Teacher Review
        print("\n--- STEP 4: Inspect Proposals & Approve Corrected Answer ---")
        await evaluate("""
        (() => {
            const tabs = Array.from(document.querySelectorAll('.tab-btn'));
            const matchTab = tabs.find(t => t.innerText.includes('Answer Matching'));
            if (matchTab) matchTab.click();
        })()
        """)
        await asyncio.sleep(1)
        
        proposals_summary = await evaluate("""
        (() => {
            const cards = Array.from(document.querySelectorAll('.matching-tab-content .finding-card'));
            const meta = Array.from(document.querySelectorAll('.matching-tab-content .meta-item')).map(m => m.innerText);
            return {
                proposalsCount: cards.length,
                meta,
                firstCardText: cards[0]?.innerText?.slice(0, 300)
            };
        })()
        """)
        print(f"Rendered proposal cards count: {proposals_summary.get('proposalsCount')}")
        print(f"Matching metadata: {proposals_summary.get('meta')}")
        await take_screenshot("05_proposals_view.png")
        
        # Click "Correct Text / Reassign" on the first proposal
        print("Clicking 'Correct Text / Reassign' on Proposal...")
        await evaluate("""
        (() => {
            const correctBtn = Array.from(document.querySelectorAll('.matching-tab-content button')).find(b => 
                b.innerText.includes('Correct Text / Reassign')
            );
            if (correctBtn) correctBtn.click();
        })()
        """)
        await asyncio.sleep(1)
        await take_screenshot("06_proposal_edit_open.png")
        
        # Fill in authoritative corrected formula using React native property setters
        corrected_formula = "a × b = |i j k; a1 a2 a3; b1 b2 b3|"
        print(f"Setting authoritative corrected text via React: '{corrected_formula}'...")
        await evaluate(f"""
        (() => {{
            const selectQ = document.querySelector('.matching-tab-content select.form-select');
            if (selectQ) {{
                const targetQOpt = Array.from(selectQ.options).find(o => o.text.includes('cross product') || o.value === '17');
                if (targetQOpt) {{
                    selectQ.value = targetQOpt.value;
                }} else if (selectQ.options.length > 1) {{
                    selectQ.value = selectQ.options[1].value;
                }}
                selectQ.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            const textarea = document.querySelector('.matching-tab-content textarea.form-textarea');
            if (textarea) {{
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                nativeSetter.call(textarea, '{corrected_formula}');
                textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            const noteInput = document.querySelector('.matching-tab-content input.form-input');
            if (noteInput) {{
                const nativeInputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                nativeInputSetter.call(noteInput, 'Teacher verified vector cross product determinant definition');
                noteInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                noteInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }})()
        """)
        await asyncio.sleep(1)
        
        # Click "Save & Approve Correction"
        print("Clicking 'Save & Approve Correction' button...")
        save_btn_clicked = await evaluate("""
        (() => {
            const saveBtn = Array.from(document.querySelectorAll('.matching-tab-content button')).find(b => 
                b.innerText.includes('Save & Approve Correction')
            );
            if (saveBtn) {
                saveBtn.click();
                return true;
            }
            return false;
        })()
        """)
        assert save_btn_clicked, "Save & Approve Correction button not found"
        await asyncio.sleep(2)
        
        # Verify approval notice and status
        approval_status = await evaluate("""
        (() => {
            const notice = document.querySelector('.alert-success')?.innerText;
            const meta = Array.from(document.querySelectorAll('.matching-tab-content .meta-item')).map(m => m.innerText);
            const correctedBox = document.querySelector('.matching-tab-content [style*="borderLeft"]')?.innerText;
            return { notice, meta, correctedBox };
        })()
        """)
        print(f"Approval notice in UI: {approval_status.get('notice')}")
        print(f"Matching metadata after approval: {approval_status.get('meta')}")
        print(f"Authoritative corrected box: {approval_status.get('correctedBox')}")
        await take_screenshot("07_proposal_approved.png")
        
        # STEP 5: Run AI Diagnostic Evaluation
        print("\n--- STEP 5: Run AI Diagnostic Evaluation via Groq VLLM ---")
        reeval_btn_clicked = await evaluate("""
        (() => {
            const btn = Array.from(document.querySelectorAll('.results-actions button')).find(b => 
                b.innerText.includes('Re-evaluate Answers')
            );
            if (btn) {
                btn.click();
                return true;
            }
            return false;
        })()
        """)
        assert reeval_btn_clicked, "'Re-evaluate Answers' button not found in UI"
        print("AI evaluation requested from UI. Waiting for Groq VLLM response...")
        
        eval_done = False
        start_eval = time.time()
        while time.time() - start_eval < 60:
            eval_state = await evaluate("""
            (() => {
                const notice = document.querySelector('.alert-success')?.innerText || document.querySelector('.alert-danger')?.innerText;
                const findings = Array.from(document.querySelectorAll('.analysis-tab-content .finding-card')).map(f => ({
                    concept: f.querySelector('.concept-title')?.innerText,
                    category: f.querySelector('.badge')?.innerText,
                    confidence: f.querySelector('.finding-confidence')?.innerText,
                    evidence: f.querySelector('blockquote')?.innerText,
                    rationale: f.querySelector('.finding-rationale p')?.innerText,
                    uncertainty: f.querySelector('.finding-uncertainty p')?.innerText,
                    reviewStatus: f.querySelector('.finding-concept .badge:nth-child(3)')?.innerText
                }));
                return { notice, findings, hasRuns: document.querySelectorAll('.evaluation-run-block').length };
            })()
            """)
            if eval_state.get("findings") and len(eval_state["findings"]) > 0:
                print(f"AI evaluation completed! Findings received: {len(eval_state['findings'])}")
                eval_done = True
                break
            await asyncio.sleep(2)
            
        assert eval_done, "AI Evaluation did not return findings in time"
        await take_screenshot("08_diagnostic_findings.png")
        
        findings = eval_state["findings"]
        print("\n[VERIFICATION OF FINDINGS IN UI]")
        for i, f in enumerate(findings):
            print(f" Finding #{i+1}:")
            print(f"   Concept: {f.get('concept')}")
            print(f"   Category: {f.get('category')}")
            print(f"   Confidence: {f.get('confidence')}")
            print(f"   Evidence Excerpt: \"{f.get('evidence')}\"")
            print(f"   Rationale: {f.get('rationale')}")
            print(f"   Uncertainty: {f.get('uncertainty')}")
            print(f"   Review Status: {f.get('reviewStatus')}")
            
        # STEP 6: Teacher Accepts Finding & Generates Remediation
        print("\n--- STEP 6: Teacher Accepts Finding & Generates Remediation ---")
        accept_clicked = await evaluate("""
        (() => {
            const acceptBtn = Array.from(document.querySelectorAll('.analysis-tab-content .finding-card button')).find(b => 
                b.innerText === 'Accept' || b.innerText.includes('Accept')
            );
            if (acceptBtn) {
                acceptBtn.click();
                return true;
            }
            return false;
        })()
        """)
        assert accept_clicked, "Accept button for finding not found"
        await asyncio.sleep(2)
        print("Finding marked as ACCEPTED in UI.")
        await take_screenshot("09_finding_accepted.png")
        
        print("Clicking '⚡ Generate Remediation Items' in UI...")
        gen_clicked = await evaluate("""
        (() => {
            const genBtn = Array.from(document.querySelectorAll('.analysis-tab-content button')).find(b => 
                b.innerText.includes('Generate Remediation Items')
            );
            if (genBtn) {
                genBtn.click();
                return true;
            }
            return false;
        })()
        """)
        assert gen_clicked, "Generate Remediation button not found"
        
        start_gen = time.time()
        remed_done = False
        while time.time() - start_gen < 45:
            remed_state = await evaluate("""
            (() => {
                const items = Array.from(document.querySelectorAll('.remediations-tab-content .finding-card'));
                const prompt = document.querySelector('.remediations-tab-content strong')?.nextSibling?.textContent;
                const meta = Array.from(document.querySelectorAll('.remediations-tab-content .meta-item')).map(m => m.innerText);
                return { itemsCount: items.length, prompt, meta };
            })()
            """)
            if remed_state.get("itemsCount", 0) > 0:
                print(f"Remediation item generated in UI! Items count: {remed_state['itemsCount']}")
                print(f"Metadata: {remed_state.get('meta')}")
                remed_done = True
                break
            await asyncio.sleep(2)
            
        assert remed_done, "Remediation generation timed out"
        await take_screenshot("10_remediation_items_generated.png")
        
        # Approve remediation item for student delivery
        print("Approving remediation item for student delivery in UI...")
        approve_remed = await evaluate("""
        (() => {
            const btn = Array.from(document.querySelectorAll('.remediations-tab-content button')).find(b => 
                b.innerText.includes('Approve for Delivery')
            );
            if (btn) {
                btn.click();
                return true;
            }
            return false;
        })()
        """)
        assert approve_remed, "Approve remediation button not found"
        await asyncio.sleep(2)
        
        remed_status = await evaluate("""
        (() => {
            const badge = document.querySelector('.remediations-tab-content .finding-card .badge')?.innerText;
            const meta = Array.from(document.querySelectorAll('.remediations-tab-content .meta-item')).map(m => m.innerText);
            return { badge, meta };
        })()
        """)
        print(f"Remediation item status after approval: {remed_status.get('badge')}")
        print(f"Remediation metadata: {remed_status.get('meta')}")
        await take_screenshot("11_remediation_approved.png")
        
        # STEP 7: Open Student Practice View & Perform Privacy Audit
        print("\n--- STEP 7: Student Practice View & Privacy Verification ---")
        # Toggle All Management Views in Navbar
        await evaluate("""
        (() => {
            const mgmtBtn = Array.from(document.querySelectorAll('header button')).find(b => b.innerText.includes('All Management Views'));
            if (mgmtBtn) mgmtBtn.click();
        })()
        """)
        await asyncio.sleep(1)
        
        # Click 'Student Practice' in nav
        await evaluate("""
        (() => {
            const practiceBtn = Array.from(document.querySelectorAll('header nav button')).find(b => b.innerText.includes('Student Practice'));
            if (practiceBtn) practiceBtn.click();
        })()
        """)
        await asyncio.sleep(1)
        
        # In Student Practice, select assessment and click Start/Resume Practice
        await evaluate(f"""
        (() => {{
            const sel = document.querySelector('select.form-select');
            if (sel) {{
                sel.value = '{target_opt["value"]}';
                sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }})()
        """)
        await asyncio.sleep(1)
        
        await evaluate("""
        (() => {
            const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Start / Resume Practice'));
            if (startBtn) startBtn.click();
        })()
        """)
        await asyncio.sleep(2)
        
        # PRIVACY AUDIT: Inspect DOM of Student View
        student_view_data = await evaluate("""
        (() => {
            const allText = document.body.innerText;
            return {
                containsTeacherKeyHeader: allText.includes('🔒 Instructor Verification') || allText.includes('Protected from Students'),
                containsTeacherRationale: allText.includes('Pedagogical Rationale') || allText.includes('Clinical / Pedagogical Rationale'),
                containsAnswerKey: allText.includes('Expected Answer Key:'),
                containsUncertainty: allText.includes('Uncertainty Note:'),
                hasPrompt: allText.includes('Targeted Practice') || allText.includes('Question') || allText.includes('practice')
            };
        })()
        """)
        print("\n[PRIVACY AUDIT RESULTS]")
        print(f" Practice prompt available: {student_view_data['hasPrompt']}")
        print(f" Contains Instructor Verification Box: {student_view_data['containsTeacherKeyHeader']}")
        print(f" Contains Pedagogical Rationale: {student_view_data['containsTeacherRationale']}")
        print(f" Contains Expected Answer Key: {student_view_data['containsAnswerKey']}")
        print(f" Contains Uncertainty Note: {student_view_data['containsUncertainty']}")
        
        assert not student_view_data['containsTeacherKeyHeader'], "PRIVACY VIOLATION: Instructor verification box visible in student view"
        assert not student_view_data['containsTeacherRationale'], "PRIVACY VIOLATION: Teacher rationale visible in student view"
        assert not student_view_data['containsAnswerKey'], "PRIVACY VIOLATION: Answer key visible in student view"
        print("  ✓ PRIVACY AUDIT PASSED: Student view strictly isolates student prompts from teacher keys & internal rationale.")
        await take_screenshot("12_student_practice_privacy_clean.png")
        
        # STEP 8: Submit Follow-up Student Practice Response & Check Outcome
        print("\n--- STEP 8: Submit Follow-up Student Practice Response ---")
        answer_to_submit = "The cross product of vectors a and b is given by the determinant with unit vectors i, j, k in the first row."
        print(f"Submitting student practice response: '{answer_to_submit}'...")
        await evaluate(f"""
        (() => {{
            const radio = document.querySelector('input[type="radio"]');
            if (radio) {{
                radio.click();
            }} else {{
                const txt = document.querySelector('textarea.form-textarea');
                if (txt) {{
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                    nativeSetter.call(txt, '{answer_to_submit}');
                    txt.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    txt.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }}
        }})()
        """)
        await asyncio.sleep(1)
        
        print("Clicking Submit Answer button...")
        await evaluate("""
        (() => {
            const submitBtn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText === 'Submit Answer' || b.innerText.includes('Submit')
            );
            if (submitBtn) submitBtn.click();
        })()
        """)
        await asyncio.sleep(2)
        await take_screenshot("13_student_response_submitted.png")
        
        # Check topic progress in Student View
        print("Clicking '📊 Topic Progress' in Student View...")
        await evaluate("""
        (() => {
            const progBtn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText.includes('Topic Progress')
            );
            if (progBtn) progBtn.click();
        })()
        """)
        await asyncio.sleep(2)
        await take_screenshot("14_topic_progress_report.png")
        
        # Check Intervention Outcomes in Management View
        print("Navigating to Intervention Outcomes view...")
        await evaluate("""
        (() => {
            const outBtn = Array.from(document.querySelectorAll('header nav button')).find(b => b.innerText.includes('Intervention Outcomes'));
            if (outBtn) outBtn.click();
        })()
        """)
        await asyncio.sleep(2)
        
        outcomes_info = await evaluate("""
        (() => {
            const text = document.body.innerText;
            const meta = Array.from(document.querySelectorAll('.meta-item')).map(m => m.innerText);
            return {
                textPreview: text.slice(0, 500),
                meta,
                hasOutcomes: text.includes('Outcome') || text.includes('Intervention') || text.includes('Progression')
            };
        })()
        """)
        print(f"Intervention outcomes metadata: {outcomes_info.get('meta')}")
        print(f"Intervention outcomes preview:\n{outcomes_info.get('textPreview')[:250]}...")
        await take_screenshot("15_intervention_outcomes.png")
        
        print("\n" + "=" * 80)
        print("✓ REAL UI ACCEPTANCE TEST COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        return True

if __name__ == "__main__":
    success = asyncio.run(run_ui_acceptance())
    sys.exit(0 if success else 1)
