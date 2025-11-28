import os
import platform
import time
from collections import deque
import requests
import subprocess
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logging.handlers import RotatingFileHandler

# General logging: all checks
def setup_logger(name, log_file, level=logging.INFO):
    handler = logging.FileHandler(log_file, encoding='utf-8')  # <-- Add encoding here
    formatter = logging.Formatter('%(asctime)s — %(levelname)s — %(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        logger.addHandler(handler)

    # Set up console output to handle Unicode
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    return logger

log_dir = os.path.abspath("") # A dd your path for store log files

log_all_path = os.path.join(log_dir, "camera_health_log.txt")
log_fail_path = os.path.join(log_dir, "camera_failure_log.txt")


# Set up two loggers
logger_all = setup_logger("all_logs", log_all_path, level=logging.INFO)
logger_fail = setup_logger("fail_logs", log_fail_path, level=logging.WARNING)



# Email notification setup
def send_email_notification(subject, body):
    sender_email = "" #You must add your mail
    receiver_email = "swastikasharmaindia@gmail.com" #Add the mail 
    password = ""  # Use App Password if using Gmail

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)  # Use the SMTP server of your email provider
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error: {e}")

# Ping the camera IP and check if it's reachable
def ping_camera(ip):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = f"ping {param} 1 {ip}"
    response = os.system(command)
    return response == 0

# Try to fetch a snapshot from the IP camera to confirm video feed is active
def check_camera_feed(ip):
    try:
        url = f"http://{ip}:8080/shot.jpg"
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

# Measure latency from ping output (Windows-specific)
def get_ping_latency(ip):
    try:
        result = subprocess.run(["ping", "-n", "1", ip], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        for line in lines:
            if "Average" in line:
                parts = line.split("=")
                latency = int(parts[-1].strip().replace("ms", ""))
                return latency
    except:
        return None

# Rule-based classifier for overall issue status
def classify_issue(ping_status, feed_status, latency_history):
    if not ping_status:
        return "⚠️ Power failure or disconnected"
    elif ping_status and not feed_status:
        return "📷 Camera reachable but not streaming"
    elif latency_history and latency_history[-1] and latency_history[-1] > 200:
        return "🌐 High latency / network congestion"
    elif all(lat is not None and lat < 200 for lat in list(latency_history)[-3:]):
        return "✅ Operational"
    else:
        return "🟡 Intermittent or unclear issue"

if __name__ == "__main__":
    ip_address = "192.168.192.65"  # Your IP webcam address
    status_history = deque(maxlen=3)
    latency_history = deque(maxlen=3)

    # Track consecutive failed pings
    consecutive_failed_pings = 0
    max_failed_pings = 5  # Number of failed pings before sending email

    for i in range(10):
        ping_status = ping_camera(ip_address)
        feed_status = check_camera_feed(ip_address) if ping_status else False
        latency = get_ping_latency(ip_address) if ping_status else None

        status_history.append(ping_status)
        latency_history.append(latency)

        issue = classify_issue(ping_status, feed_status, latency_history)

        # Console output
        print(f"[Check {i+1}] Ping: {'✔️' if ping_status else '❌'} | Feed: {'🎥' if feed_status else '🚫'} | Latency: {latency} ms → {issue}")

        # Log all checks
        logger_all.info(f"{ip_address} - Ping: {ping_status} - Feed: {feed_status} - Latency: {latency} - {issue}")

        # Log only failures
        if not ping_status or not feed_status or (latency is not None and latency > 200):
            logger_fail.warning(f"{ip_address} - FAILURE - Ping: {ping_status} - Feed: {feed_status} - Latency: {latency} - {issue}")

            # Increment the failed ping count
            consecutive_failed_pings += 1

            # If 5 consecutive failures, send email and reset counter
            if consecutive_failed_pings >= max_failed_pings:
                subject = f"Camera {ip_address} - Failure Alert"
                body = f"Your camera at {ip_address} has failed to respond to {max_failed_pings} consecutive pings. Please check the device."
                send_email_notification(subject, body)
                consecutive_failed_pings = 0  # Reset the counter after sending the email

        time.sleep(5)
