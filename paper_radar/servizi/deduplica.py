"""Riconoscimento dei doppioni.

Lo stesso paper può arrivare da più fonti (es. OpenAlex e arXiv) con
identificativi diversi. Due record sono lo stesso paper se coincide almeno
uno tra: DOI, id arXiv, PMID, id OpenAlex oppure il titolo "normalizzato".
"""
from __future__ import annotations

import re
import unicodedata

from paper_radar.modelli import PaperGrezzo


def normalizza_doi(doi: str | None) -> str | None:
    """Porta il DOI in una forma unica: minuscolo e senza prefissi."""
    if not doi:
        return None
    doi = doi.strip().lower()
    for prefisso in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefisso):
            doi = doi[len(prefisso):]
    # Le versioni dei preprint arXiv (…v2) indicano lo stesso paper.
    if doi.startswith("10.48550/arxiv."):
        doi = re.sub(r"v\d+$", "", doi)
    return doi or None


def normalizza_titolo(titolo: str) -> str:
    """Toglie accenti, maiuscole, punteggiatura e spazi: restano lettere e cifre.

    "Deep Learning: A Review!" e "deep learning - a review" diventano uguali.
    """
    senza_accenti = unicodedata.normalize("NFKD", titolo or "")
    senza_accenti = "".join(c for c in senza_accenti if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", senza_accenti.lower())


def chiavi(paper: PaperGrezzo) -> dict[str, str]:
    """Le chiavi con cui cercare un paper già presente nel database.

    Restituisce un dizionario colonna -> valore, con le sole chiavi disponibili.
    """
    candidate = {
        "doi": normalizza_doi(paper.doi),
        "arxiv_id": re.sub(r"v\d+$", "", paper.arxiv_id) if paper.arxiv_id else None,
        "pmid": paper.pmid,
        "openalex_id": paper.openalex_id,
    }
    titolo = normalizza_titolo(paper.titolo)
    # Titoli molto corti ("Editorial", "Erratum") non bastano a identificare un paper.
    if len(titolo) >= 25:
        candidate["titolo_norm"] = titolo
    return {colonna: valore for colonna, valore in candidate.items() if valore}
