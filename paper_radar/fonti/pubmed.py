"""PubMed: letteratura biomedica (tramite le E-utilities di NCBI).

Si lavora in due passi:
1. esearch -> elenco degli identificativi (PMID) che rispondono alla ricerca
2. efetch  -> dettagli (titolo, abstract, autori) di quei PMID, in XML
Senza chiave NCBI consente 3 richieste al secondo: più che sufficienti qui.
Documentazione: https://www.ncbi.nlm.nih.gov/books/NBK25499/
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from typing import Iterator

from paper_radar.fonti.http import richiesta
from paper_radar.modelli import PaperGrezzo

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MESI = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def _testo(elemento) -> str:
    """Testo completo di un elemento XML, compresi eventuali tag interni (corsivi ecc.)."""
    return " ".join("".join(elemento.itertext()).split()) if elemento is not None else ""


def _data(articolo) -> str:
    """Data in cui il record è entrato in PubMed (la più affidabile per 'recente')."""
    for d in articolo.iter("PubMedPubDate"):
        if d.get("PubStatus") == "pubmed":
            anno, mese, giorno = d.findtext("Year"), d.findtext("Month"), d.findtext("Day")
            if anno and mese and giorno:
                mese_n = int(mese) if mese.isdigit() else MESI.get(mese[:3], 1)
                return f"{int(anno):04d}-{mese_n:02d}-{int(giorno):02d}"
    return ""


def analizza_xml(xml: str) -> list[PaperGrezzo]:
    """Converte la risposta di efetch in una lista di paper."""
    paper = []
    for articolo in ET.fromstring(xml).findall("PubmedArticle"):
        pmid = articolo.findtext("MedlineCitation/PMID")
        # L'abstract può essere diviso in sezioni con etichetta (BACKGROUND, METHODS...).
        sezioni = []
        for parte in articolo.findall(".//Abstract/AbstractText"):
            etichetta = parte.get("Label")
            sezioni.append(f"{etichetta}: {_testo(parte)}" if etichetta else _testo(parte))
        ids = {i.get("IdType"): (i.text or "").strip() for i in articolo.findall(".//ArticleIdList/ArticleId")}
        autori = [
            " ".join(filter(None, [a.findtext("ForeName"), a.findtext("LastName")]))
            for a in articolo.findall(".//AuthorList/Author")
        ]
        paper.append(PaperGrezzo(
            titolo=_testo(articolo.find(".//ArticleTitle")),
            fonte="pubmed",
            abstract=" ".join(sezioni),
            autori=[a for a in autori if a][:30],
            data_pubblicazione=_data(articolo),
            doi=ids.get("doi") or None,
            pmid=pmid,
            pmcid=ids.get("pmc") or None,
            sede=articolo.findtext(".//Journal/Title") or "",
            stato="rivista",
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        ))
    return paper


class PubMed:
    nome = "pubmed"

    def __init__(self, email: str = "", timeout: float = 25, tentativi: int = 3):
        self.comuni = {"tool": "paper-radar", **({"email": email} if email else {})}
        self.timeout = timeout
        self.tentativi = tentativi

    def pagine(self, opzioni: dict, dal: str, al: str) -> Iterator[list[PaperGrezzo]]:
        giorni = max((date.fromisoformat(al) - date.fromisoformat(dal)).days, 1)
        inizio = 0
        while True:
            ricerca = richiesta(f"{BASE}/esearch.fcgi", params={
                **self.comuni, "db": "pubmed", "term": opzioni["query"],
                "reldate": giorni, "datetype": "edat",      # edat = data di ingresso in PubMed
                "retmax": 40, "retstart": inizio, "retmode": "json",
            }, timeout=self.timeout, tentativi=self.tentativi).json()
            pmid = (ricerca.get("esearchresult") or {}).get("idlist") or []
            if not pmid:
                return
            dettagli = richiesta(f"{BASE}/efetch.fcgi", params={
                **self.comuni, "db": "pubmed", "id": ",".join(pmid), "retmode": "xml",
            }, timeout=self.timeout, tentativi=self.tentativi)
            yield [p for p in analizza_xml(dettagli.text) if p.abstract]
            inizio += 40
