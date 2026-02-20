import requests
from config import config
from typing import Optional, List
from utils.logger import log

class Notifier:
    def __init__(self):
        self.url = config.NTFY_URL

    def send(self, title: str, message: str, priority: str = "default", 
             tags: Optional[List[str]] = None) -> bool:
        """
        Sends a notification to the configured ntfy topic.
        Priority options: "min", "low", "default", "high", "urgent"
        """
        if not self.url:
            log.warning("NTFY_URL not configured. Skipping notification.")
            return False

        headers = {
            "Title": title,
            "Priority": priority
        }
        if tags:
            headers["Tags"] = ",".join(tags)

        try:
            response = requests.post(self.url, data=message, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception as e:
            log.error(f"Failed to send ntfy notification: {e}")
            return False

    def step_start(self, step_name: str):
        self.send(
            title="Step Started",
            message=f"Pipeline step: {step_name} has started.",
            tags=["arrow_forward"]
        )

    def step_done(self, step_name: str, detail: str = ""):
        message = f"Pipeline step: {step_name} completed successfully."
        if detail:
            message += f"\n\nDetails: {detail}"
        self.send(
            title="Step Completed",
            message=message,
            tags=["white_check_mark"]
        )

    def step_error(self, step_name: str, error: str):
        self.send(
            title="Step Error",
            message=f"Pipeline step: {step_name} failed!\nError: {error}",
            priority="high",
            tags=["warning", "x"]
        )

    def pipeline_complete(self, output_path: str):
        self.send(
            title="Pipeline Complete ✅",
            message=f"UGC content generated successfully!\nPath: {output_path}",
            priority="high",
            tags=["tada", "movie_camera"]
        )

    def review_window_open(self, step: str, timeout: int):
        self.send(
            title="Manual Review Required",
            message=f"Waiting for human approval on: {step}\nTimeout: {timeout}s",
            priority="urgent",
            tags=["eyes", "stopwatch"]
        )

# Global instances for utilities
notifier = Notifier()
