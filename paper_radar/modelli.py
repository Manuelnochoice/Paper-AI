"""Strutture dati condivise tra le fonti e il resto dell'app."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PaperGrezzo:
    """Un paper così come arriva da una fonte, prima di entrare nel database.

    Ogni fonte (OpenAlex, arXiv, PubMed...) ha un formato diverso: i moduli in
    `paper_radar/fonti` traducono tutto in questa forma comune.
    """

    titolo: str
    fonte: str                          # "openalex", "arxiv", "pubmed", ...
    abstract: str = ""
    autori: list[str] = field(default_factory=list)
    data_pubblicazione: str = ""        # formato ISO: AAAA-MM-GG
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    openalex_id: str | None = None      # forma breve, es. "W4401234567"
    sede: str = ""                      # rivista o archivio di preprint
    stato: str = "sconosciuto"          # "preprint", "rivista" o "sconosciuto"
    url: str = ""
    url_pdf: str = ""
    n_citazioni: int | None = None
    riferimenti: list[str] = field(default_factory=list)   # id OpenAlex citati
    correlati: list[str] = field(default_factory=list)     # id OpenAlex correlati


# Etichette leggibili per lo stato di pubblicazione.
# Nota: "rivista" significa che OpenAlex lo indica come uscito su una rivista;
# la revisione tra pari è molto probabile ma non è verificata paper per paper.
ETICHETTE_STATO = {
    "preprint": "Preprint (non ancora revisionato)",
    "rivista": "Pubblicato su rivista (peer review presunta)",
    "sconosciuto": "Stato di pubblicazione non rilevabile",
}
