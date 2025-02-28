import os
import smtplib
import logging
import stat
import pathlib
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
import threading
import json
import hashlib

# Configure logging
logger = logging.getLogger(__name__)

class AlertManager:
    """
    Manages system alerts with rate limiting and multiple delivery methods.
    Currently supports email alerts via Gmail SMTP.
    
    Thread-safety: This class is designed to be thread-safe. All operations on shared resources
    (like alert_history) are protected by locks. A single global instance of this class is 
    created at the module level and should be used throughout the application.
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
    
    # Maximum age of alert entries in days
    MAX_HISTORY_AGE_DAYS = 7
    
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
        
        # Create data directory with secure permissions if it doesn't exist
        self.data_dir = pathlib.Path("data")
        if not self.data_dir.exists():
            try:
                self.data_dir.mkdir(mode=0o700, exist_ok=True)  # Owner read/write/execute only
                logger.info(f"Created secure data directory at {self.data_dir}")
            except Exception as e:
                logger.warning(f"Could not create secure data directory: {e}. Using current directory.")
                self.data_dir = pathlib.Path(".")
                
        # Initialize alert history file if it doesn't exist
        self.history_file = self.data_dir / "alert_history.json"
        
        if not self.history_file.exists():
            try:
                with open(self.history_file, "w") as f:
                    json.dump({}, f)
                # Set permissions to user read/write only
                os.chmod(self.history_file, stat.S_IRUSR | stat.S_IWUSR)
                logger.info(f"Created secure alert history file at {self.history_file}")
            except (IOError, PermissionError) as e:
                logger.warning(f"Could not create alert history file: {e}. Alerts will not persist between restarts.")
                self.history_file = None
        else:
            try:
                with open(self.history_file, "r") as f:
                    self.alert_history = json.load(f)
                # Clean up old entries on initialization
                self._clean_old_entries()
            except (json.JSONDecodeError, IOError, PermissionError) as e:
                logger.warning(f"Could not read alert history file: {e}. Creating new history.")
                self.alert_history = {}
    
    def _save_history(self):
        """Save alert history to file"""
        if not self.history_file:
            return
            
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.alert_history, f)
            # Ensure permissions remain secure
            os.chmod(self.history_file, stat.S_IRUSR | stat.S_IWUSR)
        except (IOError, PermissionError) as e:
            logger.error(f"Failed to save alert history: {e}")
    
    def _clean_old_entries(self):
        """Remove old alert entries to prevent unlimited growth"""
        if not self.alert_history:
            return
            
        now = datetime.now(timezone.utc)
        max_age = timedelta(days=self.MAX_HISTORY_AGE_DAYS)
        expired_keys = []
        
        with self.history_lock:
            for alert_hash, timestamp_str in self.alert_history.items():
                try:
                    # Handle both timezone-aware and naive datetimes
                    if timestamp_str.endswith('Z'):
                        # ISO format with Z suffix (UTC)
                        timestamp_str = timestamp_str[:-1] + '+00:00'
                        
                    if '+' in timestamp_str or 'Z' in timestamp_str:
                        # Timezone aware
                        last_sent = datetime.fromisoformat(timestamp_str)
                    else:
                        # Naive datetime - assume UTC
                        last_sent = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
                        
                    if now - last_sent > max_age:
                        expired_keys.append(alert_hash)
                except (ValueError, TypeError):
                    # If timestamp format is invalid, mark for cleanup
                    expired_keys.append(alert_hash)
            
            # Remove expired entries
            for key in expired_keys:
                del self.alert_history[key]
                
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} old alert history entries")
                self._save_history()
    
    def _get_alert_hash(self, level, title, message):
        """Generate a unique hash for an alert to track rate limiting"""
        hash_content = f"{level}:{title}:{message}"
        return hashlib.md5(hash_content.encode()).hexdigest()
    
    def _is_rate_limited(self, alert_hash):
        """Check if an alert is rate limited"""
        with self.history_lock:
            if alert_hash in self.alert_history:
                try:
                    # Use timezone-aware comparisons
                    now = datetime.now(timezone.utc)
                    timestamp_str = self.alert_history[alert_hash]
                    
                    # Handle both timezone-aware and naive timestamps
                    if '+' in timestamp_str:
                        last_sent = datetime.fromisoformat(timestamp_str)
                    else:
                        # If no timezone info, assume UTC
                        last_sent = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
                        
                    if last_sent + timedelta(minutes=self.rate_limit_minutes) > now:
                        return True
                except (ValueError, TypeError) as e:
                    # In case of invalid timestamp, don't rate limit
                    logger.warning(f"Invalid timestamp format in alert history: {e}")
                    return False
            return False
    
    def _update_alert_timestamp(self, alert_hash):
        """Update the timestamp of when an alert was last sent"""
        with self.history_lock:
            # Store timezone-aware timestamps in ISO format
            self.alert_history[alert_hash] = datetime.now(timezone.utc).isoformat()
            self._save_history()
            
            # Clean old entries periodically (1% chance on each alert)
            if random.random() < 0.01:
                self._clean_old_entries()
    
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
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                title = f"{title} - {timestamp}"
            
            emoji = self.LEVEL_EMOJIS.get(level, "")
            msg['Subject'] = f"{emoji} AmpyThropic Alert: {title}"
            
            # Sanitize message for HTML - basic protection against HTML injection
            # Replace < and > with their HTML entities
            safe_message = message.replace("<", "&lt;").replace(">", "&gt;")
            
            # Format message with level and styling
            formatted_message = f"""
            <html>
            <body>
                <h2 style='color: {self._get_color_for_level(level)};'>{emoji} {level}: {title}</h2>
                <hr>
                <pre style='font-family: monospace; white-space: pre-wrap;'>{safe_message}</pre>
                <hr>
                <p><i>AmpyThropic Trading System<br>
                Alert sent: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</i></p>
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
# This is a singleton that should be used throughout the application.
# It is thread-safe and manages all alert operations.
alert_manager = AlertManager()

# Convenience functions for sending alerts
def send_critical_alert(title, message, bypass_rate_limit=False):
    """
    Send a critical alert - for immediate attention required situations
    
    Args:
        title (str): Alert title/summary
        message (str): Detailed alert message
        bypass_rate_limit (bool): If True, ignore rate limiting
        
    Returns:
        bool: True if alert was sent
    """
    return alert_manager.send_alert(AlertManager.CRITICAL, title, message, bypass_rate_limit)

def send_error_alert(title, message, bypass_rate_limit=False):
    """
    Send an error alert - for serious issues that need attention
    
    Args:
        title (str): Alert title/summary
        message (str): Detailed alert message
        bypass_rate_limit (bool): If True, ignore rate limiting
        
    Returns:
        bool: True if alert was sent
    """
    return alert_manager.send_alert(AlertManager.ERROR, title, message, bypass_rate_limit)

def send_warning_alert(title, message, bypass_rate_limit=False):
    """
    Send a warning alert - for potential issues that might need attention
    
    Args:
        title (str): Alert title/summary
        message (str): Detailed alert message
        bypass_rate_limit (bool): If True, ignore rate limiting
        
    Returns:
        bool: True if alert was sent
    """
    return alert_manager.send_alert(AlertManager.WARNING, title, message, bypass_rate_limit)

def send_info_alert(title, message, bypass_rate_limit=False):
    """
    Send an informational alert - for notable events that aren't problems
    
    Args:
        title (str): Alert title/summary
        message (str): Detailed alert message
        bypass_rate_limit (bool): If True, ignore rate limiting
        
    Returns:
        bool: True if alert was sent
    """
    return alert_manager.send_alert(AlertManager.INFO, title, message, bypass_rate_limit)