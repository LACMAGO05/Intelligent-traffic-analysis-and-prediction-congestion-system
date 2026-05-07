import os
import django
from django.core.mail import send_mail
from django.conf import settings
from TrafficApp.services.email_service import send_verification_email

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TrafficPro.settings')
django.setup()

def test_service():
    print("--- Service Email Test ---")
    recipient = os.getenv("TEST_EMAIL_RECIPIENT", "traffik147@gmail.com")
    username = "TestUser"
    otp = "123456"
    
    print(f"Attempting to send verification email to {recipient} via service...")
    success = send_verification_email(recipient, username, otp)
    
    if success:
        print("SUCCESS: Service reported success.")
    else:
        print("FAILURE: Service reported failure.")

if __name__ == "__main__":
    test_service()
