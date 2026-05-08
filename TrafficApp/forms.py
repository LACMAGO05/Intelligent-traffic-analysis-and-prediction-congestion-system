from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from .services.email_service import send_password_reset_email

class ContactForm(forms.Form):
    SUBJECT_CHOICES = [
        ('feedback', 'Feedback'),
        ('issue', 'Report an Issue'),
        ('question', 'Ask a Question'),
        ('complaint', 'Submit a Complaint'),
    ]
    
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={
        'placeholder': 'Your Full Name',
        'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-transparent transition-all outline-none'
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'placeholder': 'Your Email Address',
        'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-transparent transition-all outline-none'
    }))
    subject = forms.ChoiceField(choices=SUBJECT_CHOICES, widget=forms.Select(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-transparent transition-all outline-none bg-white'
    }))
    message = forms.CharField(widget=forms.Textarea(attrs={
        'placeholder': 'How can we help you?',
        'rows': 4,
        'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-transparent transition-all outline-none resize-none'
    }))

class CustomPasswordResetForm(PasswordResetForm):
    def save(
        self,
        domain_override=None,
        subject_template_name=None,
        email_template_name=None,
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
        **kwargs
    ):
        """
        Generates password reset link and sends via SendGrid API
        """

        email = self.cleaned_data["email"]

        if not domain_override:
            current_site = get_current_site(request)
            domain = current_site.domain
        else:
            domain = domain_override

        UserModel = get_user_model()
        email_field_name = UserModel.get_email_field_name()

        users = UserModel._default_manager.filter(
            **{
                f"{email_field_name}__iexact": email,
                "is_active": True,
            }
        )

        for user in users:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)

            protocol = "https" if use_https else "http"

            reset_link = f"{protocol}://{domain}/reset/{uid}/{token}/"

            # 🔥 Send using SendGrid API
            send_password_reset_email(user.email, reset_link)