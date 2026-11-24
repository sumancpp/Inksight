import asyncio
import json
import urllib.request
import websockets
import base64
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
        
        await call("Page.enable")
        await call("DOM.enable")
        await call("Runtime.enable")
        
        # Get file input objectId
        res = await call("Runtime.evaluate", {"expression": "document.querySelector('input[type=\"file\"]')"})
        obj_id = res["result"]["result"]["objectId"]
        print("File input objectId:", obj_id)
        
        abs_path = os.path.abspath("/home/suman/Desktop/TechFestProject/LearnGraph/sample_engineering_math.jpg")
        await call("DOM.setFileInputFiles", {"files": [abs_path], "objectId": obj_id})
        print("DOM.setFileInputFiles called with:", abs_path)
        
        # Check if selectedFile changed in React / DOM
        await asyncio.sleep(1)
        check = await call("Runtime.evaluate", {
            "expression": "document.querySelector('.file-preview-name')?.innerText || document.body.innerText.slice(0, 500)"
        })
        print("DOM text after upload:\n", check["result"]["result"]["value"])
        
        # Capture screenshot
        snap = await call("Page.captureScreenshot")
        data = base64.b64decode(snap["result"]["data"])
        out_path = "/home/suman/Desktop/TechFestProject/LearnGraph/scripts/screenshots/01_file_selected.png"
        with open(out_path, "wb") as f:
            f.write(data)
        print("Saved screenshot to", out_path)

if __name__ == "__main__":
    asyncio.run(main())
