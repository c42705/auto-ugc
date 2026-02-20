import logging
import sys
import os
from datetime import datetime
from typing import Optional

# ANSI Color Codes
RESET = "\033[0m"
WHITE = "\033[37m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BOLD = "\033[1m"

class Logger:
    def __init__(self):
        self.session_id = None
        self.log_file = None
        
    def set_session(self, session_id: str, output_dir: str):
        """Sets the session ID and creates the log file path."""
        self.session_id = session_id
        session_path = os.path.join(output_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        self.log_file = os.path.join(session_path, "pipeline.log")

    def _format_msg(self, level: str, message: str, color: str, context: str = "") -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ctx_part = f"[{context}] " if context else ""
        formatted = f"{color}[{timestamp}] [{level}] {ctx_part}{message}{RESET}"
        
        # Write to file without colors if log_file is set
        if self.log_file:
            plain_msg = f"[{timestamp}] [{level}] {ctx_part}{message}\n"
            try:
                with open(self.log_file, "a") as f:
                    f.write(plain_msg)
            except Exception as e:
                print(f"Error writing to log file: {e}")
                
        return formatted

    def info(self, message: str, context: str = ""):
        print(self._format_msg("INFO", message, WHITE, context))

    def success(self, message: str, context: str = ""):
        print(self._format_msg("SUCCESS", message, GREEN + BOLD, context))

    def warning(self, message: str, context: str = ""):
        print(self._format_msg("WARNING", message, YELLOW, context))

    def error(self, message: str, context: str = ""):
        print(self._format_msg("ERROR", message, RED + BOLD, context), file=sys.stderr)

    def agent(self, agent_name: str, message: str):
        print(self._format_msg("AGENT", message, CYAN, context=agent_name))

# Global logger instance
log = Logger()

# For backward compatibility with the previous setup_logger
def setup_logger(name: str, log_file: Optional[str] = None):
    return log
