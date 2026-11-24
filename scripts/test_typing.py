import asyncio
import json
import urllib.request
import websockets

async def main():
    req = urllib.request.urlopen("http://127.0.0.1:9222/json")
    targets = json.loads(req.read().decode())
    page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:5173" in t.get("url", ""))
    ws_url = page_target["webSocketDebuggerUrl"]
    
    async with websockets.connect(ws_url) as ws:
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
                    return resp
        
        # Test nativeSetter
        res = await call("Runtime.evaluate", {
            "expression": """
            (() => {
                const textarea = document.querySelector('.matching-tab-content textarea.form-textarea');
                if (!textarea) return 'No textarea currently';
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                nativeSetter.call(textarea, 'a × b = |i j k; a1 a2 a3; b1 b2 b3|');
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                textarea.dispatchEvent(new Event('change', { bubbles: true }));
                return textarea.value;
            })()
            """,
            "returnByValue": True
        })
        print("nativeSetter test result:", res["result"]["result"]["value"])

if __name__ == "__main__":
    asyncio.run(main())
