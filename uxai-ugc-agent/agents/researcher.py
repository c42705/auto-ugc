"""
Researcher Agent responsible for gathering data and trends.
Research current pain points in UX/AI talent recruitment to validate content ideas.
"""

import os
import json
import praw
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import config
from utils.llm_client import LLMClient
from utils.notifier import notifier
from utils.memory_guard import memory_guard
from utils.logger import log

class ResearcherAgent:
    def __init__(self):
        self.llm = LLMClient()
        self.notifier = notifier
        self.memory_guard = memory_guard
        self.log = log
        
        # Initialize PRAW
        try:
            self.reddit = praw.Reddit(
                client_id=config.REDDIT_CLIENT_ID,
                client_secret=config.REDDIT_CLIENT_SECRET,
                user_agent=config.REDDIT_USER_AGENT,
                read_only=True
            )
        except Exception as e:
            self.log.error(f"Failed to initialize PRAW: {e}")
            self.reddit = None

        # Load prompts
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "researcher_prompts.json")
        try:
            with open(prompt_path, "r") as f:
                data = json.load(f)
                self.prompts = {k: v["system"] for k, v in data.get("prompts", {}).items()}
        except Exception as e:
            self.log.error(f"Failed to load researcher prompts: {e}")
            self.prompts = {}

    def get_trending_pain_points(self, session_id: str) -> Dict[str, Any]:
        """
        Main entry point. Returns validated pain points + content angles.
        """
        self.notifier.step_start("Researcher: Gathering trending pain points")
        self.log.info("Starting research phase...", context="ResearcherAgent")

        # 1. Search Reddit
        reddit_data = self._search_reddit()
        
        # 2. Search Web Trends
        web_data = self._search_web_trends("UX AI recruitment pain points")
        
        # Save raw results
        output_dir = os.path.join(config.OUTPUT_DIR, session_id)
        os.makedirs(output_dir, exist_ok=True)
        raw_output_path = os.path.join(output_dir, "research_raw.json")
        
        raw_data = {
            "reddit": reddit_data,
            "web": web_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        with open(raw_output_path, "w") as f:
            json.dump(raw_data, f, indent=4)
        
        # 3. Synthesize with LLM
        synthesized_data = self._synthesize_with_llm(reddit_data, web_data)
        synthesized_data["validated_at"] = datetime.utcnow().isoformat()
        
        self.log.success(f"Research phase complete. Found {len(synthesized_data.get('pain_points', []))} pain points.", context="ResearcherAgent")
        self.notifier.step_done("Researcher", f"Identified {len(synthesized_data.get('pain_points', []))} core pain points.")
        
        return synthesized_data

    def _search_reddit(self) -> List[Dict[str, Any]]:
        """
        Search relevant subreddits for UX/AI recruitment pain points.
        """
        if not self.reddit:
            self.log.warning("Reddit client not available. Skipping Reddit search.", context="ResearcherAgent")
            return []

        subreddits = ["UXResearch", "userexperience", "recruiting", "artificial", "productdesign", "ExperiencedDevs", "remotework"]
        queries = [
            "UX researcher AI tools 2025",
            "hiring UX designer AI portfolio",
            "recruiter UX research problems",
            "AI designer job interview",
            "UX research team AI workflow"
        ]
        
        results = []
        for sub_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(sub_name)
                for query in queries:
                    # Search within subreddit
                    for submission in subreddit.search(query, limit=5, sort="relevance"):
                        # Get top 3 comments
                        submission.comment_sort = "top"
                        comments = []
                        submission.comments.replace_more(limit=0)
                        for comment in submission.comments[:3]:
                            comments.append(comment.body)
                        
                        results.append({
                            "title": submission.title,
                            "score": submission.score,
                            "num_comments": submission.num_comments,
                            "url": submission.url,
                            "subreddit": sub_name,
                            "top_3_comments_text": "\n---\n".join(comments)
                        })
            except Exception as e:
                self.log.warning(f"Error searching r/{sub_name}: {e}", context="ResearcherAgent")
                
        return results

    def _search_web_trends(self, topic: str) -> Dict[str, Any]:
        """
        Gathers data from DuckDuckGo and Google Trends RSS.
        """
        result = {
            "topic": topic,
            "summary": "",
            "related_topics": [],
            "source_urls": []
        }
        
        # 1. DuckDuckGo Instant Answer
        try:
            ddg_url = f"https://api.duckduckgo.com/?q={topic}&format=json&no_html=1"
            response = requests.get(ddg_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                result["summary"] = data.get("AbstractText", "")
                result["related_topics"] = [t.get("Text", "") for t in data.get("RelatedTopics", []) if isinstance(t, dict)]
        except Exception as e:
            self.log.warning(f"DuckDuckGo search failed: {e}", context="ResearcherAgent")

        # 2. Google Trends RSS
        try:
            trends_url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
            response = requests.get(trends_url, timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for item in root.findall(".//item"):
                    title = item.find("title").text
                    link = item.find("link").text
                    if topic.lower() in title.lower() or "ai" in title.lower():
                        result["source_urls"].append(link)
        except Exception as e:
            self.log.warning(f"Google Trends RSS failed: {e}", context="ResearcherAgent")
            
        return result

    def _synthesize_with_llm(self, reddit_data: List[Dict[str, Any]], web_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize raw research into a structured pain point report.
        """
        system_prompt = self.prompts.get("synthesize", "You are a B2B content strategist.")
        
        schema = {
            "pain_points": [
                {
                    "pain_point": "str",
                    "evidence": [{"source": "reddit|web", "url": "str", "excerpt": "str"}],
                    "content_angle": "str",
                    "urgency_score": "1-10",
                    "suggested_hooks": ["str", "str", "str"]
                }
            ],
            "trending_keywords": ["str"]
        }
        
        user_prompt = f"""
        Analyze the following research data and extract insights.
        
        REDDIT DATA:
        {json.dumps(reddit_data[:15], indent=2)}
        
        WEB DATA:
        {json.dumps(web_data, indent=2)}
        
        OUTPUT SCHEMA:
        {json.dumps(schema, indent=2)}
        """
        
        try:
            return self.llm.complete_json(system_prompt, user_prompt, model="main")
        except Exception as e:
            self.log.error(f"Synthesis failed: {e}", context="ResearcherAgent")
            return {"pain_points": [], "trending_keywords": []}

    def validate_idea(self, script_idea: str) -> Dict[str, Any]:
        """
        Quick validation of a content idea against research.
        """
        self.log.info(f"Validating idea: {script_idea[:50]}...", context="ResearcherAgent")
        
        system_prompt = "You are an expert UX recruitment consultant. Validate if the following content idea is relevant to HR managers hiring AI-fluent designers."
        user_prompt = f"Content Idea: {script_idea}\n\nRespond with JSON: {{'relevance_score': 0-10, 'approved': bool, 'feedback': 'str'}}"
        
        try:
            return self.llm.complete_json(system_prompt, user_prompt, model="fast")
        except Exception as e:
            self.log.error(f"Idea validation failed: {e}", context="ResearcherAgent")
            return {"relevance_score": 0, "approved": False, "feedback": "Validation error."}
