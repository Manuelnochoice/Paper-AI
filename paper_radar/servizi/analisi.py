"""Analisi di un paper: il cuore dell'app.

Passi:
1. se l'analisi è già nel database la restituisce (non si rifà mai);
2. recupera i paper collegati da OpenAlex e il testo (completo o abstract);
3. chiede al modello un JSON con spiegazioni, affidabilità, contesto, glossario;
4. controlla il risultato con codice: citazioni, griglia, id dei collegamenti;
5. salva tutto nel database.
"""
from __future__ import annotations

from typing import Callable

from paper_radar.dati import db
from paper_radar.fonti.http import ErroreFonte
from paper_radar.llm.griglie import GRIGLIE
from paper_radar.llm.llm_client import LLMClient
from paper_radar.llm.prompt import VERSIONE_PROMPT, costruisci_prompt
from paper_radar.llm.schemi import NON_RILEVABILE, Analisi
from paper_radar.servizi import contesto as servizio_contesto
from paper_radar.servizi.citazioni import normalizza, verifica_tutte
from paper_radar.servizi.testo_completo import recupera_testo


class ErroreAnalisi(Exception):
    """Errore con messaggio adatto a essere mostrato all'utente."""


def completa_griglia(affidabilita: dict) -> None:
    """Fa sì che la griglia contenga tutti e soli i criteri previsti per il tipo di studio.

    I criteri che il modello ha dimenticato vengono aggiunti come "non rilevabile";
    quelli inventati vengono scartati.
    """
    previsti = GRIGLIE[affidabilita["tipo_studio"]]
    ricevuti = {normalizza(v["criterio"]): v for v in affidabilita["griglia"]}
    griglia = []
    for criterio in previsti:
        voce = ricevuti.get(normalizza(criterio))
        if voce is None:
            voce = {"criterio": criterio, "esito": NON_RILEVABILE,
                    "motivazione": "Criterio non valutato dal modello.", "citazione": None, "verifica": None}
        voce["criterio"] = criterio
        griglia.append(voce)
    affidabilita["griglia"] = griglia


def filtra_contesto(contesto: dict, collegati: list[dict]) -> None:
    """Tiene nel contesto solo i collegamenti verso paper realmente forniti da OpenAlex."""
    ammessi = {c["openalex_id"] for c in collegati}
    contesto["collegamenti"] = [c for c in contesto["collegamenti"] if c["id"] in ammessi]
    if not collegati:
        contesto["sintesi"] = NON_RILEVABILE


def analizza(conn, paper_id: int, llm: LLMClient, openalex, impostazioni: dict,
             avanzamento: Callable[[str], None] = lambda messaggio: None,
             solo_se_testo_completo: bool = False) -> dict:
    """Restituisce l'analisi del paper, creandola se non esiste ancora.

    `avanzamento` riceve brevi messaggi sullo stato ("Recupero il testo…"),
    che l'interfaccia mostra durante l'attesa.

    Un'analisi già salvata non viene mai rifatta, con una sola eccezione
    chiesta esplicitamente dall'utente: `solo_se_testo_completo=True` sostituisce
    un'analisi fatta sul solo abstract, ma solo se ora si riesce a leggere il
    testo completo (altrimenti si ferma prima di usare richieste del modello).
    """
    esistente = db.leggi_analisi(conn, paper_id)
    if esistente and not solo_se_testo_completo:
        return esistente

    paper = db.leggi_paper(conn, paper_id)
    avvisi: list[str] = []

    if paper["collegamenti_il"] is None:
        avanzamento("Cerco i paper collegati su OpenAlex…")
        try:
            servizio_contesto.aggiorna_collegamenti(conn, paper_id, openalex, impostazioni)
            paper = db.leggi_paper(conn, paper_id)
        except ErroreFonte as e:
            avvisi.append(f"Paper collegati non recuperati ({e}).")

    avanzamento("Recupero il testo del paper…")
    testo, base_testo = recupera_testo(paper, impostazioni["llm"]["max_caratteri_testo"])
    if len(testo) < 100:
        raise ErroreAnalisi("Questo paper non ha un abstract né un testo disponibile: non si può analizzare.")
    if solo_se_testo_completo and base_testo != "testo completo":
        raise ErroreAnalisi("Il testo completo non è disponibile ad accesso aperto (o il sito non permette "
                            "di scaricarlo): resta valida l'analisi sull'abstract. Nessuna richiesta usata.")

    collegati = [c for c in servizio_contesto.collegati(conn, paper_id) if c["openalex_id"]]
    prompt = costruisci_prompt(paper, testo, base_testo, collegati)

    avanzamento("Chiedo l'analisi al modello (può richiedere fino a un minuto)…")
    risposta = llm.genera_json(prompt, Analisi)

    avanzamento("Controllo citazioni e griglia…")
    contenuto = risposta.dati.model_dump()
    conteggio = verifica_tutte(contenuto, normalizza(testo))
    completa_griglia(contenuto["affidabilita"])
    filtra_contesto(contenuto["contesto"], collegati)
    contenuto["meta"] = {
        "versione_prompt": VERSIONE_PROMPT,
        "paper_collegati_forniti": len(collegati),
        "verifica_citazioni": conteggio,
        "avvisi": avvisi,
    }

    db.salva_analisi(conn, paper_id, contenuto, risposta.modello, base_testo)
    return db.leggi_analisi(conn, paper_id)
