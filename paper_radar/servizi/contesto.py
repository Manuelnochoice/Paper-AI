"""Paper collegati: riferimenti, citazioni e correlati presi da OpenAlex.

Questi collegamenti alimentano sia la sezione "contesto" dell'analisi sia il
grafo. Nascono solo da dati reali di OpenAlex, mai dal modello.
"""
from __future__ import annotations

from datetime import datetime

from paper_radar.dati import db
from paper_radar.fonti.openalex import OpenAlex


def _completa_da_openalex(conn, paper: dict, openalex: OpenAlex) -> dict:
    """Se il paper arriva da un'altra fonte, cerca su OpenAlex id, riferimenti e correlati."""
    if paper["openalex_id"] and (paper["riferimenti"] or paper["correlati"]):
        return paper
    trovato = None
    if paper["openalex_id"]:
        risultati = openalex.per_id([paper["openalex_id"]])
        trovato = risultati[0] if risultati else None
    elif paper["doi"]:
        trovato = openalex.per_doi(paper["doi"])
    if trovato:
        db.salva_paper(conn, trovato, origine=paper["origine"])     # completa i campi mancanti
        paper = db.leggi_paper(conn, paper["id"])
    return paper


def aggiorna_collegamenti(conn, paper_id: int, openalex: OpenAlex, impostazioni: dict) -> int:
    """Scarica da OpenAlex i paper collegati e salva gli archi. Restituisce quanti ne ha trovati."""
    limiti = impostazioni["contesto"]
    paper = _completa_da_openalex(conn, db.leggi_paper(conn, paper_id), openalex)
    adesso = datetime.now().isoformat(timespec="seconds")
    if not paper["openalex_id"]:
        # Capita con i preprint appena usciti: OpenAlex non li ha ancora indicizzati.
        db.aggiorna_campi(conn, paper_id, collegamenti_il=adesso)
        return 0

    trovati = 0

    # 1. Paper citati (riferimenti). Ne chiediamo fino a 50 e teniamo i più citati:
    #    sono di solito i lavori di riferimento del settore.
    riferimenti = openalex.per_id(paper["riferimenti"][:50]) if paper["riferimenti"] else []
    riferimenti.sort(key=lambda p: p.n_citazioni or 0, reverse=True)
    for collegato in riferimenti[:limiti["max_riferimenti"]]:
        altro_id, _ = db.salva_paper(conn, collegato, origine="collegato")
        db.salva_collegamento(conn, paper_id, altro_id, "cita")
        trovati += 1

    # 2. Paper correlati secondo OpenAlex.
    ids_correlati = paper["correlati"][:limiti["max_correlati"]]
    for collegato in (openalex.per_id(ids_correlati) if ids_correlati else []):
        altro_id, _ = db.salva_paper(conn, collegato, origine="collegato")
        db.salva_collegamento(conn, paper_id, altro_id, "correlato")
        trovati += 1

    # 3. Paper che citano questo (per i paper recenti spesso non ce ne sono ancora).
    for collegato in openalex.citanti(paper["openalex_id"], limiti["max_citanti"]):
        altro_id, _ = db.salva_paper(conn, collegato, origine="collegato")
        db.salva_collegamento(conn, altro_id, paper_id, "cita")
        trovati += 1

    db.aggiorna_campi(conn, paper_id, collegamenti_il=adesso)
    return trovati


def descrivi_relazione(arco: dict, paper_id: int) -> str:
    """Spiega a parole un arco dal punto di vista del paper aperto."""
    if arco["tipo"] == "correlato":
        return "correlato secondo OpenAlex"
    return "citato dal paper" if arco["da_id"] == paper_id else "cita il paper"


def collegati(conn, paper_id: int) -> list[dict]:
    """Paper collegati, ognuno con la descrizione della relazione (senza doppioni)."""
    visti, elenco = set(), []
    for arco in db.collegamenti_di(conn, paper_id):
        if arco["altro_id"] in visti:
            continue
        visti.add(arco["altro_id"])
        elenco.append({**arco, "relazione": descrivi_relazione(arco, paper_id)})
    return elenco
