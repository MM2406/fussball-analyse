# Fußball-Analyse mit Streamlit

Eine deutsche Eingabemaske mit dem vollständigen Fußball-Prompt. Manuelle Eingabe funktioniert ohne API-Zugang. Optional: Spielplan und verfügbare Fakten von API-Football sowie eine direkte KI-Analyse mit aktueller OpenAI-Webrecherche.

## Jetzt starten: GitHub und Streamlit

1. ZIP herunterladen und **entpacken**.
2. Bei [GitHub](https://github.com/new) ein Repository namens **fussball-analyse** erstellen. Für den einfachen Einstieg **Public** wählen und „Add a README file“ aktivieren. **Create repository** anklicken.
3. Im neuen Repository **Add file → Upload files** öffnen. Den **Inhalt** des entpackten Ordners hochladen, einschließlich des Ordners `tests`. Die ZIP-Datei selbst nicht hochladen. Vorhandene README.md bei Bedarf ersetzen. **Commit changes** bestätigen.
4. Prüfen, dass `app.py`, `logic.py`, `analysis_api.py`, `football_api.py`, `prompt.md` und `requirements.txt` direkt auf der obersten Ebene im Repository liegen. Keine zusätzliche Ordner-Ebene dazwischen.
5. In [Streamlit Community Cloud](https://share.streamlit.io/) „Deploy a public app from GitHub“ wählen.
6. Das Formular ausfüllen:

| Feld | Eintrag |
| --- | --- |
| Repository | `DEIN-GITHUB-NAME/fussball-analyse` – Platzhalter durch deinen Namen ersetzen |
| Branch | `main` – falls dein Repository anders heißt, den tatsächlichen Branch wählen |
| Main file path | `app.py` |
| App URL | Optional einen verfügbaren Namen wählen |
| Advanced settings → Python version | `3.12` |

7. Zunächst sind **keine API-Secrets nötig**. **Deploy** anklicken und warten, bis die App geöffnet wird.
8. Spieltag, Partien und Anstoßzeiten eingeben. Auf **Analyseauftrag erstellen** klicken. Den fertigen Auftrag aufklappen, kopieren und in ChatGPT einfügen, oder als Markdown herunterladen.

Beispielformat, mit deinen tatsächlichen Partien ersetzen:

```text
Heimmannschaft - Auswärtsmannschaft | 15:30
Andere Heimmannschaft - Andere Auswärtsmannschaft | 18:00
```

Die Uhrzeiten gelten für Wien/Berlin. Das eingestellte Datum gilt für alle Zeilen. Unterschiedliche Spieltage getrennt eingeben. Begonnene Partien werden vor dem Start eines Auftrags abgewiesen.

## Zugangscode und API-Funktionen einrichten

Die öffentliche Streamlit-App hat eine öffentlich erreichbare URL. Sobald du APIs anschließt, verlangt diese App einen Zugangscode, bevor kostenpflichtige Funktionen nutzbar sind. Der Code ersetzt keine professionelle Benutzerverwaltung; für mehrere Nutzer oder öffentliche Nutzung wäre eine separate Anmeldung nötig.

Unter **Manage app → Settings → Secrets** in Streamlit diese Werte hinterlegen:

```toml
APP_PASSWORD = "DEIN_EIGENER_LANGER_ZUFAELLIGER_ZUGANGSCODE"
API_FOOTBALL_KEY = "DEIN_TATSAECHLICHER_API_FOOTBALL_SCHLUESSEL"
OPENAI_API_KEY = "DEIN_TATSAECHLICHER_OPENAI_API_SCHLUESSEL"
OPENAI_MODEL = "gpt-5.4"
```

Nur die Schlüssel eintragen, die du bereits hast. `APP_PASSWORD` kannst du auch schon ohne API-Zugänge setzen. Danach speichern und die App neu laden. Die echte Secrets-Datei und echte Schlüssel **nicht in GitHub hochladen** und nicht in den Analyse-Prompt kopieren. `secrets_beispiel.toml` enthält ausschließlich Platzhalter; echte Werte werden direkt in Streamlit eingetragen.

### Spiele automatisch laden

1. Konto/Zugang bei [API-Football](https://www.api-football.com/) bzw. [API-Sports Dashboard](https://dashboard.api-football.com/) einrichten und den dort erzeugten API-Sports-Schlüssel verwenden. Die App nutzt den direkten API-Sports-Endpunkt, keinen RapidAPI-Schlüssel.
2. `API_FOOTBALL_KEY` und `APP_PASSWORD` in Streamlit-Secrets speichern.
3. In der App **Spiele automatisch laden → Spiele laden** wählen.
4. Nach Ländern und Wettbewerben filtern und Partien auswählen. Die Filter stammen aus dem tatsächlich gelieferten Spielplan.

Welche Saisons, Ligen, Verletzungen, Aufstellungen und Statistiken verfügbar sind, hängt vom Tarif und der Datenabdeckung ab. Ein kostenloser oder eingeschränkter Tarif kann für den aktuellen Spieltag unzureichend sein. Bei fehlendem Zugriff bleibt die manuelle Eingabe möglich.

### Analyse direkt in der App

1. [OpenAI API-Konto](https://platform.openai.com/) einrichten, Abrechnung aktivieren und einen API-Schlüssel erzeugen. Die Nutzung der API wird gesondert abgerechnet.
2. `OPENAI_API_KEY` und `APP_PASSWORD` in Streamlit-Secrets speichern. `OPENAI_MODEL` ist optional; voreingestellt ist `gpt-5.4` mit Websuche und hoher Reasoning-Stufe. Ein anderes Modell muss diese Funktionen und Hintergrundaufträge unterstützen.
3. Spiele auswählen und bei Bedarf aktuelle Quoten ergänzen.
4. **KI-Analyse starten (API-Kosten)** anklicken. Dies startet einen kostenpflichtigen Recherche-Auftrag. Der Status wird alle fünf Sekunden aktualisiert. Fenster geöffnet lassen.
5. Nach Abschluss den Bericht mit anklickbaren Quellen lesen oder herunterladen. Unvollständige Antworten, Datenlücken und ein zwischenzeitlicher Anpfiff werden gekennzeichnet.

Ohne API-Football-Schlüssel funktioniert die direkte KI-Analyse für manuell eingegebene Partien über Webrecherche. Bei automatisch ausgewählten Partien ergänzt API-Football verfügbare Saisonstatistiken, bis zu zehn zuletzt beendete Spiele, Aufstellungen und Ausfalldaten entsprechend der Abdeckung. Auf Wunsch werden zusätzliche Statistiken aus bis zu fünf jüngsten Ligaspielen je Team geladen. Das ist keine Zusicherung einer vollständigen xG-Datenbank oder vollständiger Verletzungsdaten.

Pro KI-Auftrag sind maximal 20 Suchwerkzeug-Aufrufe und 24.000 Ausgabe-/Reasoning-Token eingestellt. Das ist **kein Euro-Kostenlimit**. Umfang, Quellenlage und Modell beeinflussen Verbrauch und Laufzeit. API-Football-Abrufe sind zusätzlich auf 80 neue Requests pro Datenanreicherung begrenzt; danach werden Lücken ausgewiesen. Im jeweiligen API-Konto Verbrauch und Ausgaben verfolgen. Die App wiederholt kostenpflichtige Startanfragen nach Fehlern nicht automatisch. Beim Abbruch können bereits Kosten entstanden sein.

Hintergrundaufträge nutzen die gespeicherte OpenAI-Responses-API. Es werden die gewählten Partien, deine zusätzlichen Texte und ggf. Fußball-API-Daten übermittelt. Die App selbst speichert keine Analyse-Datenbank; Sitzungsdaten können bei Neustart oder Neuladen verloren gehen. Die Speicherung beim API-Anbieter folgt dessen Kontoeinstellungen und Bedingungen.

## Prompt und Quoten

`prompt.md` enthält den vollständigen eingebundenen Fußball-Prompt. Du kannst ihn in GitHub dauerhaft bearbeiten oder in der App für den aktuellen Auftrag anpassen. Die Analyse beginnt mit sportlichen Fakten; tatsächlich vorgelegte Quoten ergänzen die Bewertung.

- 2er-, 3er-, 4er- und weitere Kombis sind möglich, soweit fachlich begründet.
- Märkte desselben Spiels sind nur als sinnvoller Bet Builder mit tatsächlicher Anbieterquote zu bewerten. Zusammenhängende Wahrscheinlichkeiten/Quoten werden nicht blind multipliziert.
- Fehlende Quoten verhindern sportliche Auswahlen und Kombientwürfe nicht. Es werden keine aktuellen Anbieterquoten erfunden oder automatisch aus einem anderen Wettanbieter übernommen.
- Große Kombis und mehrere Scheine mit denselben Auswahlen erhöhen das gemeinsame Verlustrisiko. Hohe Auszahlung ist kein Beleg für eine gute Wette; es gibt keine Gewinnzusage.
- Die App platziert keine Wetten.

## Lokal starten und prüfen

Python 3.12 verwenden:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Optionale lokale Secrets: `.streamlit/secrets.toml` anlegen und Werte wie oben eintragen. `.gitignore` schließt diese Datei aus Git aus.

```bash
python -m unittest discover -s tests -v
```

Die Tests prüfen Eingabeverarbeitung, Anstoßzeiten, Datenabdeckung, API-Fehler, Quellenlinks und die Streamlit-Oberfläche. Externe API-Aufrufe werden dabei simuliert; keine kostenpflichtigen Requests. Ohne tatsächliche API-Zugänge sind weder deine Tarifabdeckung noch reale Modellzugriffe live geprüft.

## Wenn die Bereitstellung fehlschlägt

- **Main file does not exist:** Liegt `app.py` direkt im Repository und ist `main` der tatsächliche Branch?
- **ModuleNotFoundError:** `requirements.txt` und alle Python-Dateien zusammen hochladen. Bei einem fehlenden eigenen Modul (`logic` usw.) die Dateien auf derselben Ebene ablegen.
- **Keine aktuellen Spiele:** Datum, Anbieter-Tarif und freigegebene Saison prüfen; manuelle Eingabe verwenden.
- **API-Funktionen gesperrt:** `APP_PASSWORD` in Streamlit-Secrets ergänzen und App neu laden.
- **Fehler in Secrets:** TOML-Format wie im Beispiel verwenden, jede Zeichenfolge in Anführungszeichen.
- **Verbindungsfehler beim Start:** Der Auftrag kann trotz fehlender Bestätigung beim API-Anbieter existieren. Verbrauch/Dashboard prüfen, bevor du erneut startest.

Offizielle Dokumentation: [Streamlit-Deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [Streamlit-Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management), [API-Football](https://www.api-football.com/documentation-v3), [OpenAI-Websuche](https://developers.openai.com/api/docs/guides/tools-web-search), [OpenAI-Hintergrundaufträge](https://developers.openai.com/api/docs/guides/background).
