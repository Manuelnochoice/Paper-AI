"""Richieste HTTP con timeout, nuovi tentativi e messaggi d'errore leggibili.

Tutte le fonti passano da `richiesta()`, così errori, timeout e limiti delle
API sono gestiti in un solo punto.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

# Codici per cui ha senso riprovare: 429 = troppe richieste, 5xx = problema del server.
CODICI_RIPROVABILI = {429, 500, 502, 503, 504}


class ErroreFonte(Exception):
    """Errore di una fonte esterna, con un messaggio adatto a essere mostrato."""

    def __init__(self, messaggio: str, status: int | None = None):
        super().__init__(messaggio)
        self.status = status


def richiesta(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    json_body: dict | None = None,
    timeout: float = 25,
    tentativi: int = 3,
    dormi=time.sleep,
) -> requests.Response:
    """Esegue una richiesta GET (o POST se c'è `json_body`) riprovando se serve.

    L'attesa tra un tentativo e l'altro raddoppia ogni volta (backoff
    esponenziale): 2s, 4s, 8s... Se il server indica quanto aspettare
    (intestazione Retry-After) si rispetta quel valore.

    I messaggi d'errore contengono solo il nome del sito, mai l'URL completo:
    alcuni URL includono la chiave API tra i parametri.
    """
    sito = urlparse(url).netloc
    errore, status = "errore sconosciuto", None

    for n in range(tentativi):
        attesa = 2 ** (n + 1)
        try:
            if json_body is not None:
                r = requests.post(url, params=params, headers=headers, json=json_body, timeout=timeout)
            else:
                r = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.Timeout:
            errore, status = "il server non ha risposto in tempo", None
        except requests.RequestException:
            errore, status = "connessione non riuscita (controlla la rete)", None
        else:
            if r.status_code < 400:
                return r
            status = r.status_code
            if status not in CODICI_RIPROVABILI:
                raise ErroreFonte(f"{sito}: richiesta rifiutata (HTTP {status})", status)
            errore = "troppe richieste (HTTP 429)" if status == 429 else f"errore del server (HTTP {status})"
            retry_after = r.headers.get("Retry-After", "")
            if retry_after.isdigit():
                attesa = min(int(retry_after), 60)

        if n < tentativi - 1:
            dormi(attesa)

    raise ErroreFonte(f"{sito}: {errore}, dopo {tentativi} tentativi", status)
