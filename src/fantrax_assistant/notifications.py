"""Multi-Channel Emergency Notification Manager for Fantrax Assistant.

Delivers real-time lineup alerts via Slack, Discord, SMS (Twilio), Ntfy Mobile Push, and macOS Native System Alerts.
"""

import os
import json
import urllib.request
import subprocess
from typing import Dict, Any, List

from pathlib import Path

class NotificationManager:
    """Router for sending lineup scratch alerts to mobile devices, messaging apps, and system popups."""

    def __init__(self):
        settings = {}
        settings_file = Path(__file__).resolve().parent.parent.parent / "data" / "settings.json"
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
            except Exception:
                pass

        self.slack_url = settings.get("slack_webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")
        self.ntfy_topic = settings.get("ntfy_topic") or os.getenv("NTFY_TOPIC", "")
        self.macos_enabled = settings.get("macos_alerts_enabled", True)
        self.fantrax_league_id = settings.get("fantrax_league_id") or os.getenv("FANTRAX_LEAGUE_ID", "")
        self.fantrax_team_name = settings.get("fantrax_team_name") or os.getenv("FANTRAX_TEAM_NAME", "")
        self.auto_sync_enabled = settings.get("auto_sync_enabled", True)
        self.gameweek_reminder_enabled = settings.get("gameweek_reminder_enabled", True)
        
        # Twilio SMS Config
        self.twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from = os.getenv("TWILIO_FROM_NUMBER", "")
        self.twilio_to = os.getenv("TWILIO_TO_NUMBER", "")

    def send_lineup_alert(self, alert: Dict[str, Any]) -> List[str]:
        """Send a single lineup alert across all configured notification channels."""
        sent_channels = []
        alert_text = alert.get("alert_text", "Lineup Alert")
        severity = alert.get("severity", "WARNING")
        starter = alert.get("starter", "Player")
        rec_sub = alert.get("recommended_sub", "Sub")
        kickoff = alert.get("kickoff_time", "Kickoff")
        mins = alert.get("minutes_until_kickoff", 0)

        # 1. Slack Webhook Notification
        if self.slack_url:
            if self._send_slack(severity, starter, rec_sub, kickoff, mins, alert_text):
                sent_channels.append("Slack")

        # 2. Ntfy.sh Free Mobile Push Notification
        if self.ntfy_topic:
            if self._send_ntfy(severity, alert_text):
                sent_channels.append("Ntfy Mobile Push")

        # 4. Twilio SMS Notification
        if self.twilio_sid and self.twilio_token and self.twilio_to and self.twilio_from:
            if self._send_twilio(alert_text):
                sent_channels.append("SMS (Twilio)")

        # 5. macOS Native System Alert Popup
        if self.macos_enabled:
            if self._send_macos_notification(severity, alert_text):
                sent_channels.append("macOS Native Notification")

        return sent_channels

    def send_gameweek_reminder(self, reminder: Dict[str, Any]) -> List[str]:
        """Send a 24h pre-gameweek lineup health reminder (unset lineup, benched starters)."""
        sent_channels = []
        title = reminder.get("title", "Gameweek Lineup Notice")
        message = reminder.get("message", "Please check your Fantrax lineup before kickoff.")
        severity = reminder.get("severity", "WARNING")

        # 1. Slack
        if self.slack_url:
            try:
                payload = {
                    "text": f"*{title}*\n{message}",
                    "attachments": [{
                        "color": "#ef4444" if "CRITICAL" in severity else "#f59e0b",
                        "fields": [
                            {"title": "Team", "value": reminder.get("team_name", "My Team"), "short": True},
                            {"title": "First Kickoff", "value": reminder.get("first_kickoff", "Tomorrow"), "short": True}
                        ]
                    }]
                }
                req = urllib.request.Request(
                    self.slack_url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(req, timeout=5):
                    sent_channels.append("Slack")
            except Exception as e:
                print(f"Error sending Slack reminder: {e}")

        # 2. macOS
        if self.macos_enabled:
            if self._send_macos_notification(title, message):
                sent_channels.append("macOS Native Notification")

        # 3. Ntfy
        if self.ntfy_topic:
            if self._send_ntfy(title, message):
                sent_channels.append("Ntfy Mobile Push")

        return sent_channels

    def _send_slack(self, severity: str, starter: str, sub: str, kickoff: str, mins: float, text: str) -> bool:
        try:
            payload = {
                "text": f"*{severity}*\n*{starter}* is NOT starting for {kickoff} ({int(mins)} mins to kickoff)!\n*Recommended Swap*: `{sub}`",
                "attachments": [{
                    "color": "#ef4444" if "CRITICAL" in severity else "#f59e0b",
                    "fields": [
                        {"title": "Benched Starter", "value": starter, "short": True},
                        {"title": "Recommended Sub", "value": sub, "short": True},
                        {"title": "Match Kickoff", "value": kickoff, "short": True},
                        {"title": "Time Remaining", "value": f"{int(mins)} mins", "short": True}
                    ]
                }]
            }
            req = urllib.request.Request(
                self.slack_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception as e:
            print(f"Error sending Slack notification: {e}")
            return False

    def _send_ntfy(self, severity: str, text: str) -> bool:
        try:
            url = f"https://ntfy.sh/{self.ntfy_topic}"
            req = urllib.request.Request(
                url,
                data=text.encode('utf-8'),
                headers={
                    'Title': f"Fantrax Assistant: {severity}",
                    'Priority': 'high' if 'CRITICAL' in severity else 'default',
                    'Tags': 'warning,soccer'
                }
            )
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception as e:
            print(f"Error sending ntfy notification: {e}")
            return False

    def _send_twilio(self, text: str) -> bool:
        try:
            import base64
            auth_str = f"{self.twilio_sid}:{self.twilio_token}"
            b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
            
            data = urllib.parse.urlencode({
                'From': self.twilio_from,
                'To': self.twilio_to,
                'Body': text
            }).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    'Authorization': f"Basic {b64_auth}",
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception as e:
            print(f"Error sending Twilio SMS: {e}")
            return False

    def _send_macos_notification(self, severity: str, text: str) -> bool:
        try:
            clean_text = text.replace('"', '\\"').replace("'", "\\'")
            script = f'display notification "{clean_text}" with title "Fantrax Assistant Alert" subtitle "{severity}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False
