"""
Orchestrator Agent responsible for managing the entire pipeline workflow.
Coordinates between Researcher, Writer, MediaGenerator, and QA Reviewer.
Handles human review windows, state persistence, and real-time updates via SocketIO.
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from agents.researcher import ResearcherAgent
from agents.writer import WriterAgent
from agents.media_generator import MediaGeneratorAgent
from agents.qa_reviewer import QAReviewerAgent
from config import config
from utils.notifier import notifier
from utils.memory_guard import memory_guard
from utils.logger import log

class Orchestrator:
    def __init__(self, socketio=None):
        self.log = log
        self.notifier = notifier
        self.memory_guard = memory_guard
        self.socketio = socketio
        
        # Initialize Agents
        self.researcher = ResearcherAgent()
        self.writer = WriterAgent()
        self.media_gen = MediaGeneratorAgent()
        self.qa_reviewer = QAReviewerAgent()
        
        # Pipeline State
        self.session_id = None
        self.session_path = None
        self.current_step = None
        self.status = "idle"  # idle, running, paused, completed, failed
        self.start_time = None
        self.overrides = {}
        self.results = {}
        self.pending_review = None
        self.review_event = threading.Event()
        
        self.steps_list = [
            "research", "review_research", "ideation", "scripting", 
            "review_script", "qa_loop", "review_qa", "voiceover", 
            "avatar_clips", "images", "assembly", "qa_video", 
            "metadata", "finalize"
        ]

    def _create_session(self) -> str:
        """Create /output/YYYY-MM-DD-HHMMSS/ folder and return session_id"""
        session_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        session_path = os.path.join(config.OUTPUT_DIR, session_id)
        os.makedirs(session_path, exist_ok=True)
        
        self.session_id = session_id
        self.session_path = session_path
        self.log.set_session(session_id, config.OUTPUT_DIR)
        return session_id

    def _execute_step(self, step_name: str, func: Callable, *args, **kwargs):
        """Wrapper for all step executions with logging and status updates."""
        self.current_step = step_name
        self.log.info(f">>> Executing step: {step_name}", context="Orchestrator")
        
        self._emit("step_start", {"step": step_name, "session_id": self.session_id})
        
        # Memory Check
        mem_status = self.memory_guard.check(context=step_name)
        self.log.info(f"Memory Status: {mem_status['available_mb']:.1f}MB available ({mem_status['percent_used']}%)", context="Orchestrator")

        try:
            result = func(*args, **kwargs)
            self.results[step_name] = result
            self._emit("step_complete", {"step": step_name, "result_summary": str(result)[:200]})
            return result
        except Exception as e:
            self.status = "failed"
            self.log.error(f"Step {step_name} failed: {e}", context="Orchestrator")
            self._emit("step_error", {"step": step_name, "error": str(e)})
            self.notifier.step_error(step_name, str(e))
            raise

    def _human_review_window(self, step: str, data: Any) -> Any:
        """Opens a review window and blocks for human input or timeout."""
        timeout = config.HUMAN_REVIEW_TIMEOUT_SECONDS
        self.log.warning(f"WAITING FOR HUMAN REVIEW: {step} (Timeout: {timeout}s)", context="Orchestrator")
        
        self.pending_review = {
            "step": step,
            "data": data,
            "timeout_at": time.time() + timeout
        }
        
        self._emit("review_window_open", {
            "step": step,
            "data": data,
            "timeout": timeout
        })
        
        self.notifier.review_window_open(step, timeout)
        
        # Reset and wait for the override event
        self.review_event.clear()
        event_is_set = self.review_event.wait(timeout=timeout)
        
        if event_is_set:
            override = self.overrides.get(step)
            self.log.success(f"Human review received for {step}", context="Orchestrator")
            self.pending_review = None
            # Return merged data or override data
            return override if override else data
        else:
            self.log.info(f"Review window timeout for {step}. Auto-continuing with original data.", context="Orchestrator")
            self._emit("review_window_timeout", {"step": step})
            self.pending_review = None
            return data

    def submit_human_override(self, step: str, override_data: Dict[str, Any]):
        """Called externally (e.g., via API) to provide human feedback."""
        self.overrides[step] = override_data
        self._emit("override_received", {"step": step})
        self.review_event.set()

    def run_pipeline(self, topic_override: str = None) -> Dict[str, Any]:
        """Main execution logic for the 14-step UGC pipeline."""
        self._create_session()
        self.start_time = time.time()
        self.status = "running"
        self.log.info(f"Pipeline started. Session: {self.session_id}", context="Orchestrator")
        
        try:
            # 1. Research
            research = self._execute_step("research", self.researcher.get_trending_pain_points, self.session_id)
            
            # 2. Review Research
            research = self._human_review_window("review_research", research)
            
            # 3. Ideation
            ideation = self._execute_step("ideation", self.writer.generate_content_idea, research)
            
            # 4. Scripting
            script = self._execute_step("scripting", self.writer.write_script, ideation["selected_idea"], self.session_id)
            
            # 5. Review Script
            script = self._human_review_window("review_script", script)
            
            # 6. QA Loop (Self-Correction)
            qa_res = self._execute_step("qa_loop", self.qa_reviewer.improve_loop, script, research, self.writer, self.session_id)
            final_script = qa_res["final_script"]
            
            # 7. Review QA (Final script approval)
            final_script = self._human_review_window("review_qa", {
                "script": final_script, 
                "qa_score": qa_res["final_review"].get("overall_score"),
                "auto_approved": qa_res["auto_approved"]
            })
            if isinstance(final_script, dict) and "script" in final_script:
                final_script = final_script["script"] # Extract from wrapper if replaced

            # 8. Voiceover
            audio_paths = self._execute_step("voiceover", self.media_gen.generate_voiceover, final_script["segments"], self.session_path)
            
            # 9. Avatar Clips
            clip_paths = self._execute_step("avatar_clips", self.media_gen.generate_avatar_clips, final_script["segments"], audio_paths, self.session_path)
            
            # 10. Background Images
            image_paths = self._execute_step("images", self.media_gen.generate_background_images, final_script["segments"], self.session_path)
            
            # 11. Assembly
            video_manifest = self._execute_step("assembly", self.media_gen.assemble_final_video, clip_paths, image_paths, final_script, self.session_path)
            
            # 12. QA Video (Technical check)
            tech_qa = self._execute_step("qa_video", self.qa_reviewer.review_technical, video_manifest["vertical_720p"])
            
            # 13. Metadata
            social_data = self._execute_step("metadata", self.writer.generate_social_metadata, final_script)
            
            # 14. Finalize
            manifest_path = self._write_manifest()
            self.status = "completed"
            self.log.success(f"Pipeline completed successfully! Manifest: {manifest_path}", context="Orchestrator")
            self.notifier.pipeline_complete(video_manifest["vertical_720p"])
            
            return self.results["finalize"] # Set by _write_manifest logic in results map

        except Exception as e:
            self.status = "failed"
            self.log.error(f"Pipeline crashed: {e}", context="Orchestrator")
            raise

    def get_status(self) -> Dict[str, Any]:
        """Returns the current status and progress of the pipeline."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        current_idx = self.steps_list.index(self.current_step) if self.current_step in self.steps_list else 0
        progress = (current_idx / len(self.steps_list)) * 100
        
        timeout_rem = None
        if self.pending_review:
            timeout_rem = max(0, self.pending_review["timeout_at"] - time.time())

        return {
            "session_id": self.session_id,
            "status": self.status,
            "current_step": self.current_step,
            "current_step_index": current_idx,
            "total_steps": len(self.steps_list),
            "progress_percent": round(progress, 2),
            "start_time": self.start_time,
            "elapsed_seconds": round(elapsed, 1),
            "pending_review": {
                "step": self.pending_review["step"],
                "timeout_remaining": round(timeout_rem, 1)
            } if self.pending_review else None,
            "output_path": self.session_path
        }

    def _write_manifest(self) -> str:
        """Finalizes the run by writing a complete summary manifest."""
        data = {
            "session_id": self.session_id,
            "created_at": datetime.now().isoformat(),
            "pipeline_duration_seconds": round(time.time() - self.start_time, 2),
            "research_summary": self.results.get("research", {}).get("pain_points", []),
            "script": self.results.get("qa_loop", {}).get("final_script"),
            "qa_scores": self.results.get("qa_loop", {}).get("final_review"),
            "media_files": self.results.get("assembly", {}), # Contains paths to 720p, 1080p, square
            "social_metadata": self.results.get("metadata", {}),
            "iterations_taken": self.results.get("qa_loop", {}).get("iterations_taken", 0)
        }
        
        manifest_path = os.path.join(self.session_path, "final_manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(data, f, indent=4)
            
        self.results["finalize"] = data
        return manifest_path

    def _emit(self, event: str, data: Dict[str, Any]):
        """Helper to emit SocketIO events if available."""
        if self.socketio:
            self.socketio.emit(event, data)
