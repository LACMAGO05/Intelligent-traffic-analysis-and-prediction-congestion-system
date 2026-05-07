from .forms import ContactForm

def contact_form(request):
    return {
        'contact_form': ContactForm()
    }
