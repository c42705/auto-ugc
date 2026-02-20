"""
Final integration layer for uxai-ugc-agent.
Flask + SocketIO server to manage the multi-agent pipeline and web interface.
"""

import os
import threading
import argparse
import webbrowser
import psutil
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
from dotenv import load_dotenv, set_key

# Load environment before anything else
load_dotenv()

from agents.orchestrator import Orchestrator
from config import config
from utils.logger import log

app = Flask(__name__, static_folder="web/static")
CORS(app)
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# Initialize Orchestrator with socketio for live updates
orchestrator = Orchestrator(socketio=socketio)

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/api/run", methods=["POST"])
def run_pipeline():
    data = request.json or {}
    topic = data.get("topic")
    
    if orchestrator.status == "running":
        return jsonify({"error": "Pipeline is already running"}), 400
        
    # Start orchestrator in a background thread
    thread = threading.Thread(target=orchestrator.run_pipeline, args=(topic,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "message": "Pipeline started",
        "session_id": orchestrator.session_id
    })

@app.route("/api/status", methods=["GET"])
def get_status():
    status = orchestrator.get_status()
    # Add RAM usage info
    status["ram_percent"] = psutil.virtual_memory().percent
    return jsonify(status)

@app.route("/api/override/<step>", methods=["POST"])
def submit_override(step):
    data = request.json or {}
    orchestrator.submit_human_override(step, data)
    return jsonify({"status": "received"})

@app.route("/api/files/<path:filename>")
def serve_files(filename):
    # Security: Ensure we only serve from the output directory
    return send_from_directory(config.OUTPUT_DIR, filename)

@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json or {}
    updated_keys = []
    
    env_file = ".env"
    if data.get("timeout"):
        set_key(env_file, "HUMAN_REVIEW_TIMEOUT_SECONDS", str(data["timeout"]))
        config.HUMAN_REVIEW_TIMEOUT_SECONDS = int(data["timeout"])
        updated_keys.append("HUMAN_REVIEW_TIMEOUT_SECONDS")
        
    if data.get("threshold"):
        set_key(env_file, "QA_AUTO_APPROVE_THRESHOLD", str(data["threshold"]))
        config.QA_AUTO_APPROVE_THRESHOLD = float(data["threshold"])
        updated_keys.append("QA_AUTO_APPROVE_THRESHOLD")
        
    if data.get("ntfy"):
        set_key(env_file, "NTFY_URL", data["ntfy"])
        config.NTFY_URL = data["ntfy"]
        updated_keys.append("NTFY_URL")
        
    if data.get("model"):
        set_key(env_file, "OPENROUTER_MODEL_MAIN", data["model"])
        config.OPENROUTER_MODEL_MAIN = data["model"]
        updated_keys.append("OPENROUTER_MODEL_MAIN")
    
    return jsonify({"updated": updated_keys})

@app.route("/api/health")
def health_check():
    mem = psutil.virtual_memory()
    return jsonify({
        "status": "ok",
        "ram_mb": round(mem.available / (1024*1024), 2),
        "version": "1.0"
    })

def check_env():
    required = [
        "OPENROUTER_API_KEY", "ELEVENLABS_API_KEY", 
        "HEYGEN_API_KEY", "OPENAI_API_KEY"
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        log.warning(f"Missing API keys in .env: {', '.join(missing)}. Some pipeline steps may fail.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", action="store_true", help="Start web server only")
    parser.add_argument("--run", type=str, help="Run pipeline headless with topic")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    
    check_env()
    
    if args.run:
        log.info(f"Starting headless run for topic: {args.run}")
        try:
            results = orchestrator.run_pipeline(topic_override=args.run)
            log.success("Headless run complete.")
            print(json.dumps(results, indent=2))
        except Exception as e:
            log.error(f"Headless run failed: {e}")
            exit(1)
    else:
        # Defaults to web mode
        url = f"http://localhost:{args.port}"
        log.info(f"Starting web server at {url}")
        # Only open browser if not in a containerized environment (optional but nice)
        if os.environ.get("OPEN_BROWSER", "true").lower() == "true":
            webbrowser.open(url)
        socketio.run(app, host="0.0.0.0", port=args.port)
