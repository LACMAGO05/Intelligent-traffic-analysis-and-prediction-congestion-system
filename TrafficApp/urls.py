from django.urls import path
from . import views
from .audio_handler import transcribe_audio

urlpatterns = [
    path('', views.signin_view, name='signin'),
    path('signup/', views.signup_view, name='signup'),
    path("logout/", views.logout_view, name="logout"),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path("otp/", views.verify_otp, name="otp"),
    path("predict/", views.predict_view, name="predict"),
    path("alerts/", views.get_gridlock_alerts, name="alerts"),
    path('analytics/', views.analytics_view, name='analytics'),
    path('transcribe/', transcribe_audio, name="transcribe"),
]
