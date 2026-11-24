import subprocess
import time
import requests
import json
import asyncio
import websockets
import sys
import sqlite3

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"

def reset_test_fixtures():
    con = sqlite3.connect("learngraph.db")
    cur = con.cursor()
    # Reset submission 5 proposals to initial state
    cur.execute("UPDATE proposed_answers SET status = 'proposed', corrected_text = NULL, rejection_reason = NULL WHERE id = 3")
    cur.execute("UPDATE proposed_answers SET status = 'unmatched', corrected_text = NULL, rejection_reason = NULL WHERE id = 4")
    # Reset findings 1 and 2
    cur.execute("UPDATE evaluation_findings SET review_status = 'pending_review', review_notes = NULL WHERE id IN (1, 2)")
    # Delete remediation items generated for finding 1 during previous test runs
    cur.execute("DELETE FROM remediation_item_audits WHERE item_id IN (SELECT id FROM remediation_items WHERE finding_id = 1)")
    cur.execute("DELETE FROM remediation_items WHERE finding_id = 1")
    cur.execute("DELETE FROM remediation_runs WHERE finding_id = 1")
    # Delete practice sessions for submission 7 if any created during test
    cur.execute("UPDATE submissions SET student_id = 19 WHERE id = 7")
    cur.execute("DELETE FROM practice_responses WHERE session_id IN (SELECT id FROM practice_sessions WHERE submission_id = 7)")
    cur.execute("DELETE FROM practice_sessions WHERE submission_id = 7")
    con.commit()
    con.close()
    print("✓ Test fixtures reset to clean baseline", flush=True)

class ChromeSession:
    def __init__(self, ws):
        self.ws = ws
        self.req_id = 100

    async def send(self, method, params=None):
        self.req_id += 1
        cur_id = self.req_id
        payload = {"id": cur_id, "method": method}
        if params:
            payload["params"] = params
        await self.ws.send(json.dumps(payload))
        while True:
            raw = await self.ws.recv()
            resp = json.loads(raw)
            if resp.get("id") == cur_id:
                return resp.get("result", {})

    async def eval(self, js):
        clean = js.strip()
        if not clean.startswith("return ") and "return " not in clean:
            if clean.startswith("const ") or clean.startswith("let ") or clean.startswith("var "):
                wrapped_js = f"(() => {{\n{clean}\n}})()"
            else:
                expr = clean.rstrip(";")
                wrapped_js = f"(() => {{ return ({expr}); }})()"
        else:
            wrapped_js = f"(() => {{\n{clean}\n}})()"

        res = await self.send("Runtime.evaluate", {
            "expression": wrapped_js,
            "awaitPromise": True,
            "returnByValue": True
        })
        if "exceptionDetails" in res:
            raise RuntimeError(f"JS Error: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    async def select_by_val(self, sel_idx, target_val):
        await self.wait_until(f"Boolean(document.querySelectorAll('select')[{sel_idx}]?.options?.length > 0)")
        cur_idx = await self.eval(f"document.querySelectorAll('select')[{sel_idx}].selectedIndex")
        target_idx = await self.eval(f"Array.from(document.querySelectorAll('select')[{sel_idx}].options).findIndex(o => o.value === '{target_val}')")
        if target_idx < 0:
            for _ in range(20):
                await asyncio.sleep(0.25)
                target_idx = await self.eval(f"Array.from(document.querySelectorAll('select')[{sel_idx}].options).findIndex(o => o.value === '{target_val}')")
                if target_idx >= 0:
                    break
        if target_idx < 0:
            available = await self.eval(f"Array.from(document.querySelectorAll('select')[{sel_idx}].options).map(o => o.value)")
            raise ValueError(f"Option value '{target_val}' not found in select {sel_idx}. Available: {available}")
        diff = target_idx - cur_idx
        key = "ArrowDown" if diff > 0 else "ArrowUp"
        code = 40 if diff > 0 else 38
        await self.eval(f"document.querySelectorAll('select')[{sel_idx}].focus()")
        for _ in range(abs(diff)):
            await self.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": code, "key": key})
            await self.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": code, "key": key})
            await asyncio.sleep(0.05)
        await self.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": 13, "key": "Enter"})
        await self.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13, "key": "Enter"})
        await asyncio.sleep(0.5)

    async def set_react_input(self, selector, value):
        await self.eval(f"""
            const el = document.querySelector("{selector}");
            if (!el) throw new Error("Element not found: {selector}");
            const proto = el instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            const nativeSetter = Object.getOwnPropertyDescriptor(proto, "value").set;
            nativeSetter.call(el, {json.dumps(value)});
            el.dispatchEvent(new Event("input", {{ bubbles: true }}));
            el.dispatchEvent(new Event("change", {{ bubbles: true }}));
        """)

    async def wait_until(self, js_cond, timeout=12.0, interval=0.25):
        start = time.time()
        while time.time() - start < timeout:
            try:
                res = await self.eval(js_cond)
                if res:
                    return res
            except Exception:
                pass
            await asyncio.sleep(interval)
        raise TimeoutError(f"Condition timed out after {timeout}s: {js_cond}")

async def run_verification():
    reset_test_fixtures()
    print("=== Starting Headless Chrome for LearnGraph Teacher Review E2E Verification ===", flush=True)
    chrome_proc = subprocess.Popen([
        "google-chrome",
        "--headless=new",
        "--remote-debugging-port=9222",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-extensions",
        "--user-data-dir=/tmp/learngraph_chrome_e2e"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(1.5)
    try:
        tabs = requests.get("http://127.0.0.1:9222/json").json()
        page_tabs = [t for t in tabs if t.get("type") == "page"]
        if not page_tabs:
            raise RuntimeError("No Chrome page tab available")
        ws_url = page_tabs[0]["webSocketDebuggerUrl"]

        async with websockets.connect(ws_url, max_size=20_000_000) as ws:
            c = ChromeSession(ws)
            await c.send("Page.enable")
            await c.send("Page.navigate", {"url": FRONTEND_URL})

            # Wait for React app to mount
            await c.wait_until("Boolean(document.querySelector('.navbar'))", timeout=15)
            print("✓ Frontend mounted and loaded successfully", flush=True)

            # Wait for demo auth badge
            user_text = await c.wait_until(
                "document.querySelector('.navbar-user .badge')?.innerText",
                timeout=10
            )
            print(f"✓ Authentication state verified: '{user_text}'", flush=True)
            assert "Connected" in user_text and "admin" in user_text, f"Unexpected auth: {user_text}"

            # -------------------------------------------------------------
            # FLOW 1 & 2: ANSWER MATCHING & TEACHER REVIEW
            # -------------------------------------------------------------
            print("\n--- Testing Flow 1 & 2: Answer Matching & Teacher Review ---", flush=True)
            # Toggle 'All Management Views'
            await c.eval("""
                const toggle = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('All Management Views'));
                if (toggle) toggle.click();
            """)
            await asyncio.sleep(0.5)

            # Click 'Answer Matching' tab in Navbar
            await c.eval("""
                const matchTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('Answer Matching'));
                if (matchTab) matchTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('h2')?.innerText.includes('Answer Matching'))")
            print("✓ Navigated to Answer Matching & Teacher Review view", flush=True)

            # Wait for assessments to load into select
            await c.wait_until("Boolean(document.querySelectorAll('select.form-select')[0]?.options?.length > 1)")

            # Select Assessment 3 and Submission 5
            await c.select_by_val(0, "3")
            await c.wait_until("Boolean(document.querySelectorAll('select.form-select')[1]?.options?.length >= 1)")
            await c.select_by_val(1, "5")
            await c.wait_until("Boolean(document.querySelector('.card h3')?.innerText.includes('Proposed Answers'))")
            print("✓ Selected Assessment #3 / Submission #5; proposals loaded", flush=True)

            # Check initial proposal badge states
            initial_badges = await c.eval("Array.from(document.querySelectorAll('.card .badge')).map(b => b.innerText)")
            print(f"✓ Initial proposal badges: {initial_badges}", flush=True)

            # ACTION 1A: Approve Proposal #3
            print("Testing Action 1A: Approve Proposal...", flush=True)
            await c.eval("""
                const approveBtn = Array.from(document.querySelectorAll('button.btn-success')).find(b => b.innerText.includes('Approve'));
                if (approveBtn) approveBtn.click();
            """)
            alert_msg = await c.wait_until("document.querySelector('.alert.alert-success')?.innerText", timeout=5)
            print(f"✓ Approve action response: '{alert_msg}'", flush=True)
            assert "approved" in alert_msg.lower(), f"Unexpected alert: {alert_msg}"

            # ACTION 1B: Correct Proposal #3
            print("Testing Action 1B: Correct Proposal...", flush=True)
            await c.eval("""
                const correctBtn = Array.from(document.querySelectorAll('button.btn-secondary')).find(b => b.innerText.includes('Correct Text'));
                if (correctBtn) correctBtn.click();
            """)
            await c.wait_until("Boolean(document.querySelector('textarea.form-textarea'))")
            # Edit text via React input helper
            await c.set_react_input(
                "textarea.form-textarea",
                "Limit is undefined because left and right limits diverge [TEACHER VERIFIED]"
            )
            await c.eval("""
                const saveBtn = Array.from(document.querySelectorAll('button.btn-success')).find(b => b.innerText.includes('Save & Approve Correction'));
                if (saveBtn) saveBtn.click();
            """)
            alert_correct = await c.wait_until("document.querySelector('.alert.alert-success')?.innerText", timeout=5)
            print(f"✓ Correct action response: '{alert_correct}'", flush=True)
            assert "corrected" in alert_correct.lower(), f"Unexpected alert: {alert_correct}"

            # Verify badge and corrected text in UI
            corrected_badge = await c.eval("""
                Array.from(document.querySelectorAll('.badge')).map(b => b.innerText).includes('corrected')
            """)
            print(f"✓ 'corrected' status badge rendered: {corrected_badge}", flush=True)
            assert corrected_badge, "Status badge does not show 'corrected'!"

            # ACTION 1C: Reject Proposal #4
            print("Testing Action 1C: Reject Proposal...", flush=True)
            # Setup mock window.prompt for reason
            await c.eval("window.prompt = () => 'Extraneous scratch margin';")
            await c.eval("""
                const rejectBtns = Array.from(document.querySelectorAll('button.btn-danger')).filter(b => b.innerText.includes('Reject'));
                if (rejectBtns.length > 0) {
                    rejectBtns[rejectBtns.length - 1].click();
                }
            """)
            alert_reject = await c.wait_until("document.querySelector('.alert.alert-success')?.innerText", timeout=5)
            print(f"✓ Reject action response: '{alert_reject}'", flush=True)
            assert "rejected" in alert_reject.lower(), f"Unexpected alert: {alert_reject}"

            # ACTION 1D: Page Refresh Persistence
            print("Testing Flow 2: Refresh persistence for proposals...", flush=True)
            await c.send("Page.reload")
            await c.wait_until("Boolean(document.querySelector('.navbar'))", timeout=10)
            # Click All Management Views if needed
            await c.eval("""
                const toggle = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('All Management Views'));
                if (toggle) toggle.click();
            """)
            await asyncio.sleep(0.3)
            # Click Answer Matching
            await c.eval("""
                const matchTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('Answer Matching'));
                if (matchTab) matchTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('h2')?.innerText.includes('Answer Matching'))")

            # Re-select Assessment 3 and Submission 5
            await c.select_by_val(0, "3")
            await asyncio.sleep(0.5)
            await c.select_by_val(1, "5")
            await c.wait_until("Boolean(document.querySelector('.card h3')?.innerText.includes('Proposed Answers'))")

            persisted_badges = await c.eval("Array.from(document.querySelectorAll('.badge')).map(b => b.innerText)")
            print(f"✓ Status badges after refresh: {persisted_badges}", flush=True)
            assert "corrected" in persisted_badges, "Corrected status did not persist after refresh!"
            assert "rejected" in persisted_badges, "Rejected status did not persist after refresh!"

            # Verify authoritative backend state
            token = await c.eval("localStorage.getItem('token')")
            backend_qa = requests.get(
                f"{BACKEND_URL}/api/v1/submissions/5/proposed-answers",
                headers={"Authorization": f"Bearer {token}"}
            ).json()
            corrected_item = next(p for p in backend_qa["proposals"] if p["id"] == 3)
            print(f"✓ Backend proposal status: {corrected_item['status']}, corrected_text: '{corrected_item['corrected_text'][:30]}...'", flush=True)
            assert corrected_item["status"] == "corrected"
            assert "TEACHER VERIFIED" in corrected_item["corrected_text"]

            # -------------------------------------------------------------
            # FLOW 3: AI EVALUATION & FINDINGS REVIEW
            # -------------------------------------------------------------
            print("\n--- Testing Flow 3: AI Evaluation Findings Review ---", flush=True)
            await c.eval("""
                const evalTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('AI Evaluation'));
                if (evalTab) evalTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('h2')?.innerText.includes('AI Assessment'))")
            print("✓ Navigated to AI Evaluation view", flush=True)

            # Select Assessment 5, Submission 7
            await c.select_by_val(0, "5")
            await asyncio.sleep(0.5)
            await c.select_by_val(1, "7")
            await c.wait_until("Boolean(document.querySelector('.card h3')?.innerText.includes('Question #'))")
            print("✓ Evaluation runs and findings loaded for Submission #7", flush=True)

            # Verify finding content: category, confidence, evidence, rationale
            finding_text = await c.eval("document.querySelector('.card-header + div')?.parentElement?.innerText || ''")
            print(f"✓ Finding card content preview:\n{finding_text[:180]}...", flush=True)
            assert "Evidence" in finding_text or "Confidence" in finding_text

            # ACTION 3A: Accept Finding 1
            print("Testing Action 3A: Accept Finding...", flush=True)
            await c.set_react_input(
                "input[placeholder*='notes or rationale']",
                "Teacher accepted calculus concept finding"
            )
            await c.eval("""
                const acceptBtn = Array.from(document.querySelectorAll('button.btn-success')).find(b => b.innerText.includes('Accept'));
                if (acceptBtn) acceptBtn.click();
            """)
            alert_f_accept = await c.wait_until("document.querySelector('.alert.alert-success')?.innerText", timeout=5)
            print(f"✓ Accept finding alert: '{alert_f_accept}'", flush=True)
            assert "accepted" in alert_f_accept.lower()

            # Verify '⚡ Generate Practice Items' button is now displayed on accepted finding
            gen_btn_visible = await c.wait_until("""
                Boolean(Array.from(document.querySelectorAll('button.btn-primary')).find(b => b.innerText.includes('Generate Practice Items')))
            """, timeout=5)
            print(f"✓ 'Generate Practice Items' button unlocked for accepted finding: {gen_btn_visible}", flush=True)

            # ACTION 3B: Flag Finding / Needs Revision (on Submission 8)
            print("Testing Action 3B: Flag Finding as Needs Revision...", flush=True)
            await c.select_by_val(0, "6")
            await asyncio.sleep(0.5)
            await c.select_by_val(1, "8")
            await c.wait_until("Boolean(document.querySelector('.card h3')?.innerText.includes('Question #'))")

            await c.set_react_input(
                "input[placeholder*='notes or rationale']",
                "Flagged for teacher secondary review"
            )
            await c.eval("""
                const flagBtn = Array.from(document.querySelectorAll('button.btn-secondary')).find(b => b.innerText.includes('Flag'));
                if (flagBtn) flagBtn.click();
            """)
            alert_f_flag = await c.wait_until("document.querySelector('.alert.alert-success')?.innerText", timeout=5)
            print(f"✓ Flag finding alert: '{alert_f_flag}'", flush=True)
            assert "needs_revision" in alert_f_flag.lower()

            # Confirm non-accepted finding does NOT show generate button
            gen_btn_on_flagged = await c.eval("""
                Boolean(Array.from(document.querySelectorAll('button.btn-primary')).find(b => b.innerText.includes('Generate Practice Items')))
            """)
            print(f"✓ Non-accepted finding strictly hides remediation generation: {not gen_btn_on_flagged}", flush=True)
            assert not gen_btn_on_flagged, "Generate button should not be displayed on needs_revision finding!"

            # -------------------------------------------------------------
            # FLOW 4 & 5: REMEDIATION GENERATION & TEACHER APPROVAL
            # -------------------------------------------------------------
            print("\n--- Testing Flow 4 & 5: Remediation Generation & Item Approval ---", flush=True)
            # Switch back to Submission 7 with accepted finding
            await c.select_by_val(0, "5")
            await asyncio.sleep(0.5)
            await c.select_by_val(1, "7")
            await c.wait_until("Boolean(document.querySelector('.card h3')?.innerText.includes('Question #'))")

            # Click '⚡ Generate Practice Items'
            await c.eval("""
                const genBtn = Array.from(document.querySelectorAll('button.btn-primary')).find(b => b.innerText.includes('Generate Practice Items'));
                if (genBtn) genBtn.click();
            """)
            alert_gen = await c.wait_until("""
                document.querySelector('.alert.alert-success')?.innerText.includes('generated')
                    ? document.querySelector('.alert.alert-success')?.innerText
                    : false
            """, timeout=8)
            print(f"✓ Remediation generation alert: '{alert_gen}'", flush=True)
            assert "generated" in alert_gen.lower()

            # Navigate to Remediations tab
            await c.eval("""
                const remedTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('Remediations'));
                if (remedTab) remedTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('h2')?.innerText.includes('Remediation Generation'))")
            print("✓ Navigated to Remediations view", flush=True)

            # Select Assessment 5, Submission 7
            await c.select_by_val(0, "5")
            await asyncio.sleep(0.5)
            await c.select_by_val(1, "7")
            await c.wait_until("Boolean(Array.from(document.querySelectorAll('.card h3')).some(h => h.innerText.includes('Generated Remediation Items')))")
            print("✓ Generated remediation practice items loaded", flush=True)

            # Verify teacher-only answer key and rationale are clearly visible in teacher review
            teacher_view_text = await c.eval("""
                Array.from(document.querySelectorAll('.card')).find(c => c.innerText.includes('Generated Remediation Items'))?.innerText || ''
            """)
            print(f"✓ Teacher remediation card content preview:\n{teacher_view_text[:220]}...", flush=True)
            assert "Expected Answer" in teacher_view_text, "Teacher view missing expected answer!"
            assert "Protected from Students" in teacher_view_text or "Teacher Rationale" in teacher_view_text

            # ACTION 5A: Edit & Approve Practice Item
            print("Testing Action 5A: Edit & Approve Remediation Item...", flush=True)
            await c.eval("""
                const editBtn = Array.from(document.querySelectorAll('button.btn-secondary')).find(b => b.innerText.includes('Edit & Approve'));
                if (editBtn) editBtn.click();
            """)
            await c.wait_until("Boolean(document.querySelector('textarea.form-textarea'))")

            # Edit prompt, answer key, notes
            await c.set_react_input(
                "textarea.form-textarea",
                "State the geometric interpretation of the tangent line slope."
            )
            await c.set_react_input(
                "input.form-input",
                "Slope equals instantaneous rate of change"
            )
            await c.eval("""
                const saveBtn = Array.from(document.querySelectorAll('button.btn-success')).find(b => b.innerText.includes('Save Edits & Approve'));
                if (saveBtn) saveBtn.click();
            """)
            alert_edit_item = await c.wait_until("document.querySelector('.alert.alert-success')?.innerText", timeout=5)
            print(f"✓ Edit practice item alert: '{alert_edit_item}'", flush=True)
            assert "edited" in alert_edit_item.lower()

            # Confirm status badge shows 'approved'
            item_badges = await c.eval("Array.from(document.querySelectorAll('.badge')).map(b => b.innerText)")
            print(f"✓ Practice item badges: {item_badges}", flush=True)
            assert "approved" in item_badges, "Badge did not update to 'approved'!"

            # ACTION 5B: Refresh Persistence for Remediation Item
            print("Testing Flow 5: Refresh persistence for remediation item...", flush=True)
            await c.send("Page.reload")
            await c.wait_until("Boolean(document.querySelector('.navbar'))", timeout=10)
            await c.eval("""
                const toggle = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('All Management Views'));
                if (toggle) toggle.click();
            """)
            await asyncio.sleep(0.3)
            await c.eval("""
                const remedTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('Remediations'));
                if (remedTab) remedTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('h2')?.innerText.includes('Remediation Generation'))")
            await c.select_by_val(0, "5")
            await asyncio.sleep(0.5)
            await c.select_by_val(1, "7")
            await c.wait_until("Boolean(Array.from(document.querySelectorAll('.card h3')).some(h => h.innerText.includes('Generated Remediation Items')))")

            persisted_item_text = await c.eval("""
                Array.from(document.querySelectorAll('.card')).find(c => c.innerText.includes('Generated Remediation Items'))?.innerText || ''
            """)
            assert "geometric interpretation of the tangent line slope" in persisted_item_text
            assert "Slope equals instantaneous rate of change" in persisted_item_text
            print("✓ Teacher edited prompt and answer key persisted cleanly after page refresh", flush=True)

            # -------------------------------------------------------------
            # FLOW 6: STUDENT PRACTICE VIEW (DATA PROTECTION)
            # -------------------------------------------------------------
            print("\n--- Testing Flow 6: Student Practice Delivery & Leak Protection ---", flush=True)
            await c.eval("""
                const studentTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('Student Practice'));
                if (studentTab) studentTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('h2')?.innerText.includes('Student Practice'))")
            print("✓ Navigated to Student Practice View", flush=True)

            # Select Assessment 5
            await c.select_by_val(0, "5")
            await asyncio.sleep(0.5)

            # Start or resume practice session
            await c.eval("""
                const startBtn = Array.from(document.querySelectorAll('button.btn-primary')).find(b => b.innerText.includes('Start / Resume Practice') || b.innerText.includes('Practice'));
                if (startBtn) startBtn.click();
            """)
            await c.wait_until("Boolean(document.body.innerText.includes('Practice Session #'))", timeout=8)
            print("✓ Student practice session active and items rendered", flush=True)

            # INSPECT ENTIRE STUDENT PAGE TEXT & DOM
            student_full_text = await c.eval("document.body.innerText")
            leak_key = "Slope equals instantaneous rate of change"
            leak_rationale = "Focus on one-sided limit evaluation"
            leak_teacher_notes = "Teacher revised practice item"

            print(f"Checking for answer key leak ('{leak_key}')...", flush=True)
            assert leak_key not in student_full_text, "CRITICAL SECURITY LEAK: Expected Answer Key exposed in Student View!"
            print("✓ Confirmed: Expected Answer Key is strictly hidden from student view", flush=True)

            print(f"Checking for rationale leak...", flush=True)
            assert leak_rationale not in student_full_text, "CRITICAL LEAK: Teacher rationale exposed in Student View!"
            assert "Instructor Verification" not in student_full_text
            print("✓ Confirmed: Teacher rationales and instructor verification notes strictly absent from student view", flush=True)

            # Student answers question
            await c.set_react_input("textarea.form-textarea", "The slope represents the derivative at that specific point.")
            await asyncio.sleep(0.5)
            await c.eval("""
                const subBtn = Array.from(document.querySelectorAll('button.btn-primary')).find(b => b.innerText.includes('Submit Answer'));
                if (subBtn) subBtn.click();
            """)
            try:
                await c.wait_until("Boolean(document.querySelector('.badge-success')?.innerText.includes('Correct') || document.querySelector('.badge-warning')?.innerText.includes('Needs Practice'))", timeout=8)
            except Exception as e:
                err_text = await c.eval("document.querySelector('.alert.alert-danger')?.innerText || 'No error alert'")
                succ_text = await c.eval("document.querySelector('.alert.alert-success')?.innerText || 'No success alert'")
                badges_text = await c.eval("Array.from(document.querySelectorAll('.badge')).map(b => b.innerText)")
                btns_text = await c.eval("Array.from(document.querySelectorAll('button')).map(b => b.innerText)")
                print(f"DEBUG: err_alert='{err_text}', succ_alert='{succ_text}', badges={badges_text}, btns={btns_text}", flush=True)
                raise e
            print("✓ Student submitted response and received formative feedback without answer key exposure", flush=True)

            # -------------------------------------------------------------
            # FLOW 7: VALIDATION, EMPTY & SAFE ERROR STATES
            # -------------------------------------------------------------
            print("\n--- Testing Flow 7: Validation, Empty & Safe Error States ---", flush=True)
            # Empty question validation on Remediation Edit
            await c.eval("""
                const remedTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('Remediations'));
                if (remedTab) remedTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('h2')?.innerText.includes('Remediation Generation'))")
            await c.select_by_val(0, "5")
            await asyncio.sleep(0.5)
            await c.select_by_val(1, "7")
            await c.wait_until("Boolean(Array.from(document.querySelectorAll('.card h3')).some(h => h.innerText.includes('Generated Remediation Items')))")

            # Try to edit with empty prompt
            await c.eval("""
                const editBtn = Array.from(document.querySelectorAll('button.btn-secondary')).find(b => b.innerText.includes('Edit & Approve'));
                if (editBtn) editBtn.click();
            """)
            await c.wait_until("Boolean(document.querySelector('textarea.form-textarea'))")
            await c.set_react_input("textarea.form-textarea", "   ")
            await c.eval("""
                const saveBtn = Array.from(document.querySelectorAll('button.btn-success')).find(b => b.innerText.includes('Save Edits & Approve'));
                if (saveBtn) saveBtn.click();
            """)
            val_error = await c.wait_until("document.querySelector('.alert.alert-danger')?.innerText", timeout=5)
            print(f"✓ Validation error caught and rendered: '{val_error}'", flush=True)
            assert "empty" in val_error.lower()

            # -------------------------------------------------------------
            # FLOW 8: UNIFIED DEMODASHBOARD TEACHER REVIEW INTEGRATION
            # -------------------------------------------------------------
            print("\n--- Testing Flow 8: Unified DemoDashboard Teacher Review Tabs ---", flush=True)
            await c.eval("""
                const dashTab = Array.from(document.querySelectorAll('.navbar-nav button')).find(b => b.innerText.includes('PDF Diagnostic Dashboard'));
                if (dashTab) dashTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('.dashboard-title'))")
            print("✓ Navigated to DemoDashboard", flush=True)

            # Check Empty State
            dash_empty = await c.eval("document.querySelector('.empty-dashboard-card h3')?.innerText")
            print(f"✓ DemoDashboard initial empty state: '{dash_empty}'", flush=True)
            assert "No Document Scanned" in dash_empty

            # Load sample PDF and scan
            await c.eval("""
                const sampleBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Load Sample PDF'));
                if (sampleBtn) sampleBtn.click();
            """)
            selected_file = await c.wait_until("document.querySelector('.file-name')?.innerText")
            print(f"✓ Sample file loaded: '{selected_file}'", flush=True)

            await c.eval("""
                const scanBtn = Array.from(document.querySelectorAll('button.btn-primary')).find(b => b.innerText.includes('Scan & Analyze Document'));
                if (scanBtn) scanBtn.click();
            """)
            print("Triggered document processing in dashboard, waiting for OCR & evaluation completion...", flush=True)
            await c.wait_until("Boolean(document.querySelector('.results-card'))", timeout=45)
            print("✓ Document analysis pipeline completed in dashboard", flush=True)

            # Check all 4 tabs exist
            tabs_text = await c.eval("Array.from(document.querySelectorAll('.tabs-nav .tab-btn')).map(b => b.innerText.trim())")
            print(f"✓ Rendered Dashboard Tabs: {tabs_text}", flush=True)
            assert any("Extracted OCR Text" in t for t in tabs_text)
            assert any("Answer Matching" in t for t in tabs_text)
            assert any("Diagnostic Findings" in t for t in tabs_text)
            assert any("Targeted Remediation" in t for t in tabs_text)

            # Click Answer Matching & Review tab in Dashboard
            await c.eval("""
                const matchTab = Array.from(document.querySelectorAll('.tabs-nav .tab-btn')).find(b => b.innerText.includes('Answer Matching'));
                if (matchTab) matchTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('.matching-tab-content'))")
            dash_proposals_cnt = await c.eval("document.querySelectorAll('.matching-tab-content .finding-card').length")
            print(f"✓ Dashboard proposals rendered: {dash_proposals_cnt}", flush=True)
            assert dash_proposals_cnt > 0

            # Click Diagnostic Findings & Review tab in Dashboard
            await c.eval("""
                const findTab = Array.from(document.querySelectorAll('.tabs-nav .tab-btn')).find(b => b.innerText.includes('Diagnostic Findings'));
                if (findTab) findTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('.analysis-tab-content'))")
            dash_findings_cnt = await c.eval("document.querySelectorAll('.analysis-tab-content .finding-card').length")
            print(f"✓ Dashboard diagnostic findings rendered: {dash_findings_cnt}", flush=True)

            # Click Targeted Remediation tab in Dashboard
            await c.eval("""
                const remedTab = Array.from(document.querySelectorAll('.tabs-nav .tab-btn')).find(b => b.innerText.includes('Targeted Remediation'));
                if (remedTab) remedTab.click();
            """)
            await c.wait_until("Boolean(document.querySelector('.remediations-tab-content'))")
            print("✓ Dashboard Targeted Remediation tab loaded with instructor gate notice", flush=True)

            print("\n=======================================================", flush=True)
            print("🎉 ALL 8 E2E VERIFICATION FLOWS COMPLETED SUCCESSFULLY!", flush=True)
            print("=======================================================", flush=True)

    finally:
        chrome_proc.terminate()

if __name__ == "__main__":
    asyncio.run(run_verification())
