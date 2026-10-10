"""API-Football: Fakten abrufen, Abdeckung und Lücken offen ausweisen."""
from __future__ import annotations

from datetime import date
import requests

from logic import as_datetime, now_vienna


class FootballAPIError(RuntimeError):
    pass


class FootballClient:
    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str, session=None, max_requests: int = 80):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.max_requests = max_requests
        self.requests_used = 0
        self.cache: dict = {}
        self.exhausted = False

    def get(self, endpoint: str, **params):
        cache_key = (endpoint, tuple(sorted(params.items())))
        if cache_key in self.cache:
            return self.cache[cache_key]
        if self.exhausted or self.requests_used >= self.max_requests:
            self.exhausted = True
            raise FootballAPIError("Abruflimit erreicht. Verbleibende Daten fehlen; Tarif und Kontingent prüfen.")
        self.requests_used += 1
        try:
            response = self.session.get(self.BASE_URL + endpoint, params=params,
                                        headers={"x-apisports-key": self.api_key}, timeout=15)
            if response.status_code in (401, 403):
                self.exhausted = True
                raise FootballAPIError("API-Football-Zugang oder Tarif erlaubt diesen Abruf nicht.")
            if response.status_code == 429:
                self.exhausted = True
                raise FootballAPIError("API-Football-Kontingent oder Anfragelimit erreicht.")
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            raise FootballAPIError("API-Football ist momentan nicht erreichbar. Später erneut versuchen.") from None
        except (ValueError, TypeError):
            raise FootballAPIError("API-Football lieferte keine lesbare Antwort.") from None
        if not isinstance(data, dict):
            raise FootballAPIError("API-Football lieferte ein unerwartetes Antwortformat.")
        errors = data.get("errors")
        if errors:
            error_text = str(errors).lower()
            if any(word in error_text for word in ("limit", "rate", "quota", "plan", "token", "key", "subscription", "access")):
                self.exhausted = True
            raise FootballAPIError("API-Football meldet einen Abruffehler. Kontingent, Schlüssel und Saisonfreigabe im Anbieter-Dashboard prüfen.")
        result = data.get("response", [])
        self.cache[cache_key] = result
        return result

    def fixtures(self, day: date) -> list[dict]:
        result = self.get("/fixtures", date=day.isoformat(), timezone="Europe/Vienna")
        if not isinstance(result, list):
            raise FootballAPIError("Die Spiel-Liste hat ein unerwartetes Format.")
        return result

    def enrich(self, matches: list[dict], detail_statistics: bool = True) -> dict:
        collected = {"quelle": "API-Football / API-Sports", "abrufzeit": now_vienna().isoformat(),
                     "hinweis": "API-Abdeckung ist je Wettbewerb, Saison und Tarif unterschiedlich. Leere Antworten bestätigen keine vollständige Datenlage.",
                     "spiele": [], "luecken": []}

        def fetch(endpoint: str, **params):
            if self.exhausted:
                return None
            try:
                return self.get(endpoint, **params)
            except FootballAPIError as exc:
                collected["luecken"].append({"endpoint": endpoint, "parameter": params, "grund": str(exc)})
                return None

        for match in matches:
            if not match.get("fixture_id"):
                collected["luecken"].append({"spiel": f"{match['home']} – {match['away']}", "grund": "Manuelle Partie ohne verifizierte API-Spielkennung; Webrecherche verwenden."})
                continue
            league, season, fixture = match["league_id"], match["season"], match["fixture_id"]
            bundle = {"fixture_id": fixture, "home": match["home"], "away": match["away"], "teams": [], "coverage": {}}
            league_data = fetch("/leagues", id=league, season=season)
            if isinstance(league_data, list):
                for entry in league_data:
                    for listed_season in entry.get("seasons", []):
                        if listed_season.get("year") == season:
                            bundle["coverage"] = listed_season.get("coverage") or {}
            coverage = bundle["coverage"]
            if not coverage:
                collected["luecken"].append({"fixture_id": fixture, "grund": "Keine bestätigte Datenabdeckung für diese Saison verfügbar."})

            for side in ("home", "away"):
                team_id = match[side + "_id"]
                team = {"id": team_id, "name": match[side]}
                summary = fetch("/teams/statistics", league=league, season=season, team=team_id, date=now_vienna().date().isoformat())
                if isinstance(summary, dict) and summary.get("fixtures"):
                    team["saisonstatistik"] = {key: summary[key] for key in ("fixtures", "goals", "clean_sheet", "failed_to_score", "penalty") if key in summary}
                else:
                    team["saisonstatistik"] = {"hinweis": "Nicht verfügbar"}
                recent = fetch("/fixtures", team=team_id, last=10, timezone="Europe/Vienna")
                history = []
                for old in recent if isinstance(recent, list) else []:
                    try:
                        if old["fixture"]["status"]["short"] not in ("FT", "AET", "PEN") or as_datetime(old["fixture"]["date"]) >= as_datetime(match["kickoff"]):
                            continue
                        history.append({"fixture": old["fixture"], "league": old["league"],
                                        "teams": old["teams"], "goals": old.get("goals"), "score": old.get("score")})
                    except (KeyError, TypeError, ValueError):
                        continue
                history.sort(key=lambda item: item["fixture"]["date"], reverse=True)
                team["letzte_spiele"] = history[:10]
                team["stichproben_hinweis"] = "Bis zu zehn zuletzt beendete Spiele aus verschiedenen Wettbewerben. Liga, Saison und Testspiele anhand der Metadaten getrennt auswerten; keine vollständigen letzten zehn Ligaspiele zugesichert."
                if detail_statistics and (coverage.get("fixtures") or {}).get("statistics"):
                    stats = []
                    same_league = [old for old in history if old["league"].get("id") == league and old["league"].get("season") == season]
                    for old in same_league[:5]:
                        values = fetch("/fixtures/statistics", fixture=old["fixture"]["id"])
                        if isinstance(values, list) and values:
                            stats.append({"fixture_id": old["fixture"]["id"], "date": old["fixture"]["date"], "statistics": values})
                    team["spielstatistiken"] = stats
                    team["statistik_hinweis"] = "xG/Schüsse nur aus tatsächlich gelieferten Feldern verwenden; fehlende Werte nicht ersetzen."
                bundle["teams"].append(team)

            if (coverage.get("fixtures") or {}).get("lineups"):
                bundle["aufstellungen"] = fetch("/fixtures/lineups", fixture=fixture)
                bundle["aufstellungs_hinweis"] = "Leer bedeutet: zum Abrufzeitpunkt keine Aufstellung geliefert."
            else:
                bundle["aufstellungs_hinweis"] = "Aufstellungen laut Abdeckung nicht verfügbar oder Abdeckung unbekannt."
            if coverage.get("injuries"):
                bundle["ausfaelle"] = fetch("/injuries", fixture=fixture)
                bundle["ausfall_hinweis"] = "Leere Daten bestätigen nicht, dass alle Spieler einsatzfähig sind; Vereinsquellen prüfen."
            else:
                bundle["ausfall_hinweis"] = "Ausfalldaten nicht abgedeckt oder Abdeckung unbekannt; Vereinsquellen prüfen."
            collected["spiele"].append(bundle)
        collected["anfragen"] = self.requests_used
        if self.exhausted:
            collected["luecken"].append({"grund": "Weitere API-Abrufe wurden nach einem Limit/Zugangsfehler gestoppt; verbleibende Felder sind unvollständig."})
        return collected
