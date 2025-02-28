import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import threading
import json
import hashlib

# Configure logging
logger = logging.getLogger(__name__)

class AlertManager:
    """
    Manages system alerts with rate limiting and multiple delivery methods.
    Currently supports email alerts via Gmail SMTP.
    """
    
    # Alert levels
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    
    # Alert levels to emoji mapping
    LEVEL_EMOJIS = {
        CRITICAL: "🔴",
        ERROR: "🟠",
        WARNING: "🟡",
        INFO: "🔵"
    }
    
    def __init__(self):
        # Load configurations from environment variables
        self.email_enabled = os.environ.get('ENABLE_EMAIL_ALERTS', 'False').lower() == 'true'
        self.email_from = os.environ.get('EMAIL_FROM', '')
        self.email_to = os.environ.get('EMAIL_TO', '')
        self.email_password = os.environ.get('EMAIL_APP_PASSWORD', '')
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        
        # Alert rate limiting
        self.rate_limit_minutes = int(os.environ.get('ALERT_RATE_LIMIT_MINUTES', '15'))
        self.alert_history = {}
        self.history_lock = threading.Lock()
        
        # Initialize alert history file if it doesn't exist
        self.history_file = "alert_history.json"
        if not os.path.exists(self.history_file):
            with open(self.history_file, "w") as f:
                json.dump({}, f)
        else:
            try:
                with open(self.history_file, "r") as f:
                    self.alert_history = json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("Could not read alert history file. Creating new history.")
                self.alert_history = {}
    
    def _save_history(self):
        """Save alert history to file"""
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.alert_history, f)
        except IOError:
            logger.error("Failed to save alert history")
    
    def _get_alert_hash(self, level, title, message):
        """Generate a unique hash for an alert to track rate limiting"""
        hash_content = f"{level}:{title}:{message}"
        return hashlib.md5(hash_content.encode()).hexdigest()
    
    def _is_rate_limited(self, alert_hash):
        """Check if an alert is rate limited"""
        with self.history_lock:
            if alert_hash in self.alert_history:
                last_sent = datetime.fromisoformat(self.alert_history[alert_hash])
                if last_sent + timedelta(minutes=self.rate_limit_minutes) > datetime.now():
                    return True
            return False
    
    def _update_alert_timestamp(self, alert_hash):
        """Update the timestamp of when an alert was last sent"""
        with self.history_lock:
            self.alert_history[alert_hash] = datetime.now().isoformat()
            self._save_history()
    
    def send_email_alert(self, level, title, message, include_timestamp=True):
        """Send an alert via email"""
        if not self.email_enabled or not self.email_from or not self.email_to or not self.email_password:
            logger.warning("Email alerts are not configured properly")
            return False
        
        try:
            # Create email
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = self.email_to
            
            # Add timestamp if requested
            if include_timestamp:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                title = f"{title} - {timestamp}"
            
            emoji = self.LEVEL_EMOJIS.get(level, "")
            msg['Subject'] = f"{emoji} AmpyThropic Alert: {title}"
            
            # Format message with level and styling
            formatted_message = f"""
            <html>
            <body>
                <h2 style='color: {self._get_color_for_level(level)};'>{emoji} {level}: {title}</h2>
                <hr>
                <pre style='font-family: monospace; white-space: pre-wrap;'>{message}</pre>
                <hr>
                <p><i>AmpyThropic Trading System<br>
                Alert sent: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</i></p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(formatted_message, 'html'))
            
            # Connect to SMTP server and send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_from, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email alert sent: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {str(e)}")
            return False
    
    def _get_color_for_level(self, level):
        """Get HTML color code for alert level"""
        colors = {
            self.CRITICAL: "#FF0000",  # Red
            self.ERROR: "#FF7700",     # Orange
            self.WARNING: "#FFCC00",   # Yellow
            self.INFO: "#0077FF"       # Blue
        }
        return colors.get(level, "#000000")  # Default to black
    
    def send_alert(self, level, title, message, bypass_rate_limit=False):
        """
        Send an alert through all configured channels with rate limiting
        
        Args:
            level (str): Alert level (CRITICAL, ERROR, WARNING, INFO)
            title (str): Alert title/summary
            message (str): Detailed alert message
            bypass_rate_limit (bool): If True, send even if rate limited
        
        Returns:
            bool: True if alert was sent through at least one channel
        """
        # Validate level
        if level not in [self.CRITICAL, self.ERROR, self.WARNING, self.INFO]:
            level = self.ERROR  # Default to ERROR if invalid
        
        # Check rate limiting
        alert_hash = self._get_alert_hash(level, title, message)
        if not bypass_rate_limit and self._is_rate_limited(alert_hash):
            logger.debug(f"Alert '{title}' suppressed due to rate limiting")
            return False
        
        # Update timestamp regardless of send success
        self._update_alert_timestamp(alert_hash)
        
        # Send through email
        email_sent = False
        if self.email_enabled:
            email_sent = self.send_email_alert(level, title, message)
        
        # Log the alert regardless of delivery method success
        log_message = f"{level}: {title} - {message}"
        if level == self.CRITICAL:
            logger.critical(log_message)
        elif level == self.ERROR:
            logger.error(log_message)
        elif level == self.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        return email_sent

# Create a global instance of the alert manager
alert_manager = AlertManager()

# Convenience functions for sending alerts
def send_critical_alert(title, message, bypass_rate_limit=False):
    """Send a critical alert"""
    return alert_manager.send_alert(AlertManager.CRITICAL, title, message, bypass_rate_limit)

def send_error_alert(title, message, bypass_rate_limit=False):
    """Send an error alert"""
    return alert_manager.send_alert(AlertManager.ERROR, title, message, bypass_rate_limit)

def send_warning_alert(title, message, bypass_rate_limit=False):
    """Send a warning alert"""
    return alert_manager.send_alert(AlertManager.WARNING, title, message, bypass_rate_limit)

def send_info_alert(title, message, bypass_rate_limit=False):
    """Send an informational alert"""
    return alert_manager.send_alert(AlertManager.INFO, title, message, bypass_rate_limit)