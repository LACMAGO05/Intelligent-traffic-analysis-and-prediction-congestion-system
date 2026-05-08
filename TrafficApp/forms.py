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
    def save(self, domain_override=None,
             email_template_name='registration/password_reset_email.html',
             use_https=False, token_generator=default_token_generator,
             from_email=None, request=None, html_email_template_name=None,
             extra_email_context=None):
        """
        Generates a one-time use link and sends it to the user via SendGrid.
        """
        email = self.cleaned_data["email"]
        if not domain_override:
            current_site = get_current_site(request)
            site_name = current_site.name
            domain = current_site.domain
        else:
            site_name = domain = domain_override
        
        UserModel = get_user_model()
        email_field_name = UserModel.get_email_field_name()
        users = UserModel._default_manager.filter(**{
            '%s__iexact' % email_field_name: email,
            'is_active': True,
        })
        
        for user in users:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            protocol = 'https' if use_https else 'http'
            
            # Use reverse if you want to be more dynamic, but django default usually matches:
            # reset_link = f"{protocol}://{domain}/reset/{uid}/{token}/"
            # However, PasswordResetForm usually handles this via templates. 
            # Here we follow the user's requirement to build the link correctly.
            
            reset_link = f"{protocol}://{domain}/reset/{uid}/{token}/"
            
            send_password_reset_email(user.email, reset_link)
