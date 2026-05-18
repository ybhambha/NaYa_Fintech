"""
semisector/scheduler.py
────────────────────────
Scheduler — sets up a Windows Task Scheduler task to run the
daily email report automatically at 4:30 PM on trading days
(Monday–Friday).

Usage
─────
    # Set up the scheduled task (run once as Administrator)
    python main.py --setup-schedule --email you@outlook.com

    # Remove the scheduled task
    python main.py --remove-schedule

How it works
────────────
Uses the Windows 'schtasks' command-line tool to create a task that:
  - Runs Monday–Friday at 4:30 PM
  - Calls: python main.py --email <addr> --no-options --summary-only
  - Logs output to logs/scheduler.log
  - Skips weekends automatically (schtasks MON-FRI schedule)
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib  import Path


TASK_NAME = "NaYaFintech_SemiSector_DailyReport"


class Scheduler:
    """
    Creates and manages a Windows Scheduled Task for the daily email report.
    """

    def __init__(self, project_root: Path, email_to: str) -> None:
        self.project_root = project_root
        self.email_to     = email_to
        self.python_exe   = sys.executable
        self.main_script  = str(project_root / "main.py")
        self.log_dir      = project_root / "logs"
        self.log_file     = self.log_dir / "scheduler.log"

    # ── Public API ────────────────────────────────────────────────────────────

    def setup(self, run_time: str = "16:30") -> bool:
        """
        Create the Windows Scheduled Task.
        run_time format: "HH:MM" (24-hour)
        """
        self.log_dir.mkdir(exist_ok=True)

        cmd = self._build_command(run_time)
        print(f"  Creating Windows Scheduled Task: {TASK_NAME}")
        print(f"  Schedule: Mon–Fri at {run_time}")
        print(f"  Email to: {self.email_to}")
        print(f"  Log file: {self.log_file}")
        print()

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✅ Scheduled task created successfully.")
            print(f"     To view it: open Task Scheduler → "
                  f"Task Scheduler Library → {TASK_NAME}")
            self._write_env_reminder()
            return True
        else:
            print(f"  ❌ Failed to create scheduled task.")
            print(f"     Error: {result.stderr.strip()}")
            print()
            print("  Try running Anaconda Prompt as Administrator:")
            print("  Right-click Anaconda Prompt → Run as administrator")
            return False

    def remove(self) -> bool:
        """Delete the Windows Scheduled Task."""
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  ✅ Scheduled task '{TASK_NAME}' removed.")
            return True
        else:
            print(f"  ⚠  Could not remove task: {result.stderr.strip()}")
            return False

    def status(self) -> None:
        """Show the status of the scheduled task."""
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"  Task '{TASK_NAME}' not found or not accessible.")

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_command(self, run_time: str) -> list[str]:
        """Build the schtasks command."""
        # The action: python main.py --email addr --no-options
        action = (
            f'"{self.python_exe}" "{self.main_script}" '
            f'--email "{self.email_to}" '
            f'--no-options --summary-only '
            f'>> "{self.log_file}" 2>&1'
        )

        return [
            "schtasks", "/create",
            "/tn",  TASK_NAME,
            "/tr",  action,
            "/sc",  "WEEKLY",
            "/d",   "MON,TUE,WED,THU,FRI",
            "/st",  run_time,
            "/rl",  "HIGHEST",
            "/f",                    # overwrite if exists
        ]

    def _write_env_reminder(self) -> None:
        """Print a reminder about environment variables."""
        env_file = self.project_root / ".env"
        print()
        print("  ─── IMPORTANT: Email credentials ────────────────────────────")
        print(f"  Create a file at: {env_file}")
        print("  With these contents (replace with your real values):")
        print()
        print("    SEMISECTOR_EMAIL_FROM=your.email@outlook.com")
        print(f"    SEMISECTOR_EMAIL_TO={self.email_to}")
        print("    SEMISECTOR_EMAIL_PASSWORD=your_outlook_password")
        print()
        print("  ⚠  NEVER commit the .env file to GitHub.")
        print("     It is already in .gitignore.")
        print("  ─────────────────────────────────────────────────────────────")


def load_env_file(project_root: Path) -> None:
    """
    Load .env file into environment variables if it exists.
    Simple implementation — no external dependency needed.
    """
    env_file = project_root / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
