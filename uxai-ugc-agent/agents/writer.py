"""
Writer Agent responsible for creating content ideas and scripts.
Transforms research data into engaging short-form video content.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import config
from utils.llm_client import LLMClient
from utils.notifier import notifier
from utils.memory_guard import memory_guard
from utils.logger import log

class WriterAgent:
    def __init__(self):
        self.llm = LLMClient()
        self.notifier = notifier
        self.memory_guard = memory_guard
        self.log = log
        
        # Load prompts
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "writer_prompts.json")
        try:
            with open(prompt_path, "r") as f:
                data = json.load(f)
                self.prompts = {k: v["system"] for k, v in data.get("prompts", {}).items()}
        except Exception as e:
            self.log.error(f"Failed to load writer prompts: {e}")
            self.prompts = {}

    def generate_content_idea(self, research_data: Dict[str, Any], 
                               human_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate 3 content ideas and select the best one.
        """
        if human_override and "selected_idea" in human_override:
            self.log.info("Using human override for content idea.", context="WriterAgent")
            return human_override["selected_idea"]

        self.notifier.step_start("Writer: Generating content ideas")
        self.log.info("Generating content ideas from research...", context="WriterAgent")

        system_prompt = self.prompts.get("idea_generation", "You are a viral B2B video strategist.")
        
        schema = {
            "selected_idea": {
                "title": "str",
                "pain_point": "str",
                "hook_3sec": "str",
                "content_angle": "str",
                "cta": "str",
                "platform_primary": "linkedin|instagram|tiktok",
                "scores": {"pain_relevance": 0, "hook_strength": 0, "originality": 0, "total": 0}
            },
            "all_ideas": [
                {
                    "title": "str",
                    "scores": {"pain_relevance": 0, "hook_strength": 0, "originality": 0, "total": 0}
                }
            ]
        }

        user_prompt = f"""
        RESEARCH DATA:
        {json.dumps(research_data, indent=2)}

        Generate 3 content ideas based on this research. Score them and select the best one.
        
        REQUIRED SCHEMA:
        {json.dumps(schema, indent=2)}
        """

        try:
            result = self.llm.complete_json(system_prompt, user_prompt, model="main")
            self.log.success(f"Generated best idea: {result['selected_idea']['title']}", context="WriterAgent")
            self.notifier.step_done("Writer: Idea Generation", f"Selected: {result['selected_idea']['title']}")
            return result
        except Exception as e:
            self.log.error(f"Idea generation failed: {e}", context="WriterAgent")
            raise

    def write_script(self, idea: Dict[str, Any], session_id: str, human_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Write full video script for a 38-42 second video.
        """
        self.notifier.step_start("Writer: Writing script")
        self.log.info(f"Writing script for idea: {idea.get('title', 'Unknown')}", context="WriterAgent")

        system_prompt = self.prompts.get("script_writer", "You are a specialized B2B script writer.")
        
        schema = {
            "version": 1,
            "metadata": {
                "total_duration": 0,
                "total_words": 0,
                "reading_rate": 2.5
            },
            "segments": [
                {
                    "id": "hook",
                    "text": "str",
                    "duration_seconds": 4,
                    "word_count": 10,
                    "visual_suggestion": "str",
                    "on_screen_text": "str",
                    "emotion_cue": "str"
                }
            ]
        }

        user_prompt = f"""
        CONTENT IDEA:
        {json.dumps(idea, indent=2)}

        Write a script following the SEGMENT TIMING and SCRIPT RULES provided in your system instructions.
        The target duration is 38-42 seconds.
        
        OUTPUT SCHEMA:
        {json.dumps(schema, indent=2)}
        """

        try:
            script = self.llm.complete_json(system_prompt, user_prompt, model="main")
            
            # Apply human override if present
            if human_override and "segment_edits" in human_override:
                self.log.info("Applying segment edits from human override.", context="WriterAgent")
                for edit in human_override["segment_edits"]:
                    for seg in script["segments"]:
                        if seg["id"] == edit["id"]:
                            seg.update(edit)

            # Save version
            scripts_dir = os.path.join(config.OUTPUT_DIR, session_id, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            version = script.get("version", 1)
            script_path = os.path.join(scripts_dir, f"v{version}_script.json")
            
            with open(script_path, "w") as f:
                json.dump(script, f, indent=4)

            self.log.success(f"Script v{version} written and saved.", context="WriterAgent")
            self.notifier.step_done("Writer: Scripting", f"Version {version} finalized.")
            return script
        except Exception as e:
            self.log.error(f"Script writing failed: {e}", context="WriterAgent")
            raise

    def refine_script(self, script: Dict[str, Any], qa_feedback: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """
        Refines specific segments based on QA feedback.
        """
        self.log.info("Refining script based on QA feedback...", context="WriterAgent")
        
        must_fix = qa_feedback.get("must_fix", [])
        if not must_fix:
            return script

        system_prompt = f"""
        You are an expert script editor. You need to rewrite specific segments of a video script based on feedback.
        Original Context: {self.prompts.get('script_writer', '')}
        """

        user_prompt = f"""
        CURRENT SCRIPT:
        {json.dumps(script, indent=2)}

        FEEDBACK TO ADDRESS:
        {json.dumps(must_fix, indent=2)}

        ONLY rewrite the segments specified in the feedback. Keep the other segments exactly as they are.
        Increment the version number.
        Return the full script in JSON format.
        """

        try:
            refined_script = self.llm.complete_json(system_prompt, user_prompt, model="main")
            refined_script["version"] = script.get("version", 1) + 1
            
            # Save refined version
            scripts_dir = os.path.join(config.OUTPUT_DIR, session_id, "scripts")
            script_path = os.path.join(scripts_dir, f"v{refined_script['version']}_script.json")
            with open(script_path, "w") as f:
                json.dump(refined_script, f, indent=4)
                
            self.log.success(f"Script refined to v{refined_script['version']}.", context="WriterAgent")
            return refined_script
        except Exception as e:
            self.log.error(f"Script refinement failed: {e}", context="WriterAgent")
            return script

    def generate_social_metadata(self, script: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate social media captions, hashtags, and metadata.
        """
        self.log.info("Generating social metadata...", context="WriterAgent")
        
        system_prompt = "You are a social media manager for a high-end B2B brand. Generate punchy, professional, and accessible metadata for a video script."
        user_prompt = f"VIDEO SCRIPT:\n{json.dumps(script, indent=2)}\n\nGenerate captions for LinkedIn, IG, and TikTok, plus hashtags and alt-text."
        
        try:
            return self.llm.complete_json(system_prompt, user_prompt, model="fast")
        except Exception as e:
            self.log.error(f"Metadata generation failed: {e}", context="WriterAgent")
            return {}
