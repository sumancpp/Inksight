import asyncio
import json
import urllib.request
import websockets
import base64
import os

async def main():
    # Fetch targets from Chrome
    req = urllib.request.urlopen("http://127.0.0.1:9222/json")
    targets = json.loads(req.read().decode())
    page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:5173" in t.get("url", ""))
    ws_url = page_target["webSocketDebuggerUrl"]
    print("Connecting to:", ws_url)
    
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
        
        await call("Page.enable")
        await call("Runtime.enable")
        
        # Evaluate title and headings
        res = await call("Runtime.evaluate", {"expression": "document.title"})
        print("Page title:", res["result"]["result"]["value"])
        
        res = await call("Runtime.evaluate", {"expression": "document.body.innerText.slice(0, 300)"})
        print("Body preview:\n", res["result"]["result"]["value"])
        
        # Take screenshot
        snap = await call("Page.captureScreenshot")
        data = base64.b64decode(snap["result"]["data"])
        with open("scripts/screenshots/00_initial.png", "wb") as f:
            f.write(data)
        print("Screenshot saved to scripts/screenshots/00_initial.png (size:", len(data), "bytes)")

if __name__ == "__main__":
    asyncio.run(main())
