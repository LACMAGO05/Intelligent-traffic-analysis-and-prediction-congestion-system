"""
Test suite covering the Phase 1 critical-security fixes.

Run with a throwaway SQLite database so it does not require the production
Postgres instance, e.g.:

    DATABASE_URL="sqlite:///test_db.sqlite3" python manage.py test
"""
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.conf import settings
from django.core.management import call_command
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth.models import User, Group

from TrafficApp.utils import generate_otp
from TrafficApp.views import sanitize_location
from TrafficApp.models import ChatThread, PredictionLog, TrafficRecord
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

    @patch("TrafficApp.views.send_welcome_email", return_value=True)
    @patch("TrafficApp.views.generate_otp", return_value="123456")
    @patch("TrafficApp.views.send_verification_email", return_value=True)
    def test_full_signup_then_verify_creates_user_with_role(self, m_send, m_otp, m_welcome):
        self.client.post(reverse("signup"), {
            "username": "dave", "email": "dave@example.com",
            "password": "longenoughpassword123", "consent": "yes",
        })
        resp = self.client.post(reverse("otp"), {"otp": "123456"})
        self.assertRedirects(resp, reverse("signin"), fetch_redirect_response=False)
        user = User.objects.get(username="dave")
        self.assertTrue(user.groups.filter(name="Commuter").exists())
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
