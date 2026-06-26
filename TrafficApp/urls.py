from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
urlpatterns = [
    path('healthz/', views.healthz, name='healthz'),
    path('', views.landing_view, name='landing'),
    path('login/', views.signin_view, name='signin'),
    path('signup/', views.signup_view, name='signup'),
    path("logout/", views.logout_view, name="logout"),
    # path('dashboard/', views.dashboard_view, name='dashboard'),
    path("otp/", views.verify_otp, name="otp"),
    path("verify-device/", views.verify_device, name="verify_device"),
    path("devices/", views.devices_view, name="devices"),
    path("alerts/", views.alerts_view, name="alerts"),
    path("push/subscribe/", views.save_push_subscription, name="push_subscribe"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("tasks/run/", views.run_scheduled_tasks, name="run_tasks"),
    path("predict/", views.predict_view, name="predict"),
    # path("alerts/", views.get_gridlock_alerts, name="alerts"),
    path("chat-history/", views.chat_history_view, name="chat_history"),
    path("chat-history/<uuid:thread_id>/", views.thread_detail_view, name="thread_detail"),
    path('analytics/', views.analytics_view, name='analytics'),
    path('contact/', views.contact_view, name='contact'),
    path('privacy/', views.privacy_view, name='privacy'),

    # Password Reset URLs
    path('password_reset/', views.CustomPasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
]
