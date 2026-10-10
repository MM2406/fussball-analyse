import json
import os
import unittest
from datetime import datetime, timedelta, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from analysis_api import AnalysisClient
from football_api import FootballAPIError, FootballClient
from logic import (VIENNA, build_context, make_request, now_vienna, parse_matches,
                   render_response, safe_url, upcoming_fixtures, validate_upcoming)

ROOT = Path(__file__).resolve().parents[1]


def fixture(identifier=1, kickoff=None, status="NS", league=78, season=2026):
    kickoff = kickoff or (now_vienna() + timedelta(days=1))
    return {"fixture": {"id": identifier, "date": kickoff.isoformat(), "status": {"short": status}},
            "league": {"id": league, "name": "Testliga", "country": "Deutschland", "season": season},
            "teams": {"home": {"id": 10, "name": "Heim"}, "away": {"id": 20, "name": "Gast"}},
            "goals": {"home": 2, "away": 1}, "score": {"fulltime": {"home": 2, "away": 1}}}


class FakeHTTP:
    def __init__(self, router, status=200):
        self.router, self.status, self.calls = router, status, []

    def get(self, url, params, headers, timeout):
        self.calls.append((url.split(".io")[-1], params))
        data = self.router(url.split(".io")[-1], params)
        return SimpleNamespace(status_code=self.status, json=lambda: data, raise_for_status=lambda: None)


class LogicTests(unittest.TestCase):
    def test_parse_hyphens_unicode_and_per_match_time(self):
        games = parse_matches("Paris Saint-Germain - Gast | 18:30\nHeim – Anderer Gast", now_vienna().date(), time(20))
        self.assertEqual(games[0]["home"], "Paris Saint-Germain")
        self.assertEqual(datetime.fromisoformat(games[0]["kickoff"]).hour, 18)
        self.assertEqual(datetime.fromisoformat(games[1]["kickoff"]).hour, 20)

    def test_bad_rows_duplicate_and_invalid_time_rejected(self):
        for raw in ("Nur eine Mannschaft", "Heim - Heim", "Heim - Gast | 25:00", "Heim - Gast\nHeim - Gast", "Heim - Gast | 12:00 | Zusatz"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_matches(raw, now_vienna().date(), time(12))

    def test_old_and_started_fixtures_excluded(self):
        current = now_vienna()
        items = [fixture(1), fixture(2, current - timedelta(minutes=1)), fixture(3, status="1H"), fixture(4, status="PST")]
        self.assertEqual([m["fixture_id"] for m in upcoming_fixtures(items, current)], [1])
        with self.assertRaises(ValueError):
            validate_upcoming([{ "home": "Heim", "away": "Gast", "kickoff": current.isoformat()}], current)

    def test_context_does_not_include_credentials(self):
        game = upcoming_fixtures([fixture()])[0]
        game["api_key"] = "do-not-send-secret"
        context = build_context([game], quotes="Heimsieg 2,0")
        text = make_request("Mein Prompt", context)
        self.assertNotIn("do-not-send-secret", text)
        self.assertIn("Mein Prompt", text)
        self.assertIn("Heimsieg 2,0", text)
        self.assertIn("Europe/Vienna", text)

    def test_web_citations_become_links_with_deduplicated_sources(self):
        response = {"output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Befund [1].", "annotations": [
                {"type": "url_citation", "start_index": 7, "end_index": 10, "url": "https://example.org/info"},
                {"type": "url_citation", "start_index": -1, "end_index": 2, "url": "javascript:bad"}]}]},
            {"type": "web_search_call", "action": {"sources": [{"url": "https://example.org/info"}, {"url": "https://example.net/other"}]}}]}
        body, sources = render_response(response)
        self.assertEqual(body, "Befund [Quelle 1](<https://example.org/info>).")
        self.assertEqual(len(sources), 2)
        self.assertIsNone(safe_url("javascript:alert(1)"))
        self.assertIsNone(safe_url('https://example.org/\"bad'))


class FootballTests(unittest.TestCase):
    def test_quota_stops_subsequent_requests(self):
        http = FakeHTTP(lambda _e, _p: {"errors": {}, "response": []}, status=429)
        client = FootballClient("secret", http)
        with self.assertRaises(FootballAPIError):
            client.fixtures(now_vienna().date())
        with self.assertRaises(FootballAPIError):
            client.get("/leagues", id=78)
        self.assertEqual(len(http.calls), 1)

    def test_coverage_controls_endpoints_and_history_keeps_competitions(self):
        def router(endpoint, params):
            if endpoint == "/leagues":
                result = [{"seasons": [{"year": 2026, "coverage": {"fixtures": {"statistics": False, "lineups": False}, "injuries": False}}]}]
            elif endpoint == "/teams/statistics":
                result = {"fixtures": {"played": {"total": 5}}, "goals": {"for": {"total": {"total": 9}}}}
            elif endpoint == "/fixtures":
                result = [fixture(88, now_vienna() - timedelta(days=2), "FT", league=100),
                          fixture(89, now_vienna() - timedelta(days=5), "FT"),
                          fixture(90, now_vienna() + timedelta(days=4), "NS")]
            else:
                self.fail("Endpoint ohne Abdeckung aufgerufen: " + endpoint)
            return {"errors": {}, "response": result}
        http = FakeHTTP(router)
        client = FootballClient("secret", http)
        data = client.enrich(upcoming_fixtures([fixture()]))
        history = data["spiele"][0]["teams"][0]["letzte_spiele"]
        self.assertEqual([i["fixture"]["id"] for i in history], [88, 89])
        self.assertEqual(history[0]["league"]["id"], 100)
        self.assertIn("nicht verfügbar", data["spiele"][0]["aufstellungs_hinweis"])
        self.assertNotIn("secret", json.dumps(data))

    def test_unknown_season_coverage_is_not_borrowed(self):
        http = FakeHTTP(lambda endpoint, params: {"errors": {}, "response":
                          [{"seasons": [{"year": 2025, "coverage": {"injuries": True}}]}] if endpoint == "/leagues" else []})
        data = FootballClient("secret", http).enrich(upcoming_fixtures([fixture()]))
        self.assertEqual(data["spiele"][0]["coverage"], {})
        self.assertTrue(data["luecken"])
        self.assertFalse(any(endpoint == "/injuries" for endpoint, _ in http.calls))

    def test_request_cap_marks_incomplete_data(self):
        http = FakeHTTP(lambda endpoint, params: {"errors": {}, "response": []})
        data = FootballClient("secret", http, max_requests=1).enrich(upcoming_fixtures([fixture()]))
        self.assertEqual(len(http.calls), 1)
        self.assertTrue(data["luecken"])


class AnalysisTests(unittest.TestCase):
    def test_start_requires_search_and_preserves_full_prompt(self):
        calls = []
        fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or {"id": "response-test", "status": "queued"}))
        client = AnalysisClient("secret", client=fake)
        context = build_context(upcoming_fixtures([fixture()]))
        prompt = (ROOT / "prompt.md").read_text(encoding="utf-8")
        response = client.start(prompt, context)
        self.assertEqual(response["status"], "queued")
        self.assertTrue(calls[0]["background"])
        self.assertEqual(calls[0]["tools"], [{"type": "web_search"}])
        self.assertEqual(calls[0]["tool_choice"], "required")
        self.assertTrue(calls[0]["instructions"].startswith(prompt))
        self.assertNotIn("secret", calls[0]["input"])

    def test_started_match_prevents_paid_start(self):
        calls = []
        fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs)))
        context = build_context([{"home": "Heim", "away": "Gast", "kickoff": (now_vienna() - timedelta(seconds=1)).isoformat()}])
        with self.assertRaises(ValueError):
            AnalysisClient("secret", client=fake).start("Prompt", context)
        self.assertFalse(calls)


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"APP_PASSWORD": "", "API_FOOTBALL_KEY": "", "OPENAI_API_KEY": "", "OPENAI_MODEL": "gpt-5.4"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_offline_interface_and_request_creation(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
        self.assertFalse(app.exception)
        self.assertTrue(next(b for b in app.button if b.label == "KI-Analyse starten (API-Kosten)").disabled)
        app.date_input[0].set_value(now_vienna().date() + timedelta(days=1))
        app.text_area(key="manual_matches").set_value("Heim - Gast | 15:30")
        next(b for b in app.button if b.label == "Analyseauftrag erstellen").click()
        app.run()
        self.assertFalse(app.exception)
        self.assertIn("Heim", app.session_state["generated_request"])
        self.assertTrue(app.success)

    def test_api_keys_without_password_are_disabled(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-not-used", "API_FOOTBALL_KEY": "fake-not-used"}):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.warning)
            self.assertTrue(next(b for b in app.button if b.label == "KI-Analyse starten (API-Kosten)").disabled)

    def test_access_code_gates_api_and_unlocks(self):
        with patch.dict(os.environ, {"APP_PASSWORD": "test-pass", "OPENAI_API_KEY": "fake-not-used"}):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.date_input)
            app.text_input(key="login_password").set_value("wrong")
            app.button[0].click().run()
            self.assertTrue(app.error)
            app.text_input(key="login_password").set_value("test-pass")
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.date_input)
            self.assertFalse(next(b for b in app.button if b.label == "KI-Analyse starten (API-Kosten)").disabled)

    def test_direct_analysis_flow_with_mocked_api_and_citations(self):
        calls = []
        class FakeAnalysis:
            def __init__(self, *args, **kwargs):
                pass
            def start(self, prompt, context):
                calls.append(context)
                return {"id": "response-test", "status": "queued"}
            def retrieve(self, response_id):
                return {"id": response_id, "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Befund [1].", "annotations": [{"type": "url_citation", "start_index": 7, "end_index": 10, "url": "https://example.org/info"}]}]}]}
        with patch.dict(os.environ, {"APP_PASSWORD": "test-pass", "OPENAI_API_KEY": "fake-not-used"}), patch("analysis_api.AnalysisClient", FakeAnalysis):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
            app.text_input(key="login_password").set_value("test-pass")
            app.button[0].click().run()
            app.date_input[0].set_value(now_vienna().date() + timedelta(days=1))
            app.text_area(key="manual_matches").set_value("Heim - Gast | 15:30")
            next(b for b in app.button if b.label == "KI-Analyse starten (API-Kosten)").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(calls), 1)
            self.assertEqual(app.session_state["analysis_job"]["response"]["status"], "completed")
            self.assertTrue(any("[Quelle 1](<https://example.org/info>)" in m.value for m in app.markdown))

    def test_automatic_selection_with_mocked_fixture_provider(self):
        class FakeFootball:
            def __init__(self, *args, **kwargs):
                pass
            def fixtures(self, day):
                return [fixture()]
        with patch.dict(os.environ, {"APP_PASSWORD": "test-pass", "API_FOOTBALL_KEY": "fake-not-used"}), patch("football_api.FootballClient", FakeFootball):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
            app.text_input(key="login_password").set_value("test-pass")
            app.button[0].click().run()
            app.date_input[0].set_value(now_vienna().date() + timedelta(days=1))
            app.radio[0].set_value("Spiele automatisch laden").run()
            next(b for b in app.button if b.label == "Spiele laden").click().run()
            app.multiselect(key="selected_fixtures").set_value([1])
            next(b for b in app.button if b.label == "Analyseauftrag erstellen").click().run()
            self.assertFalse(app.exception)
            self.assertIn('"fixture_id": 1', app.session_state["generated_request"])


if __name__ == "__main__":
    unittest.main()
