"""
QA Reviewer Agent responsible for quality assurance and script refinement.
Evaluates script quality against research and performs technical checks on output.
"""

import os
import json
import subprocess
from typing import Dict, Any, List, Optional
from config import config
from utils.llm_client import LLMClient
from utils.notifier import notifier
from utils.memory_guard import memory_guard
from utils.logger import log

class QAReviewerAgent:
    def __init__(self):
        self.llm = LLMClient()
        self.notifier = notifier
        self.memory_guard = memory_guard
        self.log = log
        self.threshold = config.QA_AUTO_APPROVE_THRESHOLD
        self.max_iterations = config.MAX_QA_ITERATIONS

        # Load prompts
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "qa_prompts.json")
        try:
            with open(prompt_path, "r") as f:
                data = json.load(f)
                self.prompts = {k: v["system"] for k, v in data.get("prompts", {}).items()}
        except Exception as e:
            self.log.error(f"Failed to load QA prompts: {e}")
            self.prompts = {}

    def review_script(self, script: Dict[str, Any], research_data: Dict[str, Any], iteration: int = 1) -> Dict[str, Any]:
        """
        Evaluates script quality using LLM against specific criteria.
        """
        self.log.info(f"Reviewing script (Iteration {iteration})...", context="QAReviewerAgent")
        
        system_prompt_template = self.prompts.get("script_reviewer", "")
        system_prompt = system_prompt_template.format(threshold=self.threshold)
        
        schema = {
            "overall_score": 0.0,
            "criteria": {
                "hook_strength": {"score": 0, "feedback": "str"},
                "pain_relevance": {"score": 0, "feedback": "str"},
                "credibility": {"score": 0, "feedback": "str"},
                "solution_quality": {"score": 0, "feedback": "str"},
                "cta_effectiveness": {"score": 0, "feedback": "str"}
            },
            "must_fix": [{"segment": "str", "issue": "str", "suggested_rewrite": "str"}],
            "nice_to_fix": ["str"],
            "approved": False,
            "iteration": iteration
        }

        user_prompt = f"""
        SCRIPT TO REVIEW:
        {json.dumps(script, indent=2)}

        RESEARCH CONTEXT:
        {json.dumps(research_data, indent=2)}

        THRESHOLD: {self.threshold}

        Evaluate based on the research provided. If overall_score is >= {self.threshold}, set approved to true.
        REQUIRED SCHEMA:
        {json.dumps(schema, indent=2)}
        """

        try:
            review = self.llm.complete_json(system_prompt, user_prompt, model="main")
            
            # Ensure iterations are tracked
            review["iteration"] = iteration
            
            # Logic check for approval
            if review["overall_score"] >= self.threshold:
                review["approved"] = True
            else:
                review["approved"] = False

            self.log.info(f"Script Score: {review['overall_score']}/10 | Approved: {review['approved']}", context="QAReviewerAgent")
            return review
        except Exception as e:
            self.log.error(f"Script review failed: {e}", context="QAReviewerAgent")
            # Return a safe fallback to prevent pipeline crash
            return {
                "overall_score": 0.0,
                "approved": False,
                "must_fix": [],
                "iteration": iteration,
                "error": str(e)
            }

    def review_technical(self, video_path: str) -> Dict[str, Any]:
        """
        Check video file without loading into memory using ffprobe.
        """
        self.log.info(f"Performing technical review for: {os.path.basename(video_path)}", context="QAReviewerAgent")
        
        if not os.path.exists(video_path):
            return {"approved": False, "issues": ["File does not exist"]}

        issues = []
        checks = {}

        try:
            # Run ffprobe
            cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration,size,bit_rate:stream=width,height,codec_name",
                "-of", "json", video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"ffprobe failed: {result.stderr}")

            data = json.loads(result.stdout)
            
            # Extract stats
            format_info = data.get("format", {})
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
            
            duration = float(format_info.get("duration", 0))
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            codec = video_stream.get("codec_name", "unknown")

            checks = {
                "duration": duration,
                "resolution": f"{width}x{height}",
                "file_size_mb": file_size_mb,
                "codec": codec
            }

            # Validations
            if not (38 <= duration <= 45): # Allowing slight buffer over 42s
                issues.append(f"Duration {duration:.1f}s is out of range 38-42s")
            
            if height < 720:
                issues.append(f"Resolution {height}p is below 720p")
            
            if file_size_mb > 80:
                issues.append(f"File size {file_size_mb:.1f}MB exceeds 80MB limit")

            approved = len(issues) == 0
            
            if approved:
                self.log.success("Technical review passed.", context="QAReviewerAgent")
            else:
                self.log.warning(f"Technical review issues: {', '.join(issues)}", context="QAReviewerAgent")

            return {"checks": checks, "approved": approved, "issues": issues}

        except Exception as e:
            self.log.error(f"Technical review failed: {e}", context="QAReviewerAgent")
            return {"approved": False, "issues": [str(e)]}

    def improve_loop(self, script: Dict[str, Any], research_data: Dict[str, Any], 
                     writer_agent, session_id: str) -> Dict[str, Any]:
        """
        Coordinates the review-refine loop between Writer and QA.
        """
        self.log.info("Starting script improvement loop...", context="QAReviewerAgent")
        
        current_script = script
        current_review = {"approved": False, "overall_score": 0.0}
        iterations = 0
        auto_approved = False

        while iterations < self.max_iterations:
            iterations += 1
            
            # 1. Review
            current_review = self.review_script(current_script, research_data, iterations)
            
            # Send notification about progress
            status_msg = "PASSED" if current_review["approved"] else "REJECTED"
            self.notifier.send(
                title=f"QA Review Round {iterations}",
                message=f"Score: {current_review['overall_score']}/10 | Status: {status_msg}",
                priority="high" if current_review["approved"] else "default",
                tags=["mag" if not current_review["approved"] else "white_check_mark"]
            )

            if current_review["approved"]:
                break
                
            # 2. Refine if not approved
            if iterations < self.max_iterations:
                self.log.warning(f"Script rejected. Refinement required (Iteration {iterations}/{self.max_iterations})", context="QAReviewerAgent")
                current_script = writer_agent.refine_script(current_script, current_review, session_id)
            else:
                self.log.warning(f"Max iterations ({self.max_iterations}) reached. Auto-approving imperfect script.", context="QAReviewerAgent")
                auto_approved = True

        return {
            "final_script": current_script,
            "final_review": current_review,
            "iterations_taken": iterations,
            "auto_approved": auto_approved
        }
