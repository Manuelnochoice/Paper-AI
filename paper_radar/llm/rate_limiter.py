"""Limitatore di richieste per il piano gratuito.

Rispetta due limiti per ogni modello:
- RPM (richieste al minuto): se il minuto è pieno, aspetta che si liberi un posto;
- RPD (richieste al giorno): se la quota del giorno è finita, solleva un errore
  così chi chiama può passare a un modello più leggero.
"""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    FUSO_QUOTE = ZoneInfo("America/Los_Angeles")
except Exception:            # su Windows serve il pacchetto "tzdata"; se manca si usa UTC
    FUSO_QUOTE = timezone.utc


class QuotaGiornalieraEsaurita(Exception):
    """Le richieste di oggi per questo modello sono finite."""


def giorno_delle_quote() -> str:
    """Il "giorno" secondo Google: le quote si azzerano a mezzanotte, ora del Pacifico."""
    return datetime.now(FUSO_QUOTE).date().isoformat()


class ContatoreInMemoria:
    """Contatore giornaliero semplice (usato nei test; l'app usa quello su SQLite)."""

    def __init__(self):
        self._valori: dict[tuple[str, str], int] = {}

    def leggi(self, giorno: str, modello: str) -> int:
        return self._valori.get((giorno, modello), 0)

    def imposta(self, giorno: str, modello: str, richieste: int) -> None:
        self._valori[(giorno, modello)] = richieste


class RateLimiter:
    def __init__(self, modello: str, rpm: int, rpd: int, contatore,
                 orologio=time.monotonic, dormi=time.sleep, giorno=giorno_delle_quote):
        self.modello = modello
        self.rpm = rpm
        self.rpd = rpd
        self.contatore = contatore
        # orologio, dormi e giorno sono parametri per poterli sostituire nei test
        # (così i test non aspettano davvero un minuto).
        self._orologio = orologio
        self._dormi = dormi
        self._giorno = giorno
        self._recenti: deque[float] = deque()     # istanti delle richieste dell'ultimo minuto

    def usate_oggi(self) -> int:
        return self.contatore.leggi(self._giorno(), self.modello)

    def rimaste_oggi(self) -> int:
        return max(self.rpd - self.usate_oggi(), 0)

    def segna_esaurito(self) -> None:
        """Il server dice che la quota è finita: allinea il contatore locale."""
        self.contatore.imposta(self._giorno(), self.modello, self.rpd)

    def acquisisci(self) -> None:
        """Da chiamare prima di ogni richiesta: aspetta il proprio turno e la conta."""
        if self.rimaste_oggi() <= 0:
            raise QuotaGiornalieraEsaurita(self.modello)

        adesso = self._orologio()
        # Dimentica le richieste più vecchie di 60 secondi.
        while self._recenti and adesso - self._recenti[0] >= 60:
            self._recenti.popleft()
        # Minuto pieno: aspetta finché la richiesta più vecchia esce dalla finestra.
        if len(self._recenti) >= self.rpm:
            self._dormi(60 - (adesso - self._recenti[0]))
            adesso = self._orologio()
            while self._recenti and adesso - self._recenti[0] >= 60:
                self._recenti.popleft()

        self._recenti.append(adesso)
        self.contatore.imposta(self._giorno(), self.modello, self.usate_oggi() + 1)
