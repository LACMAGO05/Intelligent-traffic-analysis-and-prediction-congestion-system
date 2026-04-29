
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from .utils import generate_otp, get_realtime_traffic
from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit
from django.contrib.auth.hashers import make_password
from django.conf import settings
import traceback   #lets us print the real error to terminal
import datetime

from supabase import create_client
from django.contrib.auth.models import Group
from .rbac import role_required

supabase = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_KEY
)

def signin_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
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
            'password': make_password(password),
            'otp':      otp
            
        }
        send_mail(
            "Please verify your email address",
            f"Hi {username}, We received your request for a single-use code to finish your Traffik account creation.\n\nPlease use the 6-digit code below to verify your email address for Traffik.\n\n Your verification code: {otp}\n\nThanks,\nThe Traffik account team",
            "rebeccalacmago@gmail.com",
            [email],
            fail_silently=False,
        )
        return redirect("otp")
    return render(request, "sign_up.html")


def verify_otp(request):
    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        data        = request.session.get('signup_data')
        if not data:
            return redirect("signup")
        if entered_otp == data['otp']:
            user = User.objects.create(
                username=data['username'],
                email=data['email'],
                password=data['password']
            )
            commuter_group = Group.objects.get(name='Commuter')
            user.groups.add(commuter_group)
            user.save()
            messages.success(request, "Account created successfully")
            return redirect("signin")
        else:
            messages.error(request, "Invalid OTP")
    return render(request, "otp.html")

@login_required
def dashboard_view(request):
    # For Master's project feel: provide some simplified forecast data without using ML model
    # We'll use a static forecast or a single API call for a representative route
    # to avoid excessive API usage on every page load.
    now = datetime.datetime.now()
    forecast = [
        {"time": f"{(now.hour + 1) % 24}:00", "label": "Low", "color": "green"},
        {"time": f"{(now.hour + 2) % 24}:00", "label": "Medium", "color": "yellow"},
        {"time": f"{(now.hour + 3) % 24}:00", "label": "Low", "color": "green"},
    ]

    return render(request, 'dashboard.html', {
        'google_maps_api_key': settings.GOOGLE_CLIENT_SECRET,
        'forecast': forecast
    })


def logout_view(request):
    logout(request)
    return redirect("signin")

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
                    "timestamp": datetime.datetime.now().strftime("%H:%M")
                })
        return JsonResponse({"alerts": alerts})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# PREDICT VIEW — with proper error logging

try:
    import pandas as pd
except ImportError:
    pd = None
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

            now = datetime.datetime.now()
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

            # ── Save all results to CSV ──────────────────────────────
            if pd:
                csv_file = os.path.join(settings.BASE_DIR, "google_traffic_data.csv")
                # Flatten the data for CSV
                save_data = {
                    "route": traffic_data.get("route"),
                    "distance": traffic_data.get("distance"),
                    "hour": traffic_data.get("hour"),
                    "day": traffic_data.get("day"),
                    "travel_time": traffic_data.get("travel_time"),
                    "speed": traffic_data.get("speed"),
                    "congestion": traffic_data.get("congestion")
                }
                df = pd.DataFrame([save_data])
                file_exists = os.path.isfile(csv_file)
                df.to_csv(csv_file, mode='a', header=not file_exists, index=False)

            return JsonResponse(traffic_data)

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=500)

    # GET request: Load the page
    return render(request, 'dashboard.html', {
        'google_maps_api_key': settings.GOOGLE_CLIENT_SECRET
    })


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
