import asyncio
import json
import urllib.request
import websockets
import os

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
        
        await call("DOM.enable")
        await call("Runtime.enable")
        
        res = await call("Runtime.evaluate", {"expression": "document.querySelector('input[type=\"file\"]')"})
        obj_id = res["result"]["result"]["objectId"]
        abs_path = os.path.abspath("/home/suman/Desktop/TechFestProject/LearnGraph/sample_engineering_math.jpg")
        await call("DOM.setFileInputFiles", {"files": [abs_path], "objectId": obj_id})
        
        # Dispatch change event
        await call("Runtime.evaluate", {
            "expression": """
            const input = document.querySelector('input[type="file"]');
            input.dispatchEvent(new Event('change', { bubbles: true }));
            """
        })
        
        await asyncio.sleep(1)
        res = await call("Runtime.evaluate", {
            "expression": """
            ({
                fileName: document.querySelector('.file-preview-name')?.innerText,
                hasSelectedCard: !!document.querySelector('.selected-file-card'),
                buttons: Array.from(document.querySelectorAll('button')).map(b => b.innerText)
            })
            """,
            "returnByValue": True
        })
        print("React state after change event:", res["result"]["result"]["value"])

if __name__ == "__main__":
    asyncio.run(main())
