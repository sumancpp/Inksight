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
        
        await call("Runtime.enable")
        res = await call("Runtime.evaluate", {
            "expression": """
            Array.from(document.querySelectorAll('select.form-select option')).map(o => ({ value: o.value, text: o.text }))
            """,
            "returnByValue": True
        })
        print("Assessment Options:", res["result"]["result"]["value"])

if __name__ == "__main__":
    asyncio.run(main())
