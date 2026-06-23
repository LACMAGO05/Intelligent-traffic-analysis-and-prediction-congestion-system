
from urllib import request

from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from .utils import generate_otp, get_realtime_traffic, find_best_departure_time
from .services.email_service import (
    send_verification_email, send_welcome_email, send_contact_email,
    send_device_verification_email, send_new_device_login_alert,
)
from .tasks import run_async
from .models import ChatMessage, ChatThread, PredictionLog, TrustedDevice, TrafficRecord, AnalyticsEvent
from django.core.paginator import Paginator
from .services.hybrid_prediction_service import HybridPredictionService

from django.http import JsonResponse
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
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
import secrets
import logging

logger = logging.getLogger(__name__)

# ── New-device login verification (step-up MFA via emailed code) ───────────────
# A long-lived cookie marks a browser the user has already verified. Its raw
# token is random and only the SHA-256 hash is stored server-side (TrustedDevice).
TRUSTED_DEVICE_COOKIE = "trusted_device"
TRUSTED_DEVICE_MAX_AGE = 60 * 60 * 24 * 60  # 60 days


def _log_event(request, event, user=None):
    """
    Record a product-analytics event (best-effort; never breaks the request).

    Ensures the session has a key so anonymous activity can later be attributed
    to a signup that happens in the same browser session.
    """
    try:
        if not request.session.session_key:
            request.session.save()
        AnalyticsEvent.objects.create(
            event=event,
            session_key=request.session.session_key or "",
            user=user,
        )
    except Exception:
        logger.exception("Failed to log analytics event %s", event)


def _client_ip(request):
    """Best-effort client IP, honouring the proxy header Render sits behind."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _is_trusted_device(request, user):
    """True if this browser carries a valid, non-expired trusted-device cookie."""
    raw = request.COOKIES.get(TRUSTED_DEVICE_COOKIE)
    if not raw:
        return False
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    device = TrustedDevice.objects.filter(
        user=user, token_hash=token_hash, expires_at__gte=timezone.now()
    ).first()
    if not device:
        return False
    device.save(update_fields=["last_seen"])  # auto_now refreshes last_seen
    return True


def _remember_device(request, response, user):
    """Persist a new trusted device and drop its token in a secure cookie."""
    raw_token = secrets.token_urlsafe(32)
    TrustedDevice.objects.create(
        user=user,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
        ip_address=_client_ip(request),
        expires_at=timezone.now() + datetime.timedelta(seconds=TRUSTED_DEVICE_MAX_AGE),
    )
    response.set_cookie(
        TRUSTED_DEVICE_COOKIE,
        raw_token,
        max_age=TRUSTED_DEVICE_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )

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
        if user is None:
            # Same message whether the username exists or not — never reveal which.
            messages.error(request, "Invalid username or password")
            return redirect("signin")

        # Known device → log in straight away.
        if _is_trusted_device(request, user):
            login(request, user)
            return redirect("predict")

        # New/unknown device → require an emailed one-time code before granting a
        # session (step-up verification). We do NOT call login() yet; the user's
        # identity is parked in the session until the code is confirmed.
        code = generate_otp()
        request.session['pending_login'] = {
            'user_id': user.pk,
            'code_hash': hashlib.sha256(code.encode()).hexdigest(),
            'created_at': timezone.now().isoformat(),
            'attempts': 0,
        }

        if not send_device_verification_email(user.email, user.username, code):
            del request.session['pending_login']
            messages.error(request, "We couldn't send your verification code. Please try again.")
            return redirect("signin")

        messages.success(request, "New device detected. We emailed you a sign-in verification code.")
        return redirect("verify_device")

    return render(request, 'sign_in.html')


@ratelimit(key='ip', rate='5/10m', method='POST', block=True)
def verify_device(request):
    """Confirm the emailed code for a login from an unrecognised device."""
    data = request.session.get('pending_login')

    # GET: show the code-entry page, but only if a login is actually pending.
    if request.method != 'POST':
        if not data:
            return redirect('signin')
        return render(request, 'verify_device.html')

    if not data:
        messages.error(request, 'Your sign-in session expired. Please log in again.')
        return redirect('signin')

    created_at = datetime.datetime.fromisoformat(data['created_at'])
    if timezone.is_naive(created_at):
        created_at = timezone.make_aware(created_at)
    if (timezone.now() - created_at).total_seconds() > 600:
        del request.session['pending_login']
        messages.error(request, 'The verification code expired. Please log in again.')
        return redirect('signin')

    attempts = data.get('attempts', 0)
    if attempts >= 5:
        del request.session['pending_login']
        messages.error(request, 'Too many incorrect attempts. Please log in again.')
        return redirect('signin')

    entered = request.POST.get('otp', '').strip()
    if hashlib.sha256(entered.encode()).hexdigest() != data['code_hash']:
        data['attempts'] = attempts + 1
        request.session['pending_login'] = data
        request.session.modified = True
        messages.error(request, f'Invalid code. {5 - data["attempts"]} attempts remaining.')
        return render(request, 'verify_device.html')

    # Code correct → resolve the parked user and start the real session.
    try:
        user = User.objects.get(pk=data['user_id'])
    except User.DoesNotExist:
        del request.session['pending_login']
        messages.error(request, 'Account not found. Please log in again.')
        return redirect('signin')

    del request.session['pending_login']
    login(request, user)

    # Notify the owner of the new-device sign-in (off the request path) so they
    # can react if it wasn't them.
    run_async(
        send_new_device_login_alert,
        user.email, user.username,
        ip=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
        when=timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M %Z"),
    )

    response = redirect('predict')
    # Remember this browser so future logins from it skip the email challenge.
    _remember_device(request, response, user)
    return response


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


class CustomPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """
    On a successful password change, revoke all trust for that account:
    delete every trusted device AND every active session. A password reset is
    the user's "I may be compromised" signal, so a stolen cookie or hijacked
    session must not survive it, and every device must re-verify on next login.
    """
    success_url = reverse_lazy('password_reset_complete')

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        TrustedDevice.objects.filter(user=user).delete()
        uid = str(user.pk)
        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            if session.get_decoded().get('_auth_user_id') == uid:
                session.delete()
        return response


@login_required
def devices_view(request):
    """
    Let a signed-in user review and revoke their trusted devices (the browsers
    that skip new-device email verification). Revoking forces that device to
    pass the emailed-code challenge again on its next login.
    """
    if request.method == "POST":
        if request.POST.get("action") == "revoke_all":
            request.user.trusted_devices.all().delete()
            messages.success(
                request,
                "All trusted devices removed. Every device must verify by email on next sign-in.",
            )
        else:
            deleted, _ = TrustedDevice.objects.filter(
                user=request.user, pk=request.POST.get("device_id")
            ).delete()
            messages.success(request, "Device removed.") if deleted else \
                messages.error(request, "That device was not found.")
        return redirect("devices")

    # Flag the row (if any) that belongs to the browser making this request.
    current_hash = None
    raw = request.COOKIES.get(TRUSTED_DEVICE_COOKIE)
    if raw:
        current_hash = hashlib.sha256(raw.encode()).hexdigest()

    devices = list(request.user.trusted_devices.filter(expires_at__gte=timezone.now()))
    for d in devices:
        d.is_current = (d.token_hash == current_hash)

    return render(request, "manage_devices.html", {"devices": devices})

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

    # Funnel events: every signup, plus a conversion if this same session had
    # previously hit the guest trial wall.
    _log_event(request, AnalyticsEvent.EVENT_SIGNUP, user=user)
    if request.session.pop('saw_wall', False):
        _log_event(request, AnalyticsEvent.EVENT_GUEST_CONVERTED, user=user)

    # Welcome email is non-critical; send it off the request path.
    run_async(send_welcome_email, user.email, user.username)
    messages.success(request, 'Your account has been created. Please log in.')
    return redirect('signin')


def logout_view(request):
    # Log the user out of EVERY device, not just this one. Django's default
    # logout(request) only deletes the current device's session row; here we
    # first delete all active session rows belonging to this user so their
    # other devices are logged out on their next request.
    user = request.user
    if user.is_authenticated:
        uid = str(user.pk)
        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            if session.get_decoded().get('_auth_user_id') == uid:
                session.delete()
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


# How many free predictions an anonymous visitor gets per session before being
# asked to create an account (the "try it like ChatGPT" trial). Kept small to
# protect the paid Google Maps API from anonymous abuse.
GUEST_FREE_PREDICTIONS = 2


# IP-keyed so anonymous guests are covered too (a 'user' key is empty for them).
@ratelimit(key='ip', rate='20/m', method='POST', block=True)
def predict_view(request):
    is_guest = not request.user.is_authenticated
    if request.method == "POST":
        try:
            origin = sanitize_location(request.POST.get('origin', ''))
            destination = sanitize_location(request.POST.get('destination', ''))
            pred_day = request.POST.get("day", "now")
            pred_time = request.POST.get("time", "")

            if not origin or not destination:
                return JsonResponse({"error": "Please provide both origin and destination."}, status=400)

            # Guest trial wall: allow a few free predictions per session, then
            # require an account. Checked BEFORE the paid Maps call so an
            # over-quota guest never spends our API budget.
            guest_used = request.session.get('guest_predictions_used', 0)
            if is_guest and guest_used >= GUEST_FREE_PREDICTIONS:
                # Funnel: remember this session saw the wall so a later signup
                # can be attributed as a conversion.
                request.session['saw_wall'] = True
                _log_event(request, AnalyticsEvent.EVENT_WALL_HIT)
                return JsonResponse({
                    "auth_required": True,
                    "message": "You've used your free predictions. Create a free account to keep predicting — it only takes a minute.",
                })

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

            # Guests have no persistent chat history: just count the free use
            # and return the result (with how many trials remain).
            if is_guest:
                request.session['guest_predictions_used'] = guest_used + 1
                _log_event(request, AnalyticsEvent.EVENT_GUEST_PREDICTION)
                response_data = prediction_data.copy()
                response_data["guest"] = True
                response_data["remaining_free"] = GUEST_FREE_PREDICTIONS - (guest_used + 1)
                return JsonResponse(response_data)

            # Authenticated users: save to Chat History.
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
    guest_remaining = None
    if is_guest:
        guest_remaining = max(0, GUEST_FREE_PREDICTIONS - request.session.get('guest_predictions_used', 0))
    return render(request, 'predict.html', {
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'is_guest': is_guest,
        'guest_remaining': guest_remaining,
        'guest_free_total': GUEST_FREE_PREDICTIONS,
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

_CONGESTED = ["Medium", "High"]
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _congested_pct(qs):
    """Percentage of rows in a TrafficRecord queryset that are Medium/High."""
    agg = qs.aggregate(
        total=Count("id"),
        congested=Count("id", filter=Q(congestion__in=_CONGESTED)),
    )
    total = agg["total"] or 0
    return round(100 * agg["congested"] / total) if total else 0


# Analytics — Admin and Analyst only
@role_required('Admin', 'Analyst')
def analytics_view(request):
    try:
        is_admin = (request.user.is_superuser
                    or request.user.groups.filter(name="Admin").exists())
        tr = TrafficRecord.objects

        # ── Summary (from the rich collector dataset) ────────────────────────
        obs_total = tr.count()
        obs_high = tr.filter(congestion="High").count()
        obs_medium = tr.filter(congestion="Medium").count()
        obs_low = tr.filter(congestion="Low").count()
        congested_overall = (
            round(100 * (obs_high + obs_medium) / obs_total) if obs_total else 0
        )

        # ── 1. Peak-hour heatmap: % congested per (day_of_week, hour) ─────────
        grid_qs = (
            tr.filter(day_of_week__isnull=False, hour__isnull=False)
            .values("day_of_week", "hour")
            .annotate(
                total=Count("id"),
                congested=Count("id", filter=Q(congestion__in=_CONGESTED)),
            )
        )
        grid = {}
        for r in grid_qs:
            pct = round(100 * r["congested"] / r["total"]) if r["total"] else 0
            grid[(r["day_of_week"], r["hour"])] = (pct, r["total"])
        heatmap = []
        for d in range(7):
            cells = []
            for h in range(24):
                pct, total = grid.get((d, h), (None, 0))
                cells.append({"hour": h, "pct": pct, "total": total})
            heatmap.append({"day": _DAY_NAMES[d], "cells": cells})

        # ── 2. Worst corridors: top routes by % congested (min sample size) ───
        MIN_SAMPLES = 20
        routes_qs = (
            tr.values("route")
            .annotate(
                total=Count("id"),
                congested=Count("id", filter=Q(congestion__in=_CONGESTED)),
            )
            .filter(total__gte=MIN_SAMPLES)
        )
        worst_routes = sorted(
            (
                {
                    "route": r["route"],
                    "pct": round(100 * r["congested"] / r["total"]),
                    "total": r["total"],
                }
                for r in routes_qs
            ),
            key=lambda x: x["pct"],
            reverse=True,
        )[:10]

        # ── 3. Context impact: % congested with vs without each factor ────────
        context_impact = [
            {"factor": "Rain", "with": _congested_pct(tr.filter(rainfall_status="Rain")),
             "without": _congested_pct(tr.exclude(rainfall_status="Rain"))},
            {"factor": "School hours", "with": _congested_pct(tr.filter(school_hours_indicator=1)),
             "without": _congested_pct(tr.filter(school_hours_indicator=0))},
            {"factor": "Office rush", "with": _congested_pct(tr.filter(office_rush_hour_indicator=1)),
             "without": _congested_pct(tr.filter(office_rush_hour_indicator=0))},
            {"factor": "Holiday", "with": _congested_pct(tr.filter(holiday_indicator=1)),
             "without": _congested_pct(tr.filter(holiday_indicator=0))},
        ]

        # ── 4. Admin: usage, adoption (from PredictionLog + Users) ────────────
        total_predictions = PredictionLog.objects.count()
        guest_predictions = PredictionLog.objects.filter(user__isnull=True).count()
        admin_panel = None
        if is_admin:
            since = timezone.now() - datetime.timedelta(days=14)
            usage_qs = (
                PredictionLog.objects.filter(created_at__gte=since)
                .annotate(d=TruncDate("created_at"))
                .values("d")
                .annotate(c=Count("id"))
                .order_by("d")
            )
            # Guest → signup conversion funnel (distinct sessions per stage).
            ev = AnalyticsEvent.objects
            funnel_tried = (ev.filter(event=AnalyticsEvent.EVENT_GUEST_PREDICTION)
                            .exclude(session_key="").values("session_key").distinct().count())
            funnel_wall = (ev.filter(event=AnalyticsEvent.EVENT_WALL_HIT)
                           .exclude(session_key="").values("session_key").distinct().count())
            funnel_converted = ev.filter(event=AnalyticsEvent.EVENT_GUEST_CONVERTED).count()
            conversion_rate = round(100 * funnel_converted / funnel_wall) if funnel_wall else 0

            admin_panel = {
                "usage": [{"date": u["d"].strftime("%b %d"), "count": u["c"]} for u in usage_qs],
                "total_users": User.objects.count(),
                "registered_predictions": total_predictions - guest_predictions,
                "guest_predictions": guest_predictions,
                "funnel_tried": funnel_tried,
                "funnel_wall": funnel_wall,
                "funnel_converted": funnel_converted,
                "conversion_rate": conversion_rate,
            }

        context = {
            "obs_total": obs_total,
            "obs_high": obs_high,
            "obs_medium": obs_medium,
            "obs_low": obs_low,
            "congested_overall": congested_overall,
            "total_predictions": total_predictions,
            "guest_predictions": guest_predictions,
            "heatmap": heatmap,
            "worst_routes": worst_routes,
            "context_impact": context_impact,
            "is_admin": is_admin,
            "admin_panel": admin_panel,
        }
        return render(request, "analytics.html", context)

    except Exception:
        logger.exception("Failed to load analytics")
        return JsonResponse({"error": "Failed to load analytics"}, status=500)
