"""Recupero del testo completo, quando è disponibile in modo legale.

Tre strade, nell'ordine:
- arXiv: il PDF è liberamente scaricabile;
- PubMed Central (PMC): gli articoli open access sono disponibili in XML
  tramite Europe PMC;
- qualunque altro paper per cui OpenAlex (o l'archivio di preprint) indica un
  PDF ad accesso aperto.
Se nessuna funziona (articolo a pagamento, sito che rifiuta i download
automatici, PDF fatto di sole immagini) si usa l'abstract, e la scheda lo dichiara.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET

from paper_radar.fonti.http import richiesta

LUNGHEZZA_MINIMA = 3000          # sotto questa soglia il "testo completo" non è credibile
MAX_PAGINE = 60                  # oltre è un libro o una tesi: bastano le prime pagine
MAX_BYTE_PDF = 30 * 1024 * 1024
# Alcuni siti rispondono solo se la richiesta dichiara un programma riconoscibile.
INTESTAZIONI = {"User-Agent": "PaperRadar/1.0 (app personale di lettura; Python requests)"}


def _testo_da_pdf(contenuto: bytes) -> str:
    """Estrae il testo da un PDF con pypdf (libreria in Python puro).

    Se pypdf non è installato si prova con PyMuPDF, se c'è.
    """
    if not contenuto.startswith(b"%PDF") or len(contenuto) > MAX_BYTE_PDF:
        return ""                # non è un PDF (spesso è una pagina web di blocco) o è enorme
    try:
        from pypdf import PdfReader
        lettore = PdfReader(io.BytesIO(contenuto))
        testo = "\n".join((pagina.extract_text() or "") for pagina in lettore.pages[:MAX_PAGINE])
    except ImportError:
        import fitz              # PyMuPDF
        with fitz.open(stream=contenuto, filetype="pdf") as documento:
            testo = "\n".join(pagina.get_text() for pagina in list(documento)[:MAX_PAGINE])
    # La bibliografia non serve all'analisi e occupa spazio: la tagliamo.
    posizioni = [m.start() for m in re.finditer(r"\n\s*(References|REFERENCES|Bibliography)\s*\n", testo)]
    if posizioni and posizioni[-1] > len(testo) * 0.5:
        testo = testo[:posizioni[-1]]
    return testo


def _testo_da_xml_pmc(xml: str) -> str:
    """Estrae corpo e note finali (finanziamenti, conflitti di interesse) dall'XML di PMC."""
    radice = ET.fromstring(xml)
    parti = []
    corpo = radice.find(".//body")
    if corpo is not None:
        parti.append(" ".join(corpo.itertext()))
    for fine in radice.findall(".//back"):
        for figlio in fine:
            if figlio.tag != "ref-list":             # salta la bibliografia
                parti.append(" ".join(figlio.itertext()))
    return re.sub(r"\s+", " ", " ".join(parti)).strip()


def _tentativi(paper: dict) -> list[tuple[str, str]]:
    """Elenco di (tipo, indirizzo) da provare per questo paper."""
    elenco = []
    if paper.get("arxiv_id"):
        elenco.append(("pdf", f"https://arxiv.org/pdf/{paper['arxiv_id']}"))
    if paper.get("pmcid"):
        elenco.append(("xml", f"https://www.ebi.ac.uk/europepmc/webservices/rest/{paper['pmcid']}/fullTextXML"))
    if paper.get("url_pdf") and not paper.get("arxiv_id"):
        elenco.append(("pdf", paper["url_pdf"]))
    return elenco


def recupera_testo(paper: dict, max_caratteri: int = 60000, timeout: float = 45) -> tuple[str, str]:
    """Restituisce (testo, base) dove base è "testo completo" oppure "abstract"."""
    for tipo, indirizzo in _tentativi(paper):
        try:
            risposta = richiesta(indirizzo, headers=INTESTAZIONI, timeout=timeout, tentativi=2)
            testo = _testo_da_pdf(risposta.content) if tipo == "pdf" else _testo_da_xml_pmc(risposta.text)
        except Exception:        # sito non raggiungibile, PDF rovinato...: si prova la strada successiva
            continue
        if len(testo) >= LUNGHEZZA_MINIMA:
            return testo[:max_caratteri], "testo completo"
    return paper.get("abstract") or "", "abstract"
