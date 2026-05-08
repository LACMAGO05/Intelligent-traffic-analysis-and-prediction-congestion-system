
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from .utils import generate_otp, get_realtime_traffic, find_best_departure_time
from .services.email_service import send_verification_email, send_welcome_email, send_contact_email
from .models import ChatMessage, ChatThread
from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit
from django.contrib.auth.hashers import make_password
from django.conf import settings
from .forms import ContactForm, CustomPasswordResetForm
import traceback   #lets us print the real error to terminal
from django.utils import timezone
import datetime

from supabase import create_client
from django.contrib.auth.models import Group
from .rbac import role_required

supabase = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_KEY
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
            except Exception as e:
                print(f"Email sending failed: {e}")
                return JsonResponse({"status": "error", "message": "Failed to send email. Please try again later."}, status=500)
        else:
            return JsonResponse({"status": "error", "errors": form.errors}, status=400)
    
    return redirect('landing')

def landing_view(request):
    if request.user.is_authenticated:
        return redirect("predict")
    return render(request, "landing.html")

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


def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email    = request.POST.get("email")
        password = request.POST.get("password")

        if len(password) < 12:
            messages.error(request, "Password must be atleast 12 characters")
            return redirect("signup")
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect("signup")
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
            return redirect("signup")
        

        otp = generate_otp()
        request.session['signup_data'] = {
            'username': username,
            'email':    email,
            'password': password,
            'otp':      otp
            
        }
        success = send_verification_email(email, username, otp)
        if not success:
            messages.error(request, "Failed to send verification email. Please try again later.")
            return redirect("signup")
        return redirect("otp")
    return render(request, "sign_up.html")

class CustomPasswordResetView(auth_views.PasswordResetView):
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy('password_reset_done')


def verify_otp(request):
    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        data        = request.session.get('signup_data')
        if not data:
            return redirect("signup")
        if entered_otp == data['otp']:
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password']
            )
            commuter_group, _ = Group.objects.get_or_create(name='Commuter')
            user.groups.add(commuter_group)
            user.save()
            send_welcome_email(user.email, user.username)
            messages.success(request, "Account created successfully")
            return redirect("signin")
        else:
            messages.error(request, "Invalid OTP")
    return render(request, "otp.html")

# @login_required
# def dashboard_view(request):
#     # For Master's project feel: provide some simplified forecast data without using ML model
#     # We'll use a static forecast or a single API call for a representative route
#     # to avoid excessive API usage on every page load.
#     now = timezone.now()
#     forecast = [
#         {"time": f"{(now.hour + 1) % 24}:00", "label": "Low", "color": "green"},
#         {"time": f"{(now.hour + 2) % 24}:00", "label": "Medium", "color": "yellow"},
#         {"time": f"{(now.hour + 3) % 24}:00", "label": "Low", "color": "green"},
#     ]
#
#     return render(request, 'predict.html', {
#         'google_maps_api_key': settings.GOOGLE_CLIENT_SECRET,
#         'forecast': forecast
#     })


def logout_view(request):
    logout(request)
    return redirect("landing")

@login_required
def get_gridlock_alerts(request):
    """
    Checks for high congestion in key Buea routes and returns alerts.
    """
    routes_to_check = [
        ("Mile 17 Buea", "Malingo Junction Buea"),
        ("Malingo Junction Buea", "Great Soppo Buea"),
        ("Great Soppo Buea", "Check Point Buea"),
        ("Check Point Buea", "Mile 17 Buea")
    ]
    
    alerts = []
    try:
        for origin, destination in routes_to_check:
            # We can use real-time traffic for current alerts
            data = get_realtime_traffic(origin, destination)
            if data.get("congestion") == "High":
                alerts.append({
                    "route": data["route"],
                    "congestion": "High",
                    "travel_time": data["travel_time"],
                    "timestamp": timezone.now().strftime("%H:%M")
                })
        return JsonResponse({"alerts": alerts})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

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

@role_required('Admin', 'Analyst', 'Commuter')
def predict_view(request):
    if request.method == "POST":
        try:
            origin = request.POST.get("origin", "").strip()
            destination = request.POST.get("destination", "").strip()
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

            # Always use Google Real-time API (or future departure_time)
            traffic_data = get_realtime_traffic(origin, destination, departure_time=departure_time)

            if "error" in traffic_data:
                return JsonResponse({"error": traffic_data["error"]}, status=500)

            if traffic_data.get("is_prediction"):
                traffic_data["confidence"] = 100 # Google Maps data is highly reliable

            # If congestion is medium or high, suggest a better time if it's a 'now' request
            if departure_time == "now" and traffic_data.get("congestion") in ["Medium", "High"]:
                recommendation = find_best_departure_time(origin, destination)
                if recommendation:
                    traffic_data["recommended_departure"] = recommendation

            # ── Save all results to CSV ──────────────────────────────
            csv_file = os.path.join(settings.BASE_DIR, "google_traffic_data.csv")
            fieldnames = ["route", "distance", "hour", "day", "travel_time", "speed", "congestion"]
            save_data = {
                "route": traffic_data.get("route"),
                "distance": traffic_data.get("distance"),
                "hour": traffic_data.get("hour"),
                "day": traffic_data.get("day"),
                "travel_time": traffic_data.get("travel_time"),
                "speed": traffic_data.get("speed"),
                "congestion": traffic_data.get("congestion")
            }
            file_exists = os.path.isfile(csv_file)
            with open(csv_file, mode='a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(save_data)

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
                response=traffic_data
            )

            response_data = traffic_data.copy()
            response_data["thread_id"] = str(thread.id)
            response_data["thread_title"] = thread.title

            return JsonResponse(response_data)

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=500)

    # GET request: Load the page
    return render(request, 'predict.html', {
        'google_maps_api_key': settings.GOOGLE_CLIENT_SECRET
    })

@login_required
def chat_history_view(request):
    """
    Returns the chat history (threads) for the logged-in user.
    """
    threads = ChatThread.objects.filter(user=request.user).order_by('-created_at')
    history = []
    for thread in threads:
        history.append({
            "id": str(thread.id),
            "title": thread.title,
            "timestamp": thread.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return JsonResponse({"history": history})

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
        response = supabase.table("chat_history").select("*").execute()
        data     = response.data

        total  = len(data)
        high   = sum(1 for r in data if r.get('prediction') == "High")
        medium = sum(1 for r in data if r.get('prediction') == "Medium")
        low    = sum(1 for r in data if r.get('prediction') == "Low")

        context = {
            "total":  total,
            "high":   high,
            "medium": medium,
            "low":    low,
        }
        return render(request, "analytics.html", context)

    except Exception as e:
        print("[ANALYTICS ERROR]")
        traceback.print_exc()
        return JsonResponse({"error": "Failed to load analytics"}, status=500)
