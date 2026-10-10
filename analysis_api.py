"""Aktuelle Recherche über Responses API; kostenpflichtige Aufträge nur auf Klick."""
from __future__ import annotations

import json
from openai import OpenAI, APIError, AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError, BadRequestError

from logic import RUNTIME_INSTRUCTIONS, validate_upcoming


class AnalysisError(RuntimeError):
    pass


class AnalysisClient:
    def __init__(self, api_key: str, model: str = "gpt-5.4", client=None):
        self.model = model
        self.client = client or OpenAI(api_key=api_key, timeout=45, max_retries=0)

    def _call(self, method, *args, **kwargs) -> dict:
        try:
            response = method(*args, **kwargs)
            return response.model_dump() if hasattr(response, "model_dump") else response
        except AuthenticationError:
            raise AnalysisError("OpenAI-Schlüssel ist ungültig oder hat keinen Zugriff.") from None
        except RateLimitError:
            raise AnalysisError("OpenAI-Kontingent oder Anfragelimit erreicht. Guthaben und Limits im API-Konto prüfen.") from None
        except (APITimeoutError, APIConnectionError):
            raise AnalysisError("OpenAI-Verbindung unterbrochen. Ein Auftrag kann trotzdem gestartet worden sein. Im API-Dashboard prüfen, bevor du ihn erneut startest.") from None
        except BadRequestError:
            raise AnalysisError("OpenAI hat den Auftrag abgelehnt. Modellzugriff, Websuche und Hintergrundmodus für das konfigurierte Modell prüfen.") from None
        except APIError:
            raise AnalysisError("OpenAI meldet einen Fehler. Status und API-Konto prüfen; nicht automatisch erneut gestartet.") from None

    def start(self, prompt: str, context: dict) -> dict:
        validate_upcoming(context["spiele"])
        if not prompt.strip():
            raise AnalysisError("Der Analyse-Prompt ist leer.")
        return self._call(
            self.client.responses.create,
            model=self.model, instructions=prompt + "\n\n" + RUNTIME_INSTRUCTIONS,
            input="Analysiere diese Partien nach dem vollständigen Prompt:\n" + json.dumps(context, ensure_ascii=False, indent=2),
            tools=[{"type": "web_search"}], tool_choice="required",
            include=["web_search_call.action.sources"],
            background=True, store=True, reasoning={"effort": "high"},
            max_output_tokens=24000, max_tool_calls=20,
        )

    def retrieve(self, response_id: str) -> dict:
        return self._call(self.client.responses.retrieve, response_id, include=["web_search_call.action.sources"])

    def cancel(self, response_id: str) -> dict:
        return self._call(self.client.responses.cancel, response_id)
