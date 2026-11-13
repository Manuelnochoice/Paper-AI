"""Raccolta dei paper recenti dalle fonti configurate per ogni area.

Il problema da evitare: vedere sempre gli stessi paper. La soluzione ha due parti:
1. ogni paper trovato viene salvato nel database e riconosciuto se ricompare;
2. se la prima pagina di una fonte contiene solo paper già noti, si passa alle
   pagine successive finché non si trovano abbastanza paper davvero nuovi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from paper_radar import config
from paper_radar.dati import db
from paper_radar.fonti.arxiv import Arxiv
from paper_radar.fonti.biorxiv import BioRxiv
from paper_radar.fonti.chemrxiv import PREFISSO_DOI, ChemRxiv
from paper_radar.fonti.http import ErroreFonte
from paper_radar.fonti.openalex import OpenAlex
from paper_radar.fonti.pubmed import PubMed
from paper_radar.modelli import PaperGrezzo

LUNGHEZZA_MINIMA_ABSTRACT = 100     # senza abstract un paper non si può analizzare


@dataclass
class EsitoRaccolta:
    area: str
    trovati: int = 0                 # paper recenti restituiti dalle fonti
    nuovi: int = 0                   # di cui mai visti prima
    errori: list[str] = field(default_factory=list)


def crea_fonti(impostazioni: dict) -> dict:
    """Crea un oggetto per ogni fonte, con timeout e tentativi dalla configurazione."""
    r = impostazioni["raccolta"]
    comuni = {"timeout": r["timeout_secondi"], "tentativi": r["tentativi"]}
    return {
        "openalex": OpenAlex(config.chiave("OPENALEX_API_KEY"), **comuni),
        "arxiv": Arxiv(**comuni),
        "pubmed": PubMed(email=r.get("email_contatto", ""), **comuni),
        "biorxiv": BioRxiv("biorxiv", **comuni),
        "medrxiv": BioRxiv("medrxiv", **comuni),
        "chemrxiv": ChemRxiv(timeout=r["timeout_secondi"]),
    }


def _salva_pagine(conn, pagine: Iterable[list[PaperGrezzo]], area: str, dal: str, al: str,
                  max_nuovi: int, max_pagine: int, esito: EsitoRaccolta) -> None:
    """Scorre le pagine di una fonte salvando i paper, finché trova abbastanza novità."""
    nuovi_da_questa_fonte = 0
    for numero, pagina in enumerate(pagine):
        if numero >= max_pagine:
            return
        for paper in pagina:
            recente = dal <= paper.data_pubblicazione <= al
            if not (recente and paper.titolo and len(paper.abstract) >= LUNGHEZZA_MINIMA_ABSTRACT):
                continue
            esito.trovati += 1
            _, nuovo = db.salva_paper(conn, paper, area=area, origine="feed")
            if nuovo:
                esito.nuovi += 1
                nuovi_da_questa_fonte += 1
                if nuovi_da_questa_fonte >= max_nuovi:
                    return


def raccogli_area(conn, area_id: str, config_area: dict, fonti: dict, impostazioni: dict,
                  oggi: date | None = None) -> EsitoRaccolta:
    """Raccoglie i paper recenti di un'area da tutte le sue fonti.

    Se una fonte fallisce le altre proseguono: l'errore viene annotato in
    `esito.errori` con un messaggio comprensibile.
    """
    r = impostazioni["raccolta"]
    oggi = oggi or date.today()
    dal, al = (oggi - timedelta(days=r["giorni"])).isoformat(), oggi.isoformat()
    esito = EsitoRaccolta(area=area_id)
    limiti = dict(max_nuovi=r["max_nuovi_per_fonte"], max_pagine=r["max_pagine"])

    for nome, opzioni in (config_area.get("fonti") or {}).items():
        fonte = fonti.get(nome)
        if fonte is None:
            esito.errori.append(f"{nome}: fonte non riconosciuta (controlla config/aree.yaml)")
            continue
        try:
            _salva_pagine(conn, fonte.pagine(opzioni or {}, dal, al), area_id, dal, al, esito=esito, **limiti)
        except ErroreFonte as e:
            if nome == "chemrxiv" and "openalex" in fonti:
                # Ripiego: i preprint ChemRxiv si trovano anche su OpenAlex tramite il prefisso del DOI.
                try:
                    pagine = fonti["openalex"].pagine_doi_prefisso(PREFISSO_DOI, dal, al)
                    _salva_pagine(conn, pagine, area_id, dal, al, esito=esito, **limiti)
                except ErroreFonte as e2:
                    esito.errori.append(str(e2))
            else:
                esito.errori.append(str(e))
        except Exception as e:      # formato inatteso: non deve bloccare le altre fonti
            esito.errori.append(f"{nome}: risposta in un formato inatteso ({type(e).__name__})")
    return esito
