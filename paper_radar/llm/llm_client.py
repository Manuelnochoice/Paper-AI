"""Unico punto di contatto con il modello linguistico.

Tutto il resto dell'app chiama solo `LLMClient.genera_json()`. Per cambiare
provider (es. da Gemini a un altro) basta scrivere una nuova classe con il
metodo `genera(modello, prompt) -> str` e passarla a LLMClient.

Cosa fa il client:
- rispetta i limiti del piano gratuito (vedi rate_limiter.py);
- riprova con attese crescenti sugli errori 429;
- passa a un modello più leggero quando la quota è esaurita;
- pretende JSON valido, riprovando se la risposta è malformata.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from paper_radar.fonti.http import ErroreFonte, richiesta
from paper_radar.llm.rate_limiter import QuotaGiornalieraEsaurita, RateLimiter


class ErroreLLM(Exception):
    """Errore del modello, con messaggio adatto a essere mostrato all'utente."""

    def __init__(self, messaggio: str, quota_esaurita: bool = False):
        super().__init__(messaggio)
        # True se TUTTI i modelli hanno finito le richieste di oggi.
        self.quota_esaurita = quota_esaurita


class TroppeRichieste(Exception):
    """Il provider ha risposto 429 (limite di richieste superato)."""


class ServerOccupato(Exception):
    """Il provider è sovraccarico o non raggiungibile (errori 5xx, timeout)."""


class ModelloNonDisponibile(Exception):
    """Il modello non esiste o non è utilizzabile con questa chiave."""


# ---------------------------------------------------------------- provider

class GeminiProvider:
    """Chiama l'API REST di Gemini (https://ai.google.dev/api/generate-content)."""

    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, temperatura: float = 0.2, timeout: float = 180):
        self.api_key = api_key
        self.temperatura = temperatura
        self.timeout = timeout

    def genera(self, modello: str, prompt: str) -> str:
        try:
            r = richiesta(
                f"{self.BASE}/{modello}:generateContent",
                headers={"x-goog-api-key": self.api_key},     # la chiave viaggia nell'intestazione, non nell'URL
                json_body={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": self.temperatura,
                        "responseMimeType": "application/json",   # chiede al modello di rispondere in JSON
                    },
                },
                timeout=self.timeout,
                tentativi=1,          # i nuovi tentativi li gestisce LLMClient
            )
        except ErroreFonte as e:
            if e.status == 429:
                raise TroppeRichieste() from e
            if e.status in (400, 401, 403, 404):
                raise ModelloNonDisponibile(
                    f"{modello} (HTTP {e.status}: controlla la chiave API e il nome del modello)") from e
            raise ServerOccupato(str(e)) from e

        try:
            parti = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parti)
        except (KeyError, IndexError, ValueError) as e:
            raise ErroreLLM("Il modello ha restituito una risposta vuota o bloccata.") from e

    def modelli_disponibili(self) -> list[str]:
        """Nomi dei modelli utilizzabili con questa chiave (per lo script di verifica)."""
        r = richiesta(self.BASE, headers={"x-goog-api-key": self.api_key}, params={"pageSize": 200}, tentativi=2)
        return [
            m["name"].removeprefix("models/") for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]


# ---------------------------------------------------------------- client

@dataclass
class RispostaLLM:
    dati: BaseModel      # risposta validata
    modello: str         # modello che l'ha prodotta
    richieste: int       # richieste consumate in totale


def estrai_json(testo: str) -> dict:
    """Interpreta la risposta come JSON, togliendo eventuali recinti ```json ... ```."""
    testo = testo.strip()
    testo = re.sub(r"^```(?:json)?\s*|\s*```$", "", testo)
    dati = json.loads(testo)
    if not isinstance(dati, dict):
        raise ValueError("la risposta non è un oggetto JSON")
    return dati


class LLMClient:
    def __init__(self, provider, modelli: list[dict], contatore,
                 tentativi_json: int = 2, tentativi_429: int = 3, dormi=time.sleep):
        self.provider = provider
        self.tentativi_json = tentativi_json
        self.tentativi_429 = tentativi_429
        self._dormi = dormi
        # Un limitatore per modello, nell'ordine di preferenza della configurazione.
        self.limitatori = [
            RateLimiter(m["nome"], m["rpm"], m["rpd"], contatore, dormi=dormi) for m in modelli
        ]

    def quote(self) -> list[dict]:
        """Richieste rimaste oggi per ogni modello (mostrate nell'interfaccia)."""
        return [{"modello": l.modello, "rimaste": l.rimaste_oggi(), "totale": l.rpd} for l in self.limitatori]

    def genera_json(self, prompt: str, schema: type[BaseModel]) -> RispostaLLM:
        """Chiede al modello una risposta JSON conforme a `schema` (classe Pydantic)."""
        richieste = 0
        esauriti = 0
        problemi: list[str] = []

        for limitatore in self.limitatori:
            prompt_corrente = prompt
            for _ in range(self.tentativi_json + 1):
                try:
                    testo, usate = self._chiama(limitatore, prompt_corrente)
                    richieste += usate
                except QuotaGiornalieraEsaurita:
                    problemi.append(f"{limitatore.modello}: quota di oggi esaurita")
                    esauriti += 1
                    break                                   # passa al modello successivo
                except ModelloNonDisponibile as e:
                    problemi.append(f"modello non disponibile: {e}")
                    break

                try:
                    return RispostaLLM(schema.model_validate(estrai_json(testo)), limitatore.modello, richieste)
                except (ValueError, ValidationError) as e:
                    # JSON malformato o incompleto: si riprova spiegando l'errore al modello.
                    problemi.append(f"{limitatore.modello}: JSON non valido")
                    prompt_corrente = (
                        f"{prompt}\n\nATTENZIONE: la tua risposta precedente non era valida.\n"
                        f"Errore: {str(e)[:600]}\nRispondi di nuovo con SOLO il JSON corretto e completo."
                    )

        raise ErroreLLM(
            "Analisi non riuscita. " + "; ".join(dict.fromkeys(problemi)) + ".",
            quota_esaurita=esauriti == len(self.limitatori),
        )

    def _chiama(self, limitatore: RateLimiter, prompt: str) -> tuple[str, int]:
        """Una chiamata al modello, con nuovi tentativi e attesa crescente (backoff).

        Si riprova sugli errori 429 (troppe richieste) e sui problemi temporanei
        del server. Restituisce il testo della risposta e le richieste consumate.
        """
        ultimo_errore: Exception | None = None
        for n in range(self.tentativi_429 + 1):
            limitatore.acquisisci()
            try:
                return self.provider.genera(limitatore.modello, prompt), n + 1
            except (TroppeRichieste, ServerOccupato) as e:
                ultimo_errore = e
                if n < self.tentativi_429:
                    self._dormi(min(5 * 2 ** n, 60))        # 5s, 10s, 20s...
        if isinstance(ultimo_errore, TroppeRichieste):
            # 429 anche dopo le attese: quasi certamente è finita la quota giornaliera.
            limitatore.segna_esaurito()
            raise QuotaGiornalieraEsaurita(limitatore.modello)
        raise ModelloNonDisponibile(f"{limitatore.modello} (server sovraccarico o non raggiungibile)")
