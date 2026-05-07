import logging
import traceback
from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger(__name__)


def _send_email_safe(subject, message, to_email):
    """
    Send email using SendGrid API (NOT SMTP)
    """
    try:
        sg = SendGridAPIClient(settings.EMAIL_HOST_PASSWORD)

        email = Mail(
            from_email=settings.DEFAULT_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            plain_text_content=message,
        )

        response = sg.send(email)

        if response.status_code == 202:
            logger.info(f"✅ Email sent: '{subject}' to {to_email}")
            return True
        else:
            logger.warning(f"⚠️ SendGrid failed: {response.status_code} - {response.body}")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to send email '{subject}' to {to_email}. Error: {str(e)}")
        logger.error(traceback.format_exc())
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