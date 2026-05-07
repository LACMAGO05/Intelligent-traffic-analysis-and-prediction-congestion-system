import logging
from django.core.mail import send_mail
from django.conf import settings
import traceback

logger = logging.getLogger(__name__)

def send_verification_email(user_email, username, otp):
    """
    Sends a verification OTP email to the user.
    """
    subject = "Please verify your email address"
    message = (
        f"Hi {username},\n\n"
        f"We received your request for a single-use code to finish your Traffik account creation.\n\n"
        f"Please use the 6-digit code below to verify your email address for Traffik.\n\n"
        f"Your verification code: {otp}\n\n"
        f"Thanks,\n"
        f"The Traffik account team"
    )
    return _send_email_safe(subject, message, [user_email])

def send_welcome_email(user_email, username):
    """
    Sends a welcome email after successful registration.
    """
    subject = "Welcome to Traffik!"
    message = (
        f"Hi {username},\n\n"
        f"Welcome to Traffik! Your account has been successfully created.\n\n"
        f"You can now use our platform to check real-time traffic and predict travel times.\n\n"
        f"Best regards,\n"
        f"The Traffik team"
    )
    return _send_email_safe(subject, message, [user_email])

def send_password_reset_email(user_email, reset_link):
    """
    Future-proofing: Send password reset link.
    """
    subject = "Password Reset Request"
    message = (
        f"Hi,\n\n"
        f"You requested a password reset for your Traffik account.\n"
        f"Please click the link below to reset your password:\n\n"
        f"{reset_link}\n\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"Thanks,\n"
        f"The Traffik team"
    )
    return _send_email_safe(subject, message, [user_email])

def _send_email_safe(subject, message, recipient_list):
    """
    Internal helper to send email with proper error handling and logging.
    """
    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False, # We handle it in the except block
        )
        if sent_count:
            logger.info(f"Successfully sent email: '{subject}' to {recipient_list}")
            return True
        else:
            logger.warning(f"Email '{subject}' to {recipient_list} was not sent (0 count returned)")
            return False
    except Exception as e:
        logger.error(f"Failed to send email: '{subject}' to {recipient_list}. Error: {str(e)}")
        logger.error(traceback.format_exc())
        return False
