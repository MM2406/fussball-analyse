from __future__ import annotations

import hmac
import os
from datetime import timedelta
from pathlib import Path

import streamlit as st

from analysis_api import AnalysisClient, AnalysisError
from football_api import FootballClient, FootballAPIError
from logic import (as_datetime, build_context, make_request, match_label, now_vienna,
                   parse_matches, password_digest, render_response, upcoming_fixtures,
                   validate_upcoming)

st.set_page_config(page_title="Fußball-Analyse", page_icon="⚽", layout="wide")


def setting(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        try:
            value = st.secrets.get(name, default)
        except (FileNotFoundError, KeyError):
            value = default
    value = str(value).strip() if value is not None else default
    if name in {"APP_PASSWORD", "API_FOOTBALL_KEY", "OPENAI_API_KEY"} and value.startswith(("HIER_", "DEIN_")):
        return ""
    return value


password = setting("APP_PASSWORD")
football_key = setting("API_FOOTBALL_KEY")
openai_key = setting("OPENAI_API_KEY")
model = setting("OPENAI_MODEL", "gpt-5.4")
apis_enabled = bool(password)

st.title("⚽ Fußball-Analyse")
st.caption("Spiele auswählen · Fakten prüfen · sinnvolle Auswahlen und Kombis erstellen")

if password:
    digest = password_digest(password)
    if not hmac.compare_digest(str(st.session_state.get("authenticated", "")), digest):
        st.write("Gib deinen Zugangscode ein, um die App zu öffnen.")
        with st.form("login", clear_on_submit=True):
            entered = st.text_input("Zugangscode", type="password", key="login_password")
            unlock = st.form_submit_button("App öffnen")
        if unlock:
            if hmac.compare_digest(password_digest(entered), digest):
                st.session_state.authenticated = digest
                st.rerun()
            else:
                st.error("Der Zugangscode stimmt nicht.")
        st.stop()
    with st.sidebar:
        if st.button("Abmelden"):
            st.session_state.clear()
            st.rerun()

if (football_key or openai_key) and not apis_enabled:
    st.warning("API-Funktionen sind gesperrt: Lege unter Streamlit → Settings → Secrets zuerst APP_PASSWORD fest. Die manuelle Eingabe und der Analyseauftrag bleiben verfügbar.")

with st.sidebar:
    st.subheader("Verbindungen")
    st.write("Spielabruf: " + ("bereit" if football_key and apis_enabled else "noch nicht eingerichtet"))
    st.write("KI-Analyse: " + ("bereit" if openai_key and apis_enabled else "noch nicht eingerichtet"))
    st.caption("Ohne API-Zugänge kannst du den Analyseauftrag erzeugen und in ChatGPT einfügen.")
    st.markdown("[Streamlit-Anleitung](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)")

current = now_vienna()
day = st.date_input("Spieltag", value=current.date(), format="DD.MM.YYYY", key="match_day")
mode = st.radio("Wie möchtest du die Spiele auswählen?", ["Selbst eingeben", "Spiele automatisch laden"], horizontal=True)
matches: list[dict] = []
manual_text = ""
default_time = (current + timedelta(hours=1)).time().replace(second=0, microsecond=0, tzinfo=None)
competition = ""

if mode == "Selbst eingeben":
    left, right = st.columns(2)
    with left:
        shared_time = st.time_input("Anstoßzeit, falls keine Uhrzeit pro Zeile angegeben ist", value=default_time)
    with right:
        competition = st.text_input("Liga / Wettbewerb (optional)", placeholder="Bei verschiedenen Ligen leer lassen")
    manual_text = st.text_area(
        "Spiele – eine Partie pro Zeile", height=150, key="manual_matches",
        placeholder="Heimmannschaft - Auswärtsmannschaft | 15:30\nAndere Heimmannschaft - Andere Auswärtsmannschaft | 18:00",
        help="Datum gilt für alle Partien. Uhrzeiten in Wien/Berlin. Die Mannschaftsnamen werden anhand der Recherche geprüft.",
    )
else:
    st.caption("API-Football liefert Partien für das gewählte Datum. Es werden nur noch nicht gestartete Spiele mit bestätigter Uhrzeit angeboten.")
    if not football_key:
        st.info("Für diese Funktion API_FOOTBALL_KEY in den Streamlit-Secrets hinterlegen. Du kannst inzwischen Spiele selbst eingeben.")
    if st.button("Spiele laden", disabled=not (football_key and apis_enabled)):
        try:
            with st.spinner("Spielplan laden …"):
                items = FootballClient(football_key).fixtures(day)
            st.session_state.fixture_list = upcoming_fixtures(items)
            st.session_state.fixture_day = day.isoformat()
            st.session_state.fixture_loaded = now_vienna().strftime("%H:%M")
            st.session_state.pop("selected_fixtures", None)
        except FootballAPIError as exc:
            st.error(str(exc))
    available = st.session_state.get("fixture_list", []) if st.session_state.get("fixture_day") == day.isoformat() else []
    if available:
        available = [m for m in available if as_datetime(m["kickoff"]) > now_vienna()]
        countries = sorted({m["country"] for m in available})
        chosen_countries = st.multiselect("Länder filtern (leer = alle)", countries)
        filtered = [m for m in available if not chosen_countries or m["country"] in chosen_countries]
        leagues = sorted({f"{m['country']} · {m['competition']}" for m in filtered})
        chosen_leagues = st.multiselect("Wettbewerbe filtern (leer = alle)", leagues)
        filtered = [m for m in filtered if not chosen_leagues or f"{m['country']} · {m['competition']}" in chosen_leagues]
        by_id = {m["fixture_id"]: m for m in filtered}
        # Bei Filteränderung keine unsichtbaren alten Partien weiterverwenden.
        if "selected_fixtures" in st.session_state:
            st.session_state.selected_fixtures = [i for i in st.session_state.selected_fixtures if i in by_id]
        chosen = st.multiselect("Partien für die Analyse", list(by_id), format_func=lambda i: match_label(by_id[i]), key="selected_fixtures")
        matches = [by_id[i] for i in chosen]
        st.caption(f"{len(available)} anstehende Partien verfügbar. Spielplan abgerufen um {st.session_state.get('fixture_loaded', '')} Uhr.")
    elif st.session_state.get("fixture_day") == day.isoformat():
        st.info("Keine anstehenden Partien geliefert. Abdeckung und Saisonzugriff hängen vom API-Football-Tarif ab; bei Bedarf manuell eingeben.")

with st.expander("Quoten und eigene Hinweise hinzufügen (optional)"):
    bookmaker = st.text_input("Wettanbieter", placeholder="Optional")
    quotes = st.text_area("Tatsächlich angebotene Quoten", height=120,
                          placeholder="Spiel | Markt | Quote | Uhrzeit des Quotenstands\nBei Bet Builder: die angezeigte gemeinsame Quote angeben.")
    notes = st.text_area("Zusätzliche Hinweise", placeholder="Zum Beispiel gewünschte Märkte oder bekannte Besonderheiten")

original_prompt = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
with st.expander("Vollständigen Analyse-Prompt ansehen oder für diesen Auftrag anpassen"):
    prompt = st.text_area("Analyse-Prompt", value=original_prompt, height=320, key="analysis_prompt")
    st.caption("Änderungen hier gelten für deine aktuelle Sitzung. Für eine dauerhafte Änderung prompt.md in GitHub bearbeiten.")

details = st.checkbox("Verfügbare Statistiken der letzten Ligaspiele zusätzlich abrufen", value=True,
                      disabled=not (football_key and apis_enabled and mode == "Spiele automatisch laden"),
                      help="Nur bei direkter KI-Analyse und automatisch gewählten Partien. Kann zusätzliche API-Football-Anfragen verbrauchen; Abdeckung variiert.")
job = st.session_state.get("analysis_job")
pending = bool(job and job.get("response", {}).get("status") in ("queued", "in_progress"))
first, second = st.columns(2)
with first:
    generate = st.button("Analyseauftrag erstellen", type="primary", use_container_width=True)
with second:
    analyze = st.button("KI-Analyse starten (API-Kosten)", use_container_width=True,
                        disabled=not (openai_key and apis_enabled) or pending)
st.caption("2er-, 3er-, 4er- und weitere Kombis entstehen nur, wenn die Analyse sie trägt. Fehlende Quoten verhindern den sportlichen Entwurf nicht. Größere Kombis erhöhen die Auszahlung und senken die Trefferchance.")

if generate or analyze:
    try:
        if mode == "Selbst eingeben":
            matches = parse_matches(manual_text, day, shared_time, competition)
        validate_upcoming(matches)
        if not prompt.strip():
            raise ValueError("Bitte den Analyse-Prompt ausfüllen.")
        context = build_context(matches, quotes, bookmaker, notes)
        if generate:
            st.session_state.generated_request = make_request(prompt, context)
            st.session_state.request_games = len(matches)
        if analyze:
            evidence = None
            if football_key and mode == "Spiele automatisch laden":
                with st.spinner("Verfügbare Fakten abrufen …"):
                    evidence = FootballClient(football_key).enrich(matches, details)
            # Anstoßzeiten nach dem Datenabruf erneut prüfen.
            validate_upcoming(matches)
            context = build_context(matches, quotes, bookmaker, notes, evidence)
            with st.spinner("Recherche-Auftrag starten …"):
                response = AnalysisClient(openai_key, model).start(prompt, context)
            st.session_state.analysis_job = {"response": response, "context": context, "model": model, "started": now_vienna().isoformat()}
            st.session_state.generated_request = make_request(prompt, context)
            st.session_state.request_games = len(matches)
            st.rerun()
    except (ValueError, FootballAPIError, AnalysisError) as exc:
        st.error(str(exc))

if st.session_state.get("generated_request"):
    st.success(f"Analyseauftrag für {st.session_state.get('request_games', 0)} Spiel(e) erstellt.")
    st.download_button("Analyseauftrag herunterladen", st.session_state.generated_request,
                       file_name="Fussball_Analyseauftrag.md", mime="text/markdown")
    with st.expander("Auftrag kopieren und hier in ChatGPT einfügen"):
        st.text_area("Fertiger Auftrag", st.session_state.generated_request, height=350, disabled=False)
    st.caption("Der erzeugte Auftrag ist noch keine Analyse. In ChatGPT einfügen oder die direkte KI-Analyse mit API-Zugang starten.")


@st.fragment(run_every="5s" if pending else None)
def analysis_result():
    stored = st.session_state.get("analysis_job")
    if not stored:
        return
    response = stored["response"]
    status = response.get("status", "unknown")
    if status in ("queued", "in_progress"):
        st.info("Die KI recherchiert und erstellt die Analyse. Dieses Fenster geöffnet lassen; der Status wird automatisch aktualisiert.")
        try:
            if st.button("Laufende Analyse abbrechen", key="cancel_analysis"):
                stored["response"] = AnalysisClient(openai_key, stored["model"]).cancel(response["id"])
                st.rerun()
            refreshed = AnalysisClient(openai_key, stored["model"]).retrieve(response["id"])
            stored["response"] = refreshed
            if refreshed.get("status") not in ("queued", "in_progress"):
                st.rerun()
        except AnalysisError as exc:
            st.warning(str(exc))
        return
    if status == "cancelled":
        st.info("Analyse abgebrochen. Bereits verbrauchte API-Leistungen können Kosten verursachen.")
        return
    if status not in ("completed", "incomplete"):
        st.error("Die Analyse konnte nicht abgeschlossen werden. Modellzugriff, Kontingent und API-Status prüfen.")
        return
    st.subheader("Analyse")
    if status == "incomplete":
        reason = (response.get("incomplete_details") or {}).get("reason", "unbekannt")
        st.warning(f"Diese Ausgabe ist unvollständig ({reason}). Keine vollständig geprüfte Kombi-Auswertung.")
    late = [m for m in stored["context"]["spiele"] if as_datetime(m["kickoff"]) <= now_vienna()]
    if late:
        st.warning("Mindestens eine Partie hat inzwischen begonnen. Der Bericht ist für diese Partie keine aktuelle Pre-Match-Empfehlung. Kombis mit solchen Partien nicht als anstehende Auswahl verwenden.")
    body, sources = render_response(response)
    if not body:
        st.warning("Keine lesbare Analyse zurückgegeben. Quellen und API-Status prüfen.")
        return
    st.markdown(body)
    if sources:
        with st.expander("Quellen aus der Recherche"):
            for index, url in enumerate(sources, 1):
                st.markdown(f"[Quelle {index}](<{url}>)")
    else:
        st.warning("Die API-Ausgabe enthält keine Quellenverweise. Aussagen vor einer Auswahl unabhängig prüfen.")
    header = f"# Fußball-Analyse\n\nAuftrag gestartet: {stored['started']} (Europe/Vienna)\n\nStatus: {status}\n\n"
    if late:
        header += "**Hinweis: Mindestens eine Partie hat inzwischen begonnen. Keine aktuelle Pre-Match-Auswertung für diese Partie.**\n\n"
    if status == "incomplete":
        header += "**Unvollständige Ausgabe.**\n\n"
    source_list = "\n\n## Recherchequellen\n\n" + "\n".join(f"- [Quelle {i}](<{url}>)" for i, url in enumerate(sources, 1)) if sources else ""
    st.download_button("Analyse herunterladen", header + body + source_list,
                       file_name="Fussball_Analyse.md", mime="text/markdown", key="download_report")
    with st.expander("Datenstand und Abruflücken"):
        st.write("Modell: " + stored["model"])
        st.json(stored["context"]["daten"])


analysis_result()
