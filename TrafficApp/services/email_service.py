import os
import requests
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import logging

logger = logging.getLogger(__name__)


def _lookup_location(ip):
    """
    Best-effort, human-readable location for an IP (e.g. "Buea, Cameroon").

    Uses the free, keyless ip-api.com endpoint. Never raises: any failure,
    timeout, or private/loopback IP just yields "Unknown location" so the
    caller (a non-critical alert email) is unaffected.
    """
    if not ip or ip.startswith(("127.", "10.", "192.168.", "172.")):
        return "Unknown location"
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,city,regionName,country",
            timeout=4,
        )
        data = resp.json()
        if data.get("status") == "success":
            parts = [data.get("city"), data.get("regionName"), data.get("country")]
            located = ", ".join(p for p in parts if p)
            return located or "Unknown location"
    except Exception as e:
        logger.warning("IP geolocation failed for %s: %s", ip, e)
    return "Unknown location"

def _send_email_safe(subject, message, recipient_list):
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))

        email = Mail(
            from_email=os.getenv("DEFAULT_FROM_EMAIL"),
            to_emails=recipient_list,
            subject=subject,
            plain_text_content=message,
        )

        response = sg.send(email)

        if response.status_code in [200, 202]:
            logger.info(f"Email sent successfully to {recipient_list}")
            return True
        else:
            logger.error(f"SendGrid failed: {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"Email error: {str(e)}")
        return False

def send_verification_email(user_email, username, otp):
    subject = "Please verify your email address"
    message = (
        f"Hi {username},\n\n"
        f"We received your request for a single-use code to finish your Traffik account creation.\n\n"
        f"Your verification code: {otp}\n\n"
        f"Thanks,\n"
        f"The Traffik team"
    )
    return _send_email_safe(subject, message, user_email)


def send_device_verification_email(user_email, username, code):
    subject = "Your Traffik sign-in verification code"
    message = (
        f"Hi {username},\n\n"
        f"We noticed a sign-in to your Traffik account from a device we don't recognise.\n\n"
        f"Your sign-in verification code: {code}\n\n"
        f"Enter this code to finish signing in. It expires in 10 minutes.\n\n"
        f"If this wasn't you, do NOT share this code — change your password immediately.\n\n"
        f"Thanks,\n"
        f"The Traffik team"
    )
    return _send_email_safe(subject, message, user_email)


def send_new_device_login_alert(user_email, username, ip, user_agent, when):
    """
    Notify a user that their account was just signed in to from a new device.

    Sent AFTER a successful new-device verification so the real owner has a
    chance to react if it wasn't them. Resolves the IP to a city/country here
    (off the request path) so login latency is never affected.
    """
    location = _lookup_location(ip)
    subject = "New sign-in to your Traffik account"
    message = (
        f"Hi {username},\n\n"
        f"Your Traffik account was just signed in to from a new device:\n\n"
        f"  When:     {when}\n"
        f"  Location: {location}\n"
        f"  IP:       {ip or 'unknown'}\n"
        f"  Device:   {user_agent or 'unknown'}\n\n"
        f"If this was you, no action is needed.\n\n"
        f"If this WASN'T you, change your password immediately — that will sign out "
        f"every device and remove all trusted devices. You can also review your "
        f"trusted devices from the 'Devices' page in the app.\n\n"
        f"Thanks,\n"
        f"The Traffik team"
    )
    return _send_email_safe(subject, message, user_email)


def send_welcome_email(user_email, username):
    subject = "Welcome to Traffik!"
    message = (
        f"Hi {username},\n\n"
        f"Welcome to Traffik! Your account has been successfully created.\n\n"
        f"Best regards,\n"
        f"The Traffik team"
    )
    return _send_email_safe(subject, message, user_email)


def send_password_reset_email(user_email, reset_link):
    subject = "Password Reset Request"
    message = (
        f"Hi,\n\n"
        f"Reset your password using the link below:\n\n"
        f"{reset_link}\n\n"
        f"If you didn’t request this, ignore this email.\n\n"
        f"Thanks,\n"
        f"The Traffik team"
    )
    return _send_email_safe(subject, message, user_email)


def send_contact_email(name, email, subject, message):
    email_subject = f"Contact Form: {subject} from {name}"
    email_message = f"Name: {name}\nEmail: {email}\nSubject: {subject}\n\nMessage:\n{message}"
    recipient = os.getenv("DEFAULT_FROM_EMAIL")
    return _send_email_safe(email_subject, email_message, recipient)