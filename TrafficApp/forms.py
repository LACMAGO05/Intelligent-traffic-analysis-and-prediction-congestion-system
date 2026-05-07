from django import forms

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
