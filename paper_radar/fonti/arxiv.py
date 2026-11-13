"""arXiv: preprint di fisica, matematica, informatica, AI, astronomia.

L'API restituisce XML in formato Atom. Non serve chiave, ma arXiv chiede di
non fare più di una richiesta ogni 3 secondi.
Documentazione: https://info.arxiv.org/help/api/
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Iterator

from paper_radar.fonti.http import richiesta
from paper_radar.modelli import PaperGrezzo

URL = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
PAUSA_SECONDI = 3


def _pulisci(testo: str | None) -> str:
    """Toglie ritorni a capo e spazi multipli."""
    return re.sub(r"\s+", " ", testo or "").strip()


def analizza_xml(xml: str) -> list[PaperGrezzo]:
    """Converte la risposta Atom di arXiv in una lista di paper."""
    radice = ET.fromstring(xml)
    paper = []
    for voce in radice.findall(f"{ATOM}entry"):
        indirizzo = _pulisci(voce.findtext(f"{ATOM}id"))        # http://arxiv.org/abs/2411.01234v2
        arxiv_id = re.sub(r"v\d+$", "", indirizzo.split("/abs/")[-1])
        if not arxiv_id:
            continue
        paper.append(PaperGrezzo(
            titolo=_pulisci(voce.findtext(f"{ATOM}title")),
            fonte="arxiv",
            abstract=_pulisci(voce.findtext(f"{ATOM}summary")),
            autori=[_pulisci(a.findtext(f"{ATOM}name")) for a in voce.findall(f"{ATOM}author")][:30],
            data_pubblicazione=_pulisci(voce.findtext(f"{ATOM}published"))[:10],
            arxiv_id=arxiv_id,
            # Ogni paper arXiv ha un DOI "di servizio": aiuta a riconoscere i doppioni.
            doi=f"10.48550/arxiv.{arxiv_id}",
            sede="arXiv",
            stato="preprint",
            url=f"https://arxiv.org/abs/{arxiv_id}",
            url_pdf=f"https://arxiv.org/pdf/{arxiv_id}",
        ))
    return paper


class Arxiv:
    nome = "arxiv"

    def __init__(self, timeout: float = 25, tentativi: int = 3, dormi=time.sleep):
        self.timeout = timeout
        self.tentativi = tentativi
        self.dormi = dormi

    def pagine(self, opzioni: dict, dal: str, al: str) -> Iterator[list[PaperGrezzo]]:
        ricerca = " OR ".join(f"cat:{c}" for c in opzioni["categorie"])
        inizio = 0
        while True:
            r = richiesta(URL, params={
                "search_query": ricerca,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": inizio,
                "max_results": 50,
            }, timeout=self.timeout, tentativi=self.tentativi)
            paper = analizza_xml(r.text)
            if not paper:
                return
            yield paper
            # I risultati sono in ordine di data: se l'ultimo è già troppo vecchio ci fermiamo.
            if paper[-1].data_pubblicazione < dal:
                return
            inizio += 50
            self.dormi(PAUSA_SECONDI)
