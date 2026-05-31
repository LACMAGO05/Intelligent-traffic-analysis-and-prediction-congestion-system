
from urllib import request

from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from .utils import generate_otp, get_realtime_traffic, find_best_departure_time
from .services.email_service import send_verification_email, send_welcome_email, send_contact_email
from .tasks import run_async
from .models import ChatMessage, ChatThread, PredictionLog
from django.core.paginator import Paginator
from .services.hybrid_prediction_service import HybridPredictionService

from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit
from django.contrib.auth.hashers import make_password
from django.conf import settings
from .forms import ContactForm, CustomPasswordResetForm
import traceback   #lets us print the real error to terminal
import os
import csv
from django.utils import timezone
import datetime

from django.contrib.auth.models import Group
from .rbac import role_required

from django.contrib.auth.hashers import make_password
from django.utils import timezone
import hashlib
import logging

logger = logging.getLogger(__name__)

from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy


def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            subject_key = form.cleaned_data['subject']
            message = form.cleaned_data['message']

            # Map choice key to label
            subjects = dict(ContactForm.SUBJECT_CHOICES)
            subject_label = subjects.get(subject_key, subject_key)

            email_subject = f"Contact Form: {subject_label} from {name}"
            email_message = f"Name: {name}\nEmail: {email}\nSubject: {subject_label}\n\nMessage:\n{message}"

            try:
                success = send_contact_email(name, email, subject_label, message)
                if success:
                    return JsonResponse({"status": "success", "message": "Your message has been sent successfully!"})
                else:
                    return JsonResponse({"status": "error", "message": "Failed to send email. Please try again later."}, status=500)
            except Exception:
                logger.exception("Contact email sending failed")
                return JsonResponse({"status": "error", "message": "Failed to send email. Please try again later."}, status=500)
        else:
            return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    return redirect('landing')

def landing_view(request):
    if request.user.is_authenticated:
        return redirect("predict")
    return render(request, "landing.html")

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def signin_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("predict")
        else:
            messages.error(request, "Invalid username or password")
            return redirect("signin")
    return render(request, 'sign_in.html')


@ratelimit(key='ip', rate='3/h', method='POST', block=True)
def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        if not username or not email or not password:
            messages.error(request, 'All fields are required.')
            return redirect('signup')
        if len(password) < 12:
            messages.error(request, 'Password must be at least 12 characters.')
            return redirect('signup')
        if User.objects.filter(username=username).exists():
            messages.error(request, 'That username is already taken.')
            return redirect('signup')
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'An account with that email already exists.')
            return redirect('signup')

        otp = generate_otp()
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        request.session['signup_data'] = {
            'username': username,
            'email': email,
            'password_hash': make_password(password),
            'otp_hash': otp_hash,
            'otp_created_at': timezone.now().isoformat(),
            'otp_attempts': 0,
        }

        # Deliver the verification code. If delivery fails we abandon the
        # pending signup so the user isn't stranded on the OTP page.
        email_sent = send_verification_email(email, username, otp)
        if not email_sent:
            del request.session['signup_data']
            messages.error(request, 'We could not send your verification code. Please try again.')
            return redirect('signup')

        messages.success(request, 'We sent a verification code to your email.')
        return redirect('otp')

    return render(request, 'sign_up.html')
    

class CustomPasswordResetView(auth_views.PasswordResetView):
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        # Build reset links with the scheme of the actual request so that
        # tokens are not emitted over plaintext http:// in production.
        form.save(request=self.request, use_https=self.request.is_secure())
        return super().form_valid(form)

@ratelimit(key='ip', rate='5/10m', method='POST', block=True)
def verify_otp(request):
    # GET: render the OTP entry page, but only if a signup is actually pending.
    if request.method != 'POST':
        if not request.session.get('signup_data'):
            return redirect('signup')
        return render(request, 'otp.html')

    data = request.session.get('signup_data')
    if not data:
        messages.error(request, 'Session expired. Please register again.')
        return redirect('signup')

    created_at = datetime.datetime.fromisoformat(data['otp_created_at'])
    if timezone.is_naive(created_at):
        created_at = timezone.make_aware(created_at)
    elapsed = (timezone.now() - created_at).total_seconds()
    if elapsed > 600:
        del request.session['signup_data']
        messages.error(request, 'OTP has expired. Please register again.')
        return redirect('signup')

    attempts = data.get('otp_attempts', 0)
    if attempts >= 5:
        del request.session['signup_data']
        messages.error(request, 'Too many failed attempts. Please register again.')
        return redirect('signup')

    entered_otp = request.POST.get('otp', '').strip()
    entered_hash = hashlib.sha256(entered_otp.encode()).hexdigest()
    if entered_hash != data['otp_hash']:
        data['otp_attempts'] = attempts + 1
        request.session['signup_data'] = data
        request.session.modified = True
        messages.error(request, f'Invalid OTP. {5 - data["otp_attempts"]} attempts remaining.')
        return render(request, 'otp.html')

    user = User(username=data['username'], email=data['email'])
    user.password = data['password_hash']  # already hashed during signup
    user.save()

    # New users default to the Commuter role; without a group they would be
    # blocked from the prediction view by @role_required.
    commuter_group, _ = Group.objects.get_or_create(name='Commuter')
    user.groups.add(commuter_group)

    del request.session['signup_data']
    # Welcome email is non-critical; send it off the request path.
    run_async(send_welcome_email, user.email, user.username)
    messages.success(request, 'Your account has been created. Please log in.')
    return redirect('signin')


def logout_view(request):
    logout(request)
    return redirect("landing")
import csv
import os

def get_next_weekday(start_date, weekday_name):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if weekday_name not in days:
        return start_date
    target_day = days.index(weekday_name)
    current_day = start_date.weekday()
    days_ahead = target_day - current_day
    if days_ahead < 0:
        days_ahead += 7
    return start_date + datetime.timedelta(days_ahead)


import re
def sanitize_location(value: str) -> str:
    if not value:
        return ''
    value = re.sub(r'<[^>]+>', '', value)
    value = re.sub(r'(?i)(javascript|<script|on\w+=)', '', value)
    return value.strip()[:200]


@ratelimit(key='user', rate='30/m', method='POST', block=True)
@role_required('Admin', 'Analyst', 'Commuter')
def predict_view(request):
    if request.method == "POST":
        try:
            origin = sanitize_location(request.POST.get('origin', ''))
            destination = sanitize_location(request.POST.get('destination', ''))
            pred_day = request.POST.get("day", "now")
            pred_time = request.POST.get("time", "")

            if not origin or not destination:
                return JsonResponse({"error": "Please provide both origin and destination."}, status=400)

            now = timezone.now()
            departure_time = "now"

            if pred_day != "now" or pred_time:
                # Calculate future timestamp
                target_dt = now
                if pred_day != "now":
                    target_dt = get_next_weekday(now, pred_day)

                if pred_time:
                    try:
                        hour, minute = map(int, pred_time.split(":"))
                        target_dt = target_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    except:
                        pass

                # If target_dt is in the past (e.g. today earlier), move to next occurrence
                if target_dt < now:
                    if pred_day == "now": # User selected 'now' day but past time, assume tomorrow
                        target_dt += datetime.timedelta(days=1)
                    else:
                        # Day was specified, and it's today but past time, move to next week
                        target_dt += datetime.timedelta(days=7)

                departure_time = int(target_dt.timestamp())

            # Always use Hybrid Prediction System
            hybrid_service = HybridPredictionService()
            prediction_data = hybrid_service.get_hybrid_prediction(origin, destination, departure_time)

            if "error" in prediction_data:
                return JsonResponse({"error": prediction_data["error"]}, status=500)

            # ── Log this prediction to its own durable table ─────────────
            # Kept separate from the TrafficRecord training dataset so the two
            # schemas can never collide (previously both were appended to the
            # same CSV with different columns).
            if departure_time == "now":
                log_hour, log_day = now.hour, now.strftime("%A")
            else:
                _dt = datetime.datetime.fromtimestamp(departure_time)
                log_hour, log_day = _dt.hour, _dt.strftime("%A")

            PredictionLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                origin=origin,
                destination=destination,
                distance=prediction_data.get("distance"),
                hour=log_hour,
                day=log_day,
                travel_time=prediction_data.get("travel_time"),
                speed=prediction_data.get("speed"),
                congestion=prediction_data.get("congestion") or "",
                is_prediction=bool(prediction_data.get("is_prediction")),
            )

            # Save to Chat History
            thread_id = request.POST.get("thread_id")
            thread = None
            if thread_id:
                try:
                    thread = ChatThread.objects.get(id=thread_id, user=request.user)
                except (ChatThread.DoesNotExist, ValueError):
                    pass

            if not thread:
                thread = ChatThread.objects.create(
                    user=request.user,
                    title=f"{origin} to {destination}"
                )

            ChatMessage.objects.create(
                thread=thread,
                user=request.user,
                message=f"From {origin} to {destination}",
                response=prediction_data
            )

            response_data = prediction_data.copy()
            response_data["thread_id"] = str(thread.id)
            response_data["thread_title"] = thread.title

            logger.debug(
                "Prediction %s -> %s: travel_time=%s normal=%s speed=%s distance=%s congestion=%s",
                origin, destination,
                response_data.get('travel_time'), response_data.get('normal_duration'),
                response_data.get('speed'), response_data.get('distance'),
                response_data.get('congestion'),
            )

            return JsonResponse(response_data)

        except Exception:
            # Log the full traceback server-side; never leak internals to the client.
            logger.exception("Prediction failed for %s -> %s", origin, destination)
            return JsonResponse(
                {"error": "We couldn't process your prediction right now. Please try again."},
                status=500,
            )

    # GET request: Load the page
    return render(request, 'predict.html', {
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY
    })

@login_required
def chat_history_view(request):
    """
    Returns the chat history (threads) for the logged-in user, paginated so the
    response stays bounded as a user accumulates threads.
    """
    threads = ChatThread.objects.filter(user=request.user).order_by('-created_at')

    try:
        page_size = int(request.GET.get("page_size", 20))
    except (TypeError, ValueError):
        page_size = 20
    page_size = max(1, min(page_size, 100))

    paginator = Paginator(threads, page_size)
    page = paginator.get_page(request.GET.get("page", 1))

    history = [
        {
            "id": str(thread.id),
            "title": thread.title,
            "timestamp": thread.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for thread in page
    ]
    return JsonResponse({
        "history": history,
        "page": page.number,
        "num_pages": paginator.num_pages,
        "total": paginator.count,
        "has_next": page.has_next(),
    })

@login_required
def thread_detail_view(request, thread_id):
    """
    Returns messages for a specific thread.
    """
    try:
        thread = ChatThread.objects.get(id=thread_id, user=request.user)
        messages = thread.messages.all().order_by('timestamp')
        history = []
        for msg in messages:
            history.append({
                "message": msg.message,
                "response": msg.response,
                "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M")
            })
        return JsonResponse({
            "thread_id": str(thread.id),
            "title": thread.title,
            "messages": history
        })
    except (ChatThread.DoesNotExist, ValueError):
        return JsonResponse({"error": "Thread not found"}, status=404)

# Analytics — Admin and Analyst only
@role_required('Admin', 'Analyst')
def analytics_view(request):
    try:
        # Aggregate directly from the local PredictionLog table (Postgres),
        # replacing the previous external Supabase read.
        logs = PredictionLog.objects.all()
        context = {
            "total":  logs.count(),
            "high":   logs.filter(congestion="High").count(),
            "medium": logs.filter(congestion="Medium").count(),
            "low":    logs.filter(congestion="Low").count(),
        }
        return render(request, "analytics.html", context)

    except Exception:
        logger.exception("Failed to load analytics")
        return JsonResponse({"error": "Failed to load analytics"}, status=500)
