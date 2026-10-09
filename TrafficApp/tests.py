"""
Test suite covering the Phase 1 critical-security fixes.

Run against a disposable PostgreSQL database. The outbox claim tests use
``select_for_update(skip_locked=True)``, which SQLite does not implement; the
repository CI workflow provides a disposable PostgreSQL service.
"""
import os
import hashlib
from pathlib import Path
import json
import tempfile
import datetime
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase, Client, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.conf import settings
from django.core.management import call_command
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth.models import User, Group

from TrafficApp.utils import generate_otp
from TrafficApp.views import sanitize_location
from TrafficApp.models import (
    ChatThread, PredictionLog, TrafficAlert, TrafficRecord, RouteWatch, TaskOutbox,
)
from TrafficApp.forms import ContactForm
from traffic_context.congestion import CongestionIntelligence
from traffic_context.pressure_score import PressureScoreCalculator
from traffic_collector.record_store import TrafficRecordStore


# Disable rate limiting and avoid the manifest static storage (which would
# require collectstatic) for the HTTP-level tests.
TEST_OVERRIDES = dict(
    RATELIMIT_ENABLE=False,
    # The prod security block (active when DEBUG=False) would otherwise 301 every
    # plain-http test request to https before it reaches a view.
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    # Run background tasks synchronously so their side effects are assertable.
    TASK_ALWAYS_EAGER=True,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)


class SettingsTests(TestCase):
    """C1 + configuration bindings."""

    def test_debug_is_boolean(self):
        self.assertIsInstance(settings.DEBUG, bool)

    def test_google_maps_key_binding_present(self):
        # The setting must exist (value may be None in a bare env).
        self.assertTrue(hasattr(settings, "GOOGLE_MAPS_API_KEY"))

    def test_cache_backend_configured(self):
        self.assertIn("default", settings.CACHES)


class PureLogicTests(TestCase):
    """Pure, dependency-free domain logic."""

    def test_congestion_classification(self):
        self.assertEqual(CongestionIntelligence.classify(10, 10), "Low")
        self.assertEqual(CongestionIntelligence.classify(10, 14), "Medium")   # ratio 1.4
        self.assertEqual(CongestionIntelligence.classify(10, 20), "High")     # ratio 2.0
        self.assertEqual(CongestionIntelligence.classify(0, 5), "Low")        # guard

    def test_pressure_score_bounds_and_factors(self):
        calc = PressureScoreCalculator()
        clear = calc.calculate({"congestion": "Low", "hour": 3})
        self.assertGreaterEqual(clear, 0)
        heavy = calc.calculate({
            "congestion": "High", "office_rush_hour_indicator": True,
            "rainfall_status": "Rain", "hour": 8,
        })
        self.assertLessEqual(heavy, 100)
        self.assertGreater(heavy, clear)

    def test_generate_otp_format(self):
        otp = generate_otp()
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    def test_sanitize_location_strips_markup(self):
        self.assertEqual(sanitize_location("<script>alert(1)</script>Mile 17"), "alert(1)Mile 17")
        self.assertNotIn("<", sanitize_location("<b>Molyko</b>"))
        self.assertEqual(sanitize_location(""), "")
        self.assertLessEqual(len(sanitize_location("x" * 500)), 200)


@override_settings(**TEST_OVERRIDES)
class SignupOtpFlowTests(TestCase):
    """C4 — signup must deliver an OTP and the full flow must create a user."""

    def setUp(self):
        self.client = Client()

    @patch("TrafficApp.views.generate_otp", return_value="123456")
    @patch("TrafficApp.views.send_verification_email", return_value=True)
    def test_signup_sends_otp_and_redirects(self, mock_send, mock_otp):
        resp = self.client.post(reverse("signup"), {
            "username": "alice", "email": "alice@example.com",
            "password": "longenoughpassword123", "consent": "yes",
        })
        self.assertRedirects(resp, reverse("otp"), fetch_redirect_response=False)
        mock_send.assert_called_once()
        self.assertIn("signup_data", self.client.session)

    def test_signup_rejects_short_password(self):
        resp = self.client.post(reverse("signup"), {
            "username": "bob", "email": "bob@example.com", "password": "short",
            "consent": "yes",
        })
        self.assertRedirects(resp, reverse("signup"), fetch_redirect_response=False)
        self.assertNotIn("signup_data", self.client.session)

    @patch("TrafficApp.views.send_verification_email", return_value=False)
    def test_signup_aborts_when_email_fails(self, mock_send):
        resp = self.client.post(reverse("signup"), {
            "username": "carol", "email": "carol@example.com",
            "password": "longenoughpassword123", "consent": "yes",
        })
        self.assertRedirects(resp, reverse("signup"), fetch_redirect_response=False)
        self.assertNotIn("signup_data", self.client.session)

    def test_verify_otp_get_without_session_redirects_to_signup(self):
        resp = self.client.get(reverse("otp"))
        self.assertRedirects(resp, reverse("signup"), fetch_redirect_response=False)

    @patch("TrafficApp.views.enqueue")
    @patch("TrafficApp.views.send_welcome_email", return_value=True)
    @patch("TrafficApp.views.generate_otp", return_value="123456")
    @patch("TrafficApp.views.send_verification_email", return_value=True)
    def test_full_signup_then_verify_creates_user_with_role(self, m_send, m_otp, m_welcome, m_enqueue):
        self.client.post(reverse("signup"), {
            "username": "dave", "email": "dave@example.com",
            "password": "longenoughpassword123", "consent": "yes",
        })
        resp = self.client.post(reverse("otp"), {"otp": "123456"})
        self.assertRedirects(resp, reverse("signin"), fetch_redirect_response=False)
        user = User.objects.get(username="dave")
        self.assertTrue(user.groups.filter(name="Commuter").exists())
        m_enqueue.assert_called_once_with(
            "send_welcome_email", user_email=user.email, username=user.username,
        )
        # password was stored as a hash and must authenticate
        self.assertTrue(self.client.login(username="dave", password="longenoughpassword123"))

    @patch("TrafficApp.views.generate_otp", return_value="123456")
    @patch("TrafficApp.views.send_verification_email", return_value=True)
    def test_wrong_otp_does_not_create_user(self, m_send, m_otp):
        self.client.post(reverse("signup"), {
            "username": "erin", "email": "erin@example.com",
            "password": "longenoughpassword123", "consent": "yes",
        })
        self.client.post(reverse("otp"), {"otp": "000000"})
        self.assertFalse(User.objects.filter(username="erin").exists())


@override_settings(**TEST_OVERRIDES)
class RbacTests(TestCase):
    """role_required gating around the prediction view."""

    def setUp(self):
        self.client = Client()

    def test_anonymous_can_load_predict_as_guest(self):
        # Predict is now public (guest trial mode): anonymous visitors get the
        # page (200) with a limited free quota, not a redirect to login.
        resp = self.client.get(reverse("predict"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["is_guest"])

    def test_login_url_setting(self):
        self.assertEqual(settings.LOGIN_URL, "/login/")

    def test_logged_in_without_group_can_load_predict(self):
        # With guest mode, predict no longer requires a role — any visitor
        # (logged in or not) can load it.
        User.objects.create_user(username="nogroup", password="longenoughpassword123")
        self.client.login(username="nogroup", password="longenoughpassword123")
        resp = self.client.get(reverse("predict"))
        self.assertEqual(resp.status_code, 200)

    def test_commuter_can_load_predict(self):
        user = User.objects.create_user(username="commuter", password="longenoughpassword123")
        group, _ = Group.objects.get_or_create(name="Commuter")
        user.groups.add(group)
        self.client.login(username="commuter", password="longenoughpassword123")
        resp = self.client.get(reverse("predict"))
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────── Phase 2: data pipeline ──────────────────────────

def _sample_record(timestamp="2026-05-30 08:00:00", route="Molyko to Mile 17"):
    return {
        "timestamp": timestamp, "route": route,
        "distance_km": 3.2, "hour": 8, "day": "Saturday", "day_of_week": 5,
        "travel_time_mins": 12.5, "speed_kmh": 15.3, "congestion": "High",
        "weather_condition": "Rain", "rainfall_status": "Rain",
        "holiday_indicator": 0, "school_holiday_indicator": 0, "school_hours_indicator": 1,
        "working_hours_indicator": 1, "office_rush_hour_indicator": 1,
        "event_indicator": 1, "event_type": "Market Activity", "event_severity": "High",
        "traffic_pressure_score": 85,
    }


@override_settings(**TEST_OVERRIDES)
class VerificationExpiryAndAttemptTests(TestCase):
    def _set_signup_session(self, *, age_seconds=0, attempts=0):
        session = self.client.session
        session["signup_data"] = {
            "username": "pending-user",
            "email": "pending@example.com",
            "password_hash": "unused",
            "otp_hash": hashlib.sha256(b"123456").hexdigest(),
            "otp_created_at": (timezone.now() - timedelta(seconds=age_seconds)).isoformat(),
            "otp_attempts": attempts,
        }
        session.save()

    def test_signup_otp_expiry_discards_pending_signup(self):
        self._set_signup_session(age_seconds=601)
        response = self.client.post(reverse("otp"), {"otp": "123456"})
        self.assertRedirects(response, reverse("signup"), fetch_redirect_response=False)
        self.assertNotIn("signup_data", self.client.session)

    def test_signup_otp_exhausted_attempts_discards_pending_signup(self):
        self._set_signup_session(attempts=5)
        response = self.client.post(reverse("otp"), {"otp": "123456"})
        self.assertRedirects(response, reverse("signup"), fetch_redirect_response=False)
        self.assertNotIn("signup_data", self.client.session)

    def test_device_verification_exhausted_attempts_discards_pending_login(self):
        session = self.client.session
        session["pending_login"] = {
            "user_id": 1,
            "created_at": timezone.now().isoformat(),
            "code_hash": hashlib.sha256(b"123456").hexdigest(),
            "attempts": 5,
        }
        session.save()
        response = self.client.post(reverse("verify_device"), {"otp": "000000"})
        self.assertRedirects(response, reverse("signin"), fetch_redirect_response=False)
        self.assertNotIn("pending_login", self.client.session)

    def test_device_verification_locks_after_five_wrong_codes(self):
        session = self.client.session
        session["pending_login"] = {
            "user_id": 1,
            "created_at": timezone.now().isoformat(),
            "code_hash": hashlib.sha256(b"123456").hexdigest(),
            "attempts": 0,
        }
        session.save()
        for _ in range(5):
            response = self.client.post(reverse("verify_device"), {"otp": "000000"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["pending_login"]["attempts"], 5)
        response = self.client.post(reverse("verify_device"), {"otp": "123456"})
        self.assertRedirects(response, reverse("signin"), fetch_redirect_response=False)
        self.assertNotIn("pending_login", self.client.session)


class TrafficRecordStoreTests(TestCase):
    """H7/M3 — durable, de-duplicated collection store."""

    def test_append_creates_record(self):
        store = TrafficRecordStore()
        self.assertTrue(store.append_record(_sample_record()))
        self.assertEqual(TrafficRecord.objects.count(), 1)
        rec = TrafficRecord.objects.first()
        self.assertEqual(rec.route, "Molyko to Mile 17")
        self.assertEqual(rec.congestion, "High")

    def test_duplicate_timestamp_route_is_skipped(self):
        store = TrafficRecordStore()
        self.assertTrue(store.append_record(_sample_record()))
        self.assertFalse(store.append_record(_sample_record()))   # same ts+route
        self.assertEqual(TrafficRecord.objects.count(), 1)

    def test_record_with_missing_key_is_rejected(self):
        store = TrafficRecordStore()
        bad = _sample_record()
        del bad["timestamp"]
        self.assertFalse(store.append_record(bad))
        self.assertEqual(TrafficRecord.objects.count(), 0)


@override_settings(**TEST_OVERRIDES)
class AnalyticsFromPostgresTests(TestCase):
    """M5 — analytics aggregates from PredictionLog, not Supabase."""

    def setUp(self):
        self.client = Client()
        admin = User.objects.create_user(username="boss", password="longenoughpassword123")
        admin.groups.add(Group.objects.get_or_create(name="Admin")[0])
        self.client.login(username="boss", password="longenoughpassword123")
        # Summary cards aggregate the rich collector dataset (TrafficRecord).
        base = timezone.now()
        for i, cong in enumerate(["High", "High", "Medium", "Low"]):
            TrafficRecord.objects.create(
                timestamp=base - timedelta(hours=i),
                route=f"A to B {i}", congestion=cong, hour=8, day_of_week=1,
            )
        # Prediction count comes from PredictionLog.
        for cong in ["High", "Medium"]:
            PredictionLog.objects.create(origin="A", destination="B", congestion=cong)

    def test_analytics_counts(self):
        resp = self.client.get(reverse("analytics"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["obs_total"], 4)
        self.assertEqual(resp.context["obs_high"], 2)
        self.assertEqual(resp.context["obs_medium"], 1)
        self.assertEqual(resp.context["obs_low"], 1)
        self.assertEqual(resp.context["total_predictions"], 2)


@override_settings(**TEST_OVERRIDES)
class ChatHistoryPaginationTests(TestCase):
    """M4 — chat history is paginated."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="paginator", password="longenoughpassword123")
        self.client.login(username="paginator", password="longenoughpassword123")
        for i in range(25):
            ChatThread.objects.create(user=self.user, title=f"T{i}")

    def test_pagination_limits_results(self):
        resp = self.client.get(reverse("chat_history"), {"page_size": 10})
        data = resp.json()
        self.assertEqual(len(data["history"]), 10)
        self.assertEqual(data["num_pages"], 3)
        self.assertEqual(data["total"], 25)
        self.assertTrue(data["has_next"])

    def test_page_size_is_clamped(self):
        resp = self.client.get(reverse("chat_history"), {"page_size": 9999})
        self.assertLessEqual(len(resp.json()["history"]), 100)


class ManagementCommandTests(TestCase):
    """H7 export + M4 retention commands."""

    def test_export_training_data(self):
        TrafficRecordStore().append_record(_sample_record())
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "export.csv")
            call_command("export_training_data", output=out)
            with open(out) as f:
                lines = f.read().splitlines()
        self.assertEqual(len(lines), 2)            # header + 1 record
        self.assertIn("Molyko to Mile 17", lines[1])

    def test_purge_old_data(self):
        user = User.objects.create_user(username="old", password="longenoughpassword123")
        recent = ChatThread.objects.create(user=user, title="recent")
        stale = ChatThread.objects.create(user=user, title="stale")
        # auto_now_add cannot be set on create; backdate via queryset update.
        ChatThread.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=200)
        )
        call_command("purge_old_data", days=180)
        self.assertTrue(ChatThread.objects.filter(pk=recent.pk).exists())
        self.assertFalse(ChatThread.objects.filter(pk=stale.pk).exists())

    def test_purge_dry_run_keeps_data(self):
        user = User.objects.create_user(username="dry", password="longenoughpassword123")
        stale = ChatThread.objects.create(user=user, title="stale")
        ChatThread.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=200)
        )
        call_command("purge_old_data", days=180, dry_run=True)
        self.assertTrue(ChatThread.objects.filter(pk=stale.pk).exists())


# ─────────────────────────── Phase 3: performance ────────────────────────────

class ModelCacheTests(TestCase):
    """H1 — model + encoder are loaded once per process, not per request."""

    def test_artifacts_loaded_once_across_instances(self):
        from TrafficApp.services import model_service
        model_service._load_artifacts.cache_clear()
        schema = {"route_vocab": [], "feature_columns": [], "threshold": 0.5}
        with patch("TrafficApp.services.model_service.joblib.load", return_value="DUMMY") as mock_load, \
             patch("TrafficApp.services.model_service.mlf.load_schema", return_value=schema) as mock_schema, \
             patch("TrafficApp.services.model_service.os.path.exists", return_value=True):
            model_service.ModelService()
            model_service.ModelService()
            model_service.ModelService()
        # Model (joblib) and schema each loaded once despite 3 instances.
        self.assertEqual(mock_load.call_count, 1)
        self.assertEqual(mock_schema.call_count, 1)
        model_service._load_artifacts.cache_clear()


class WeatherCacheTests(TestCase):
    """H2 — weather is fetched at most once per TTL."""

    def setUp(self):
        cache.clear()

    @override_settings(OPENWEATHER_API_KEY="test-key")
    def test_weather_is_cached(self):
        from traffic_context import weather_service

        class _Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"weather": [{"main": "Rain"}]}

        with patch.object(weather_service.requests, "get", return_value=_Resp()) as mock_get:
            svc = weather_service.WeatherService()
            first = svc.get_current_weather()
            second = svc.get_current_weather()

        self.assertEqual(first, second)
        self.assertEqual(first["rainfall_status"], "Rain")
        mock_get.assert_called_once()   # second call served from cache


class HolidayCacheTests(TestCase):
    """H2 — holiday lookups are cached per date."""

    def setUp(self):
        cache.clear()

    def test_holiday_lookup_is_cached(self):
        from datetime import date
        from traffic_context.holiday_service import HolidayService
        svc = HolidayService()
        d = date(2026, 1, 1)
        result = svc.is_public_holiday(d)
        self.assertIn(result, (0, 1))
        self.assertEqual(cache.get(f"holiday:CM:{d.isoformat()}"), result)


class DirectionsClientTests(TestCase):
    """Phase 4 (L4) — one Google Directions client shared by all callers."""

    def test_clean_location_adds_region(self):
        from traffic_context.directions_client import clean_location
        self.assertEqual(clean_location("Molyko"), "Molyko, Buea, Cameroon")
        self.assertEqual(clean_location("Mile 17, Buea"), "Mile 17, Buea")

    def test_fetch_requires_api_key(self):
        from traffic_context.directions_client import DirectionsClient, DirectionsError
        with self.assertRaises(DirectionsError):
            DirectionsClient(api_key="").fetch("A", "B")

    def test_fetch_raises_on_non_ok_status(self):
        from traffic_context import directions_client as dc

        class _Resp:
            def json(self):
                return {"status": "ZERO_RESULTS"}

        with patch.object(dc.requests, "get", return_value=_Resp()):
            with self.assertRaises(dc.DirectionsError):
                dc.DirectionsClient(api_key="k").fetch("A", "B")

    def test_google_service_delegates_to_client(self):
        from TrafficApp.services.google_maps_service import GoogleMapsService
        fake = {"routes": [{"summary": "R1", "overview_polyline": {"points": "xyz"},
                "legs": [{"distance": {"value": 3200}, "duration": {"value": 600},
                          "duration_in_traffic": {"value": 900}, "steps": []}]}]}
        svc = GoogleMapsService()
        with patch.object(svc.client, "fetch", return_value=("O", "D", fake)):
            out = svc.get_route_details("Molyko", "Mile 17")
        self.assertEqual(out["status"], "success")
        self.assertEqual(out["primary_route"]["distance"], 3.2)
        self.assertEqual(out["primary_route"]["traffic_duration"], 15.0)

    def test_collector_fetch_delegates_to_client(self):
        from traffic_collector.collector import TrafficCollector
        fake = {"routes": [{"legs": [{"distance": {"value": 3000},
                "duration": {"value": 600}, "duration_in_traffic": {"value": 1200}}]}]}
        collector = TrafficCollector()
        with patch.object(collector.directions, "fetch", return_value=("O", "D", fake)):
            out = collector.fetch_google_traffic("Molyko", "Mile 17")
        self.assertEqual(out["distance_km"], 3.0)
        self.assertEqual(out["travel_time_mins"], 20.0)
        self.assertIn(out["congestion"], ("Low", "Medium", "High"))


# ─────────────────────────── Phase 5: ML pipeline ────────────────────────────

class MLFeatureTests(TestCase):
    """5.1 — shared feature engineering for train + serve."""

    def test_binary_target_mapping(self):
        import pandas as pd
        from traffic_context import ml_features as mlf
        s = pd.Series(["Low", "Medium", "High", "Low"])
        self.assertEqual(list(mlf.binary_target(s)), [0, 1, 1, 0])

    def test_feature_row_matches_schema_columns(self):
        from traffic_context import ml_features as mlf
        vocab = ["Mile 17 to Malingo", "A to B"]
        cols = mlf.feature_columns(vocab)
        feat = mlf.row_to_features({
            "distance_km": 3, "hour": 8, "day_of_week": 1,
            "weather_condition": "Rain", "rainfall_status": "Rain",
            "route": "Mile 17 to Malingo", "event_severity": "High",
        }, vocab)
        self.assertEqual(set(feat.keys()), set(cols))
        self.assertEqual(feat["is_morning_rush"], 1)
        self.assertEqual(feat["weather_Rain"], 1)
        self.assertEqual(feat["rainfall_Rain"], 1)
        self.assertEqual(feat["event_severity"], 2)
        self.assertEqual(feat[mlf.route_col("Mile 17 to Malingo")], 1)

    def test_clean_drops_corrupt_rows(self):
        import pandas as pd
        from traffic_context import ml_features as mlf
        base = {"timestamp": "2026-05-07 08:00:00", "route": "A to B", "distance_km": 3,
                "day_of_week": 1, "congestion": "Low", "weather_condition": "Clouds",
                "rainfall_status": "No Rain", "holiday_indicator": 0, "school_holiday_indicator": 0,
                "school_hours_indicator": 1, "working_hours_indicator": 1,
                "office_rush_hour_indicator": 0, "event_indicator": 0, "event_severity": "Low"}
        df = pd.DataFrame([{**base, "hour": 8}, {**base, "hour": "Monday"}])  # 2nd row corrupt
        self.assertEqual(len(mlf.clean_training_frame(df)), 1)


class ModelServingTests(TestCase):
    """5.1/5.2 — serving runs against the promoted schema (no train/serve skew)."""

    def test_predict_runs_with_promoted_schema(self):
        from TrafficApp.services import model_service
        model_service._load_artifacts.cache_clear()
        ms = model_service.ModelService()
        if not ms.model or not ms.schema:
            self.skipTest("No promoted model/schema present")
        out = ms.predict({
            "distance_km": 3.2, "hour": 8, "day_of_week": 1, "holiday_indicator": 0,
            "school_holiday_indicator": 0, "school_hours_indicator": 1,
            "working_hours_indicator": 1, "office_rush_hour_indicator": 1,
            "event_indicator": 0, "event_severity": 0, "weather_condition": "Clouds",
            "rainfall_status": "No Rain", "route": "Mile 17 to Malingo",
        })
        self.assertNotIn("error", out)
        self.assertIn(out["congestion_level"], ("Low", "Medium"))
        model_service._load_artifacts.cache_clear()


class HybridDisplayTests(TestCase):
    """5.x — final congestion shows the more severe of model vs Google."""

    def test_google_high_escalates_display(self):
        from TrafficApp.services.hybrid_prediction_service import HybridPredictionService
        svc = HybridPredictionService()
        google = {"origin": "O", "destination": "D", "is_prediction": False, "alternatives": [],
                  "departure_time": 0,
                  "primary_route": {"summary": "R", "distance": 5, "normal_duration": 10,
                                    "traffic_duration": 20, "polyline": "p", "segments_delay": []}}
        with patch.object(svc.google_maps, "get_route_details", return_value=google), \
             patch.object(svc.model_service, "predict",
                          return_value={"congestion_level": "Low", "confidence": 90, "probabilities": {}}):
            out = svc.get_hybrid_prediction("O", "D", "now")
        # Google ratio 20/10 = 2.0 -> High; model says Low -> display escalates to High.
        self.assertEqual(out["congestion"], "High")


class BackgroundTaskTests(TestCase):
    """3.3 — run_async executes work; eager mode runs it synchronously."""

    @override_settings(TASK_ALWAYS_EAGER=True)
    def test_eager_runs_synchronously(self):
        from TrafficApp.tasks import run_async
        bucket = []
        run_async(lambda x: bucket.append(x), 42)
        self.assertEqual(bucket, [42])

    @override_settings(TASK_ALWAYS_EAGER=True)
    def test_eager_swallows_exceptions(self):
        from TrafficApp.tasks import run_async
        def boom():
            raise ValueError("nope")
        # Should not propagate.
        self.assertIsNone(run_async(boom))


@override_settings(**{**TEST_OVERRIDES, "RATELIMIT_ENABLE": True})
class ContactAbuseTests(TestCase):
    def setUp(self):
        cache.clear()
        self.data = {
            "name": "TrafficPro user",
            "email": "sender@example.com",
            "subject": "question",
            "message": "Please contact me.",
        }

    def test_contact_message_has_a_server_side_length_limit(self):
        self.data["message"] = "x" * 5001
        self.assertFalse(ContactForm(data=self.data).is_valid())

    @patch("TrafficApp.views.send_contact_email", return_value=True)
    def test_contact_submission_is_rate_limited(self, mock_send):
        client = Client()
        responses = [
            client.post(reverse("contact"), self.data)
            for _ in range(6)
        ]
        self.assertEqual([response.status_code for response in responses[:5]], [200] * 5)
        self.assertEqual(responses[5].status_code, 403)
        self.assertEqual(mock_send.call_count, 5)


@override_settings(**TEST_OVERRIDES)
class ContactFailureLoggingTests(TestCase):
    @patch("TrafficApp.views.send_contact_email", side_effect=RuntimeError("private message and recipient"))
    def test_email_failure_logs_type_without_exception_contents(self, mock_send):
        with self.assertLogs("TrafficApp.views", level="ERROR") as captured:
            response = self.client.post(reverse("contact"), {
                "name": "Contact User",
                "email": "person@example.com",
                "subject": "question",
                "message": "private message and recipient",
            })
        self.assertEqual(response.status_code, 500)
        self.assertIn("RuntimeError", "\n".join(captured.output))
        self.assertNotIn("private message and recipient", "\n".join(captured.output))
        mock_send.assert_called_once()


@override_settings(**{**TEST_OVERRIDES, "CRON_SECRET": "test-only-cron-secret"})
class ScheduledTaskEndpointTests(TestCase):
    def test_get_with_query_secret_is_rejected_without_running_tasks(self):
        with patch("TrafficApp.services.alert_job.run_gridlock_alerts") as alerts, \
             patch("TrafficApp.services.outbox.process_outbox") as outbox:
            response = self.client.get(
                reverse("run_tasks"), {"token": "test-only-cron-secret"}
            )
        self.assertEqual(response.status_code, 405)
        alerts.assert_not_called()
        outbox.assert_not_called()

    @patch("TrafficApp.services.outbox.process_outbox", return_value=(2, 0))
    @patch("TrafficApp.services.alert_job.run_gridlock_alerts", return_value=1)
    def test_valid_post_header_runs_scheduled_tasks(self, alerts, outbox):
        response = self.client.post(
            reverse("run_tasks"),
            HTTP_X_CRON_SECRET="test-only-cron-secret",
        )
        self.assertEqual(response.status_code, 200)
        alerts.assert_called_once_with()
        outbox.assert_called_once_with()

    def test_query_secret_is_not_accepted_on_post(self):
        response = self.client.post(
            reverse("run_tasks"), {"token": "test-only-cron-secret"}
        )
        self.assertEqual(response.status_code, 403)


@override_settings(**TEST_OVERRIDES)
class LogoutMethodTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="logout-user", password="longenoughpassword123"
        )
        self.client.force_login(self.user)

    def test_get_does_not_log_user_out(self):
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_post_logs_user_out(self):
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(**TEST_OVERRIDES)
class OutboxClaimTests(TestCase):
    def test_pending_task_is_claimed_before_execution_and_completed(self):
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(task="test_claim")

        def verify_claim(**_payload):
            row.refresh_from_db()
            self.assertEqual(row.status, "processing")
            self.assertIsNotNone(row.locked_at)
            return True

        with patch.dict(TASK_REGISTRY, {"test_claim": verify_claim}):
            self.assertEqual(process_outbox(), (1, 0))

        row.refresh_from_db()
        self.assertEqual(row.status, TaskOutbox.STATUS_DONE)
        self.assertIsNone(row.locked_at)
        self.assertEqual(row.attempts, 1)

    def test_expired_claim_is_recovered(self):
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(
            task="test_recovery",
            status=TaskOutbox.STATUS_PROCESSING,
            attempts=1,
            locked_at=timezone.now() - timedelta(minutes=16),
        )
        with patch.dict(TASK_REGISTRY, {"test_recovery": lambda **_payload: True}):
            self.assertEqual(process_outbox(), (1, 0))
        row.refresh_from_db()
        self.assertEqual(row.status, TaskOutbox.STATUS_DONE)
        self.assertEqual(row.attempts, 2)

    def test_expired_lease_at_max_attempts_is_failed_without_delivery(self):
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(
            task="test_max_attempts",
            status=TaskOutbox.STATUS_PROCESSING,
            attempts=5,
            locked_at=timezone.now() - timedelta(minutes=16),
        )
        with patch.dict(TASK_REGISTRY, {"test_max_attempts": lambda **_payload: self.fail("must not run")}):
            self.assertEqual(process_outbox(), (0, 1))
        row.refresh_from_db()
        self.assertEqual(row.status, TaskOutbox.STATUS_FAILED)
        self.assertIsNone(row.locked_at)

    def test_delivery_failure_on_final_attempt_marks_row_failed(self):
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(task="test_final_failure", attempts=4)
        with patch.dict(TASK_REGISTRY, {"test_final_failure": lambda **_payload: False}):
            self.assertEqual(process_outbox(), (0, 1))
        row.refresh_from_db()
        self.assertEqual(row.status, TaskOutbox.STATUS_FAILED)
        self.assertEqual(row.attempts, 5)
        self.assertIsNone(row.locked_at)

    def test_unexpired_lease_is_not_reclaimed(self):
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(
            task="test_active_lease",
            status=TaskOutbox.STATUS_PROCESSING,
            attempts=1,
            locked_at=timezone.now(),
        )
        with patch.dict(TASK_REGISTRY, {"test_active_lease": lambda **_payload: self.fail("must not run")}):
            self.assertEqual(process_outbox(), (0, 0))
        row.refresh_from_db()
        self.assertEqual(row.status, TaskOutbox.STATUS_PROCESSING)

    def test_failure_does_not_persist_exception_text(self):
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(task="test_failure")

        def fail(**_payload):
            raise RuntimeError("private recipient data")

        with patch.dict(TASK_REGISTRY, {"test_failure": fail}):
            self.assertEqual(process_outbox(), (0, 1))
        row.refresh_from_db()
        self.assertEqual(row.status, TaskOutbox.STATUS_PENDING)
        self.assertNotIn("private recipient data", row.last_error)


@override_settings(**TEST_OVERRIDES)
class AlertClaimTests(TestCase):
    def test_sent_alert_window_is_not_sent_twice(self):
        from TrafficApp.services.alert_job import run_gridlock_alerts

        user = User.objects.create_user(username="alert-user", password="longenoughpassword123")
        RouteWatch.objects.create(user=user, origin="Origin", destination="Destination")
        fixed_now = timezone.make_aware(datetime.datetime(2026, 6, 8, 10, 0))
        forecast = {
            "origin": "Origin",
            "destination": "Destination",
            "target_dt": fixed_now + timedelta(minutes=60),
            "congestion": "High",
            "worst_point": None,
            "route": "Origin to Destination",
        }
        with patch("TrafficApp.services.alert_job.timezone.localtime", return_value=fixed_now), \
             patch("TrafficApp.services.alert_job.forecast_gridlock", return_value=forecast), \
             patch("TrafficApp.services.alert_job.notify_user", return_value=1) as notify:
            self.assertEqual(run_gridlock_alerts(), 1)
            self.assertEqual(run_gridlock_alerts(), 0)
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(TrafficAlert.objects.get().status, TrafficAlert.STATUS_SENT)


@skipUnlessDBFeature("has_select_for_update_skip_locked")
class PostgresOutboxClaimConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_worker_skips_a_pending_row_locked_by_another_transaction(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connection, transaction
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(task="locked_claim")
        with patch.dict(TASK_REGISTRY, {"locked_claim": lambda **_payload: self.fail("locked row must be skipped")}):
            with transaction.atomic():
                TaskOutbox.objects.select_for_update().get(pk=row.pk)
                with ThreadPoolExecutor(max_workers=1) as workers:
                    result = workers.submit(process_outbox, 1).result(timeout=5)
                self.assertEqual(result, (0, 0))
        row.refresh_from_db()
        self.assertEqual(row.status, TaskOutbox.STATUS_PENDING)

    def test_two_workers_do_not_run_the_same_live_claim(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event, Lock
        from TrafficApp.services.outbox import process_outbox, TASK_REGISTRY

        row = TaskOutbox.objects.create(task="concurrency_claim")
        started = Event()
        release = Event()
        calls = []
        calls_lock = Lock()

        def blocking_task(**_payload):
            with calls_lock:
                calls.append(1)
            started.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test worker release timed out")
            return True

        with patch.dict(TASK_REGISTRY, {"concurrency_claim": blocking_task}):
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(process_outbox, 1)
                self.assertTrue(started.wait(timeout=5), "first worker did not claim the row")
                second = workers.submit(process_outbox, 1)
                try:
                    self.assertEqual(second.result(timeout=5), (0, 0))
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=10), (1, 0))

        row.refresh_from_db()
        self.assertEqual(len(calls), 1)
        self.assertEqual(row.status, TaskOutbox.STATUS_DONE)


class TrainingInputFingerprintTests(TestCase):
    def test_fingerprint_is_for_the_bytes_parsed(self):
        from TrafficApp.management.commands.train_model import _read_training_csv

        contents = b"route,hour,day_of_week,distance_km,congestion\nA-B,8,1,2.5,Low\n"
        with tempfile.NamedTemporaryFile() as source:
            source.write(contents)
            source.flush()
            frame, fingerprint = _read_training_csv(source.name)
        self.assertEqual(fingerprint, hashlib.sha256(contents).hexdigest())
        self.assertEqual(frame.iloc[0]["route"], "A-B")


class ArtifactManifestTests(TestCase):
    def test_manifest_points_to_complete_matching_release(self):
        from TrafficApp.services.artifact_manifest import (
            promote_artifact_release, resolve_artifact_paths,
        )

        with tempfile.TemporaryDirectory() as tmp:
            candidate_model = os.path.join(tmp, "candidate.pkl")
            candidate_schema = os.path.join(tmp, "candidate.json")
            with open(candidate_model, "wb") as model_file:
                model_file.write(b"model-bytes")
            from traffic_context.ml_features import feature_columns
            with open(candidate_schema, "w", encoding="utf-8") as schema_file:
                json.dump({
                    "version": "release-1",
                    "model_type": "lightgbm-binary",
                    "route_vocab": [],
                    "feature_columns": feature_columns([]),
                }, schema_file)

            with patch("TrafficApp.services.artifact_manifest.joblib.load") as load_model:
                load_model.return_value.feature_name.return_value = feature_columns([])
                release_dir = promote_artifact_release(
                    tmp, candidate_model, candidate_schema, "release-1"
                )
            model_path, schema_path, version = resolve_artifact_paths(tmp)

            self.assertEqual(version, "release-1")
            self.assertEqual(model_path.parent, release_dir)
            self.assertEqual(schema_path.parent, release_dir)
            self.assertTrue(model_path.is_file())
            self.assertTrue(schema_path.is_file())

    def test_schema_version_mismatch_is_rejected_before_release_creation(self):
        from TrafficApp.services.artifact_manifest import promote_artifact_release
        from traffic_context.ml_features import feature_columns

        with tempfile.TemporaryDirectory() as tmp:
            model = os.path.join(tmp, "candidate.pkl")
            schema = os.path.join(tmp, "candidate.json")
            Path(model).write_bytes(b"model")
            Path(schema).write_text(json.dumps({
                "version": "old-version",
                "model_type": "lightgbm-binary",
                "route_vocab": [],
                "feature_columns": feature_columns([]),
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version"):
                promote_artifact_release(tmp, model, schema, "new-version")
            self.assertFalse((Path(tmp) / "ml_artifacts").exists())

    def test_manifest_write_failure_preserves_active_release(self):
        from TrafficApp.services.artifact_manifest import promote_artifact_release, resolve_artifact_paths
        from traffic_context.ml_features import feature_columns
        from unittest.mock import patch
        import TrafficApp.services.artifact_manifest as artifacts

        with tempfile.TemporaryDirectory() as tmp:
            def create_candidate(version, contents):
                model = Path(tmp) / f"{version}.pkl"
                schema = Path(tmp) / f"{version}.json"
                model.write_bytes(contents)
                schema.write_text(json.dumps({
                    "version": version,
                    "model_type": "lightgbm-binary",
                    "route_vocab": [],
                    "feature_columns": feature_columns([]),
                }), encoding="utf-8")
                return model, schema

            first_model, first_schema = create_candidate("release-1", b"old-model")
            with patch("TrafficApp.services.artifact_manifest.joblib.load") as load_model:
                load_model.return_value.feature_name.return_value = feature_columns([])
                promote_artifact_release(tmp, first_model, first_schema, "release-1")
            second_model, second_schema = create_candidate("release-2", b"new-model")
            original_replace = artifacts.os.replace

            def fail_manifest_replace(source, destination):
                if Path(destination).name == "current.json":
                    raise OSError("simulated manifest replacement failure")
                return original_replace(source, destination)

            with patch("TrafficApp.services.artifact_manifest.joblib.load") as load_model:
                load_model.return_value.feature_name.return_value = feature_columns([])
                with patch("TrafficApp.services.artifact_manifest.os.replace", side_effect=fail_manifest_replace):
                    with self.assertRaisesRegex(OSError, "simulated"):
                        promote_artifact_release(tmp, second_model, second_schema, "release-2")

            model_path, schema_path, active_version = resolve_artifact_paths(tmp)
            self.assertEqual(active_version, "release-1")
            self.assertEqual(model_path.read_bytes(), b"old-model")
            self.assertEqual(json.loads(schema_path.read_text(encoding="utf-8"))["version"], "release-1")

    def test_model_feature_mismatch_is_rejected_before_release_creation(self):
        from TrafficApp.services.artifact_manifest import promote_artifact_release
        from traffic_context.ml_features import feature_columns

        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "candidate.pkl"
            schema = Path(tmp) / "candidate.json"
            model.write_bytes(b"serialized-model")
            schema.write_text(json.dumps({
                "version": "release-1",
                "model_type": "lightgbm-binary",
                "route_vocab": [],
                "feature_columns": feature_columns([]),
            }), encoding="utf-8")
            with patch("TrafficApp.services.artifact_manifest.joblib.load") as load_model:
                load_model.return_value.feature_name.return_value = ["wrong_feature"]
                with self.assertRaisesRegex(ValueError, "model features"):
                    promote_artifact_release(tmp, model, schema, "release-1")
            self.assertFalse((Path(tmp) / "ml_artifacts").exists())

    def test_manifest_rejects_path_traversal(self):
        from TrafficApp.services.artifact_manifest import resolve_artifact_paths

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = os.path.join(tmp, "ml_artifacts")
            os.makedirs(artifact_dir)
            with open(os.path.join(artifact_dir, "current.json"), "w", encoding="utf-8") as manifest:
                manifest.write('{"version": "..", "artifact_dir": "releases/.."}')
            with self.assertRaises(ValueError):
                resolve_artifact_paths(tmp)
