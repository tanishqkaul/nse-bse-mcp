import sys
import subprocess
import json
import urllib.request
import time
import atexit

sys.path.insert(0, r"C:\Users\TANISHQ KAUL\Documents\Claude\Projects\PMS\nse-bse-mcp")
from server import mcp
from starlette.routing import Route

# ─── NGROK CONFIGURATION ──────────────────────────────────────────────────────
# If you have a free static domain from ngrok (e.g. "goldfish-exact-simply.ngrok-free.app"),
# paste it here. If left empty, ngrok will spin up a random dynamic URL automatically.
NGROK_DOMAIN = "unidentical-archegonial-dorsey.ngrok-free.dev"

ngrok_process = None

def start_ngrok(port: int, domain: str = None) -> str:
    global ngrok_process
    
    # 1. First, check if ngrok is already running (e.g. in another terminal window)
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as response:
            tunnels = json.loads(response.read().decode())["tunnels"]
            if tunnels:
                url = tunnels[0]["public_url"]
                print(f"\n✨ ngrok is already running! Reusing existing tunnel: {url}")
                return url
    except Exception:
        pass

    # 2. If not running, start it programmatically in the background
    cmd = ["ngrok", "http"]
    if domain:
        cmd.append(f"--domain={domain}")
    cmd.append(str(port))
    
    print(f"\n🚀 Starting ngrok tunnel on port {port}...")
    try:
        ngrok_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
        )
    except FileNotFoundError:
        print("\n⚠️ 'ngrok' command not found in your system PATH.")
        print("👉 Please download/install ngrok and ensure it is in your PATH to use auto-tunneling.\n")
        return None

    # 3. Poll the local ngrok API to wait for the tunnel to establish
    for _ in range(15):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels") as response:
                tunnels = json.loads(response.read().decode())["tunnels"]
                if tunnels:
                    url = tunnels[0]["public_url"]
                    print(f"✨ Tunnel established successfully at: {url}")
                    print(f"👉 Use this URL in your Claude/Agent connector!\n")
                    return url
        except Exception:
            pass
            
    print("\n⚠️ ngrok started but could not retrieve the tunnel URL.")
    return None

def cleanup():
    global ngrok_process
    if ngrok_process:
        print("\n🛑 Stopping background ngrok tunnel...")
        # Use taskkill on Windows to kill the command shell and all its child processes (like ngrok.exe)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(ngrok_process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

atexit.register(cleanup)

# ─── Custom Route Registration ────────────────────────────────────────────────
# Wrap the sse_app generator to mount the SSE handler at the root "/" as well
orig_sse_app = mcp.sse_app

def custom_sse_app(*args, **kwargs):
    app = orig_sse_app(*args, **kwargs)
    # Find the '/sse' route and duplicate it for '/'
    sse_route = next((r for r in app.routes if getattr(r, "path", None) == "/sse"), None)
    if sse_route:
        root_route = Route(
            "/",
            endpoint=sse_route.endpoint,
            methods=list(sse_route.methods),
            name="sse_endpoint_root"
        )
        app.routes.insert(0, root_route)
    return app

mcp.sse_app = custom_sse_app

# ─── Start Server ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = 8000
    mcp.settings.port = port
    
    # Automatically start ngrok in the background
    start_ngrok(port=port, domain=NGROK_DOMAIN)
    
    mcp.run(transport="sse")


