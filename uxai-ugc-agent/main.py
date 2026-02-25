"""
Final integration layer for uxai-ugc-agent.
Flask + SocketIO server to manage the multi-agent pipeline and web interface.
"""

import os
import json
import threading
import argparse
import webbrowser
import psutil
from flask import Flask, jsonify, request, send_from_directory, send_file
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

@app.before_request
def check_auth():
    password = os.getenv("UI_PASSWORD")
    if password and request.path.startswith("/api/") and request.path not in ["/api/login", "/api/auth_config"]:
        client_pwd = request.headers.get("X-UI-Password") or request.args.get("pwd")
        if client_pwd != password:
            log.warning(f"[AUTH] Failed auth on {request.path} from client IP: {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401

@app.after_request
def add_cache_control(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/api/auth_config", methods=["GET"])
def auth_config():
    password = os.getenv("UI_PASSWORD")
    log.info(f"[AUTH_CONFIG] Request received. UI_PASSWORD is set: {bool(password)}")
    return jsonify({"auth_required": bool(password)})

@app.route("/api/login", methods=["POST"])
def login():
    password = os.getenv("UI_PASSWORD")
    log.info("[LOGIN API] Request received.")
    if not password:
        log.info("[LOGIN API] No UI_PASSWORD set in backend. Passing automatically.")
        return jsonify({"valid": True}) # No password set = valid
    
    data = request.get_json(silent=True) or {}
    log.info(f"[LOGIN API] Parsed JSON payload. Contains password field: {'yes' if 'password' in data else 'no'}")
    if data.get("password") == password:
        log.info("[LOGIN API] Password matched successfully.")
        return jsonify({"valid": True})
    
    log.warning("[LOGIN API] Password mismatch or empty payload.")
    return jsonify({"valid": False}), 401

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

@app.route("/api/cancel", methods=["POST"])
def cancel_pipeline():
    # Attempt to gracefully kill or reset
    if orchestrator.status == "running":
        orchestrator.status = "idle"
        # Just notify UI
        socketio.emit('pipeline_log', {'level': 'WARNING', 'msg': 'Pipeline cancelled by user.'})
        socketio.emit('step_error', {'step': orchestrator.current_step, 'error': 'Cancelled'})
    return jsonify({"status": "cancelled"})

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
    # filename can be "session_id/folder/file.ext"
    return send_from_directory(config.OUTPUT_DIR, filename)

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    sessions = []
    if not os.path.exists(config.OUTPUT_DIR):
        return jsonify({"sessions": []})
        
    for d in sorted(os.listdir(config.OUTPUT_DIR), reverse=True):
        path = os.path.join(config.OUTPUT_DIR, d)
        if os.path.isdir(path):
            # Check for common markers
            has_script = os.path.exists(os.path.join(path, "scripts", "v1_script.json"))
            has_audio = os.path.exists(os.path.join(path, "audio"))
            has_clips = os.path.exists(os.path.join(path, "clips")) or os.path.exists(os.path.join(path, "final_720p.mp4"))
            
            sessions.append({
                "id": d,
                "has_script": has_script,
                "has_audio": has_audio,
                "has_clips": has_clips
            })
    return jsonify({"sessions": sessions})

@app.route("/api/sessions/<session_id>", methods=["GET"])
def get_session_detail(session_id):
    path = os.path.join(config.OUTPUT_DIR, session_id)
    if not os.path.exists(path):
        return jsonify({"error": "Session not found"}), 404
        
    # 1. Load Script
    script = None
    script_path = os.path.join(path, "scripts", "v1_script.json")
    if os.path.exists(script_path):
        with open(script_path, "r") as f:
            script = json.load(f)
            
    # 2. List Audio
    audio_files = []
    audio_dir = os.path.join(path, "audio")
    if os.path.exists(audio_dir):
        for f in sorted(os.listdir(audio_dir)):
            if f.endswith(".mp3"):
                audio_files.append({
                    "name": f,
                    "stem": os.path.splitext(f)[0],
                    "url": f"/api/files/{session_id}/audio/{f}"
                })
                
    # 3. List Clips/Outputs
    clips = []
    # Check for raw clips
    clips_dir = os.path.join(path, "clips")
    if os.path.exists(clips_dir):
        for f in sorted(os.listdir(clips_dir)):
            if f.endswith(".mp4"):
                clips.append({
                    "name": f"Clip {f}",
                    "url": f"/api/files/{session_id}/clips/{f}"
                })
    # Check for final renders
    for f in ["final_720p.mp4", "final_1080p.mp4", "final_square.mp4"]:
        if os.path.exists(os.path.join(path, f)):
            clips.append({
                "name": f.replace("_", " ").replace(".mp4", "").title(),
                "url": f"/api/files/{session_id}/{f}"
            })

    # 4. List Images
    images = []
    img_dir = os.path.join(path, "images")
    if os.path.exists(img_dir):
        for f in sorted(os.listdir(img_dir)):
            if f.endswith((".png", ".jpg", ".jpeg")):
                images.append({
                    "name": f,
                    "stem": os.path.splitext(f)[0],
                    "url": f"/api/files/{session_id}/images/{f}"
                })

    # 5. Load Manifest (Metadata)
    manifest = None
    manifest_path = os.path.join(path, "final_manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
            
    # 6. Load Log
    log_content = ""
    log_path = os.path.join(path, "pipeline.log")
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            log_content = f.read()
            
    return jsonify({
        "id": session_id,
        "script": script,
        "audio": audio_files,
        "clips": clips,
        "images": images,
        "manifest": manifest,
        "log": log_content
    })

@app.route("/api/sessions/<session_id>/download", methods=["GET"])
def download_session(session_id):
    import shutil
    import tempfile
    
    path = os.path.join(config.OUTPUT_DIR, session_id)
    if not os.path.exists(path):
        return jsonify({"error": "Session not found"}), 404
        
    # Create a temporary zip file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        tmp_path = tmp.name
        
    shutil.make_archive(tmp_path.replace(".zip", ""), 'zip', path)
    
    return send_file(tmp_path, as_attachment=True, download_name=f"uxai_ugc_{session_id}.zip")

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
        import json
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
