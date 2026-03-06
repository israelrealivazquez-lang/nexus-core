#!/usr/bin/env python3
"""
Nexus Sentinel — HuggingFace Spaces Dashboard + Keep-Alive
Deploy as a Gradio app on HuggingFace Spaces (free tier).
This app serves as the immortal sentinel that never sleeps.
"""
import json
import os
import time
import threading
from datetime import datetime, timezone

try:
    import gradio as gr
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "gradio"])
    import gradio as gr

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# ============================================================
# State
# ============================================================
SENTINEL_STATE = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "last_check": None,
    "checks_count": 0,
    "providers": {},
    "last_migration": None,
    "alerts": [],
}

PROVIDERS = [
    {"name": "GitHub Codespaces", "url": "https://api.github.com", "type": "api"},
    {"name": "Gitpod", "url": "https://gitpod.io", "type": "url"},
    {"name": "Google Cloud Shell", "url": "https://shell.cloud.google.com", "type": "url"},
    {"name": "HuggingFace Spaces", "url": "https://huggingface.co", "type": "url"},
    {"name": "Oracle Cloud", "url": "https://cloud.oracle.com", "type": "url"},
    {"name": "Supabase", "url": None, "type": "env", "env": "SUPABASE_URL"},
]

# ============================================================
# Check functions
# ============================================================
def check_provider(provider):
    """Check if a provider is reachable."""
    try:
        if provider["type"] == "url" and provider.get("url"):
            r = requests.get(provider["url"], timeout=10)
            return {"status": "online" if r.status_code < 500 else "degraded",
                    "code": r.status_code, "latency_ms": int(r.elapsed.total_seconds() * 1000)}
        elif provider["type"] == "api" and provider.get("url"):
            r = requests.get(provider["url"], timeout=10)
            return {"status": "online" if r.status_code < 500 else "degraded",
                    "code": r.status_code, "latency_ms": int(r.elapsed.total_seconds() * 1000)}
        elif provider["type"] == "env":
            val = os.environ.get(provider.get("env", ""), "")
            return {"status": "configured" if val else "not_configured"}
        return {"status": "unknown"}
    except Exception as e:
        return {"status": "offline", "error": str(e)[:100]}

def run_health_check():
    """Run health check on all providers."""
    results = {}
    for p in PROVIDERS:
        results[p["name"]] = check_provider(p)
    SENTINEL_STATE["providers"] = results
    SENTINEL_STATE["last_check"] = datetime.now(timezone.utc).isoformat()
    SENTINEL_STATE["checks_count"] += 1
    return results

# ============================================================
# Keep-alive background thread
# ============================================================
def keep_alive_loop():
    """Background loop that keeps the Space alive and runs periodic checks."""
    while True:
        try:
            run_health_check()
        except Exception as e:
            SENTINEL_STATE["alerts"].append({
                "time": datetime.now(timezone.utc).isoformat(),
                "message": f"Health check error: {str(e)[:100]}"
            })
        time.sleep(300)  # Check every 5 minutes

# Start background thread
bg_thread = threading.Thread(target=keep_alive_loop, daemon=True)
bg_thread.start()

# ============================================================
# Gradio UI
# ============================================================
def get_dashboard():
    """Generate dashboard view."""
    run_health_check()
    
    lines = []
    lines.append(f"# 🛰️ Nexus Sentinel Dashboard")
    lines.append(f"**Started**: {SENTINEL_STATE['started_at']}")
    lines.append(f"**Last Check**: {SENTINEL_STATE['last_check']}")
    lines.append(f"**Total Checks**: {SENTINEL_STATE['checks_count']}")
    lines.append("")
    lines.append("## Provider Status")
    lines.append("| Provider | Status | Details |")
    lines.append("|----------|--------|---------|")
    
    for name, info in SENTINEL_STATE["providers"].items():
        status = info.get("status", "unknown")
        emoji = {"online": "🟢", "configured": "🔵", "degraded": "🟡",
                 "offline": "🔴", "not_configured": "⚪", "unknown": "⚪"}.get(status, "⚪")
        details = []
        if "latency_ms" in info:
            details.append(f"{info['latency_ms']}ms")
        if "code" in info:
            details.append(f"HTTP {info['code']}")
        if "error" in info:
            details.append(info["error"][:50])
        lines.append(f"| {name} | {emoji} {status} | {', '.join(details)} |")
    
    if SENTINEL_STATE["alerts"]:
        lines.append("")
        lines.append("## Recent Alerts")
        for alert in SENTINEL_STATE["alerts"][-5:]:
            lines.append(f"- `{alert['time']}`: {alert['message']}")
    
    return "\n".join(lines)

def ping():
    """Keep-alive endpoint."""
    return f"pong {datetime.now(timezone.utc).isoformat()}"

def get_state_json():
    """Return full state as JSON."""
    return json.dumps(SENTINEL_STATE, indent=2, default=str)

# Build the Gradio app
with gr.Blocks(title="Nexus Sentinel", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🛰️ Nexus Sentinel — El Nómada Inmortal")
    gr.Markdown("Sistema de monitoreo multi-cloud 24/7")
    
    with gr.Tab("Dashboard"):
        dashboard_output = gr.Markdown(value=get_dashboard)
        refresh_btn = gr.Button("🔄 Refresh", variant="primary")
        refresh_btn.click(fn=get_dashboard, outputs=dashboard_output)
    
    with gr.Tab("Raw State"):
        state_output = gr.Code(value=get_state_json, language="json")
        state_btn = gr.Button("🔄 Refresh State")
        state_btn.click(fn=get_state_json, outputs=state_output)
    
    with gr.Tab("Keep-Alive"):
        gr.Markdown("### Ping endpoint for external cron jobs")
        ping_output = gr.Textbox(value=ping)
        ping_btn = gr.Button("🏓 Ping")
        ping_btn.click(fn=ping, outputs=ping_output)

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
