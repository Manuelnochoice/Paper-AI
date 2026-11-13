"""bioRxiv e medRxiv: preprint di biologia e medicina.

I due archivi condividono la stessa API; cambia solo il nome del server.
L'API elenca i preprint per intervallo di date, 100 per pagina, senza filtro
per categoria: il filtro lo applichiamo noi sui risultati.
Documentazione: https://api.biorxiv.org
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator

from paper_radar.fonti.http import richiesta
from paper_radar.modelli import PaperGrezzo

BASE = "https://api.biorxiv.org/details"
# I due archivi pubblicano centinaia di preprint al giorno: guardiamo solo
# gli ultimi giorni per restare entro poche richieste.
GIORNI_FINESTRA = 3


def converti(voce: dict, server: str) -> PaperGrezzo:
    doi = voce.get("doi", "")
    versione = voce.get("version", "1")
    sito = "www.biorxiv.org" if server == "biorxiv" else "www.medrxiv.org"
    return PaperGrezzo(
        titolo=(voce.get("title") or "").strip(),
        fonte=server,
        abstract=(voce.get("abstract") or "").strip(),
        autori=[a.strip() for a in (voce.get("authors") or "").split(";") if a.strip()][:30],
        data_pubblicazione=voce.get("date") or "",
        doi=doi or None,
        sede="bioRxiv" if server == "biorxiv" else "medRxiv",
        stato="preprint",
        url=f"https://{sito}/content/{doi}v{versione}",
        url_pdf=f"https://{sito}/content/{doi}v{versione}.full.pdf",
    )


class BioRxiv:
    """Vale sia per bioRxiv sia per medRxiv: basta cambiare `server`."""

    def __init__(self, server: str = "biorxiv", timeout: float = 25, tentativi: int = 3):
        self.server = server
        self.nome = server
        self.timeout = timeout
        self.tentativi = tentativi

    def pagine(self, opzioni: dict, dal: str, al: str) -> Iterator[list[PaperGrezzo]]:
        categorie = {c.lower() for c in opzioni.get("categorie") or []}
        inizio_finestra = max(dal, (date.fromisoformat(al) - timedelta(days=GIORNI_FINESTRA)).isoformat())
        cursore = 0
        while True:
            dati = richiesta(
                f"{BASE}/{self.server}/{inizio_finestra}/{al}/{cursore}/json",
                timeout=self.timeout, tentativi=self.tentativi,
            ).json()
            voci = dati.get("collection") or []
            if not voci:
                return
            # Se è stato scelto un elenco di categorie teniamo solo quelle.
            scelte = [v for v in voci if not categorie or (v.get("category") or "").lower() in categorie]
            yield [converti(v, self.server) for v in scelte]
            cursore += len(voci)
