import os
import django
from django.core.mail import send_mail
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TrafficPro.settings')
django.setup()

def test_sendgrid_email():
    print("--- SendGrid SMTP Test ---")
    print(f"Using EMAIL_HOST: {settings.EMAIL_HOST}")
    print(f"Using EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
    print(f"Using DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    
    recipient = os.getenv("TEST_EMAIL_RECIPIENT")
    if not recipient:
        print("Error: TEST_EMAIL_RECIPIENT environment variable not set.")
        return

    try:
        sent = send_mail(
            subject="SendGrid SMTP Test Email",
            message="If you are reading this, your SendGrid SMTP integration is working correctly!",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        if sent:
            print(f"SUCCESS: Email sent to {recipient}")
        else:
            print("FAILURE: Email not sent (count is 0)")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_sendgrid_email()
