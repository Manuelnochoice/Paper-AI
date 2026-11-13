"""ChemRxiv: preprint di chimica.

ChemRxiv ha un'API pubblica, ma a volte respinge le richieste automatiche.
In quel caso `raccolta.py` ripiega su OpenAlex, cercando i paper il cui DOI
inizia con il prefisso di ChemRxiv (10.26434).
Documentazione: https://chemrxiv.org/engage/chemrxiv/public-api/documentation
"""
from __future__ import annotations

from typing import Iterator

from paper_radar.fonti.http import richiesta
from paper_radar.modelli import PaperGrezzo

URL = "https://chemrxiv.org/engage/chemrxiv/public-api/v1/items"
PREFISSO_DOI = "10.26434"


def converti(elemento: dict) -> PaperGrezzo:
    doi = elemento.get("doi") or None
    return PaperGrezzo(
        titolo=(elemento.get("title") or "").strip(),
        fonte="chemrxiv",
        abstract=(elemento.get("abstract") or "").strip(),
        autori=[
            f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
            for a in elemento.get("authors") or []
        ][:30],
        data_pubblicazione=(elemento.get("publishedDate") or "")[:10],
        doi=doi,
        sede="ChemRxiv",
        stato="preprint",
        url=f"https://doi.org/{doi}" if doi else "https://chemrxiv.org",
    )


class ChemRxiv:
    nome = "chemrxiv"

    def __init__(self, timeout: float = 25, tentativi: int = 2):
        self.timeout = timeout
        self.tentativi = tentativi

    def pagine(self, opzioni: dict, dal: str, al: str) -> Iterator[list[PaperGrezzo]]:
        salto = 0
        while True:
            dati = richiesta(URL, params={
                "limit": 50, "skip": salto, "sort": "PUBLISHED_DATE_DESC",
            }, headers={"Accept": "application/json"}, timeout=self.timeout, tentativi=self.tentativi).json()
            voci = [h.get("item") or {} for h in dati.get("itemHits") or []]
            if not voci:
                return
            paper = [converti(v) for v in voci]
            yield paper
            if paper[-1].data_pubblicazione < dal:
                return
            salto += 50
