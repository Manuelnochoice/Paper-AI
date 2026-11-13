"""OpenAlex: la fonte di base per tutte le aree.

Fornisce metadati, citazioni, riferimenti bibliografici e paper correlati.
Dal febbraio 2026 l'API richiede una chiave gratuita (OPENALEX_API_KEY).
Documentazione: https://docs.openalex.org
"""
from __future__ import annotations

from typing import Iterator

from paper_radar.fonti.http import ErroreFonte, richiesta
from paper_radar.modelli import PaperGrezzo

BASE = "https://api.openalex.org"

# Chiediamo solo i campi che servono: risposte più leggere e veloci.
CAMPI = (
    "id,doi,display_name,publication_date,type,abstract_inverted_index,authorships,"
    "primary_location,ids,cited_by_count,referenced_works,related_works,open_access"
)


def id_breve(valore: str | None) -> str | None:
    """'https://openalex.org/W123' -> 'W123'."""
    if not valore:
        return None
    return valore.rstrip("/").split("/")[-1]


def ricostruisci_abstract(indice: dict | None) -> str:
    """OpenAlex salva l'abstract come 'indice invertito': parola -> posizioni.

    Esempio: {"Ciao": [0], "mondo": [1]} diventa "Ciao mondo".
    """
    if not indice:
        return ""
    posizioni = [(pos, parola) for parola, lista in indice.items() for pos in lista]
    return " ".join(parola for _, parola in sorted(posizioni))


def _stato(lavoro: dict) -> str:
    """Deduce preprint/rivista dai metadati (non lo decide il modello)."""
    sede = (lavoro.get("primary_location") or {}).get("source") or {}
    if lavoro.get("type") == "preprint" or sede.get("type") == "repository":
        return "preprint"
    if sede.get("type") == "journal":
        return "rivista"
    return "sconosciuto"


def converti(lavoro: dict) -> PaperGrezzo:
    """Traduce un 'work' di OpenAlex nel formato comune dell'app."""
    posizione = lavoro.get("primary_location") or {}
    sede = posizione.get("source") or {}
    ids = lavoro.get("ids") or {}
    doi = (lavoro.get("doi") or "").replace("https://doi.org/", "") or None
    pmid = id_breve(ids.get("pmid"))
    pmcid = id_breve(ids.get("pmcid"))
    arxiv_id = None
    if doi and doi.lower().startswith("10.48550/arxiv."):
        arxiv_id = doi[len("10.48550/arxiv."):]

    return PaperGrezzo(
        titolo=(lavoro.get("display_name") or "").strip(),
        fonte="openalex",
        abstract=ricostruisci_abstract(lavoro.get("abstract_inverted_index")),
        autori=[
            (a.get("author") or {}).get("display_name", "")
            for a in (lavoro.get("authorships") or [])[:30]
        ],
        data_pubblicazione=lavoro.get("publication_date") or "",
        doi=doi,
        arxiv_id=arxiv_id,
        pmid=pmid,
        pmcid=pmcid,
        openalex_id=id_breve(lavoro.get("id")),
        sede=sede.get("display_name") or "",
        stato=_stato(lavoro),
        url=posizione.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else lavoro.get("id", "")),
        url_pdf=posizione.get("pdf_url") or (lavoro.get("open_access") or {}).get("oa_url") or "",
        n_citazioni=lavoro.get("cited_by_count"),
        riferimenti=[id_breve(x) for x in lavoro.get("referenced_works") or []],
        correlati=[id_breve(x) for x in lavoro.get("related_works") or []],
    )


class OpenAlex:
    nome = "openalex"

    def __init__(self, api_key: str | None, timeout: float = 25, tentativi: int = 3):
        self.api_key = api_key
        self.timeout = timeout
        self.tentativi = tentativi

    def _get(self, percorso: str, params: dict) -> dict:
        if self.api_key:
            params = {**params, "api_key": self.api_key}
        r = richiesta(f"{BASE}{percorso}", params=params, timeout=self.timeout, tentativi=self.tentativi)
        return r.json()

    # --- raccolta dei paper recenti -------------------------------------
    def pagine(self, opzioni: dict, dal: str, al: str) -> Iterator[list[PaperGrezzo]]:
        """Restituisce una pagina alla volta di paper recenti, dal più nuovo."""
        filtro = (
            f"{opzioni['filtro']},from_publication_date:{dal},to_publication_date:{al},"
            "has_abstract:true,type:article|preprint|review"
        )
        cursore = "*"
        while cursore:
            dati = self._get("/works", {
                "filter": filtro,
                "sort": "publication_date:desc",
                "per-page": 50,
                "cursor": cursore,
                "select": CAMPI,
            })
            risultati = dati.get("results") or []
            if not risultati:
                return
            yield [converti(x) for x in risultati]
            cursore = (dati.get("meta") or {}).get("next_cursor")

    # --- ricerche puntuali (contesto e grafo) ---------------------------
    def per_id(self, ids: list[str]) -> list[PaperGrezzo]:
        """Metadati di più paper in una sola richiesta (massimo 50 id per volta)."""
        trovati: list[PaperGrezzo] = []
        for i in range(0, len(ids), 50):
            blocco = "|".join(ids[i:i + 50])
            dati = self._get("/works", {"filter": f"openalex:{blocco}", "per-page": 50, "select": CAMPI})
            trovati += [converti(x) for x in dati.get("results") or []]
        return trovati

    def per_doi(self, doi: str) -> PaperGrezzo | None:
        try:
            return converti(self._get(f"/works/doi:{doi}", {"select": CAMPI}))
        except ErroreFonte as e:
            if e.status == 404:      # paper non (ancora) presente in OpenAlex
                return None
            raise

    def citanti(self, openalex_id: str, massimo: int) -> list[PaperGrezzo]:
        """Paper che citano quello indicato, dai più citati."""
        dati = self._get("/works", {
            "filter": f"cites:{openalex_id}",
            "sort": "cited_by_count:desc",
            "per-page": massimo,
            "select": CAMPI,
        })
        return [converti(x) for x in dati.get("results") or []]

    def pagine_doi_prefisso(self, prefisso: str, dal: str, al: str) -> Iterator[list[PaperGrezzo]]:
        """Paper recenti il cui DOI inizia con un prefisso (usato come ripiego per ChemRxiv)."""
        dati = self._get("/works", {
            "filter": f"doi_starts_with:{prefisso},from_publication_date:{dal},to_publication_date:{al}",
            "sort": "publication_date:desc",
            "per-page": 50,
            "select": CAMPI,
        })
        yield [converti(x) for x in dati.get("results") or []]
