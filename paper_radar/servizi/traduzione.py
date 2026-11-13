"""Traduzione in italiano di titolo e abstract, per leggere gli elenchi più in fretta.

Per risparmiare richieste si traducono più paper per volta e ogni traduzione
viene salvata nel database: un paper non viene mai tradotto due volte.
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from paper_radar.dati import db
from paper_radar.llm.llm_client import LLMClient

ISTRUZIONI = """Traduci in italiano il titolo e l'abstract di ciascun paper scientifico qui sotto.
Regole:
- traduzione fedele e scorrevole, senza aggiungere, togliere o commentare nulla;
- lascia invariati nomi propri, sigle, formule, numeri e i termini tecnici che in italiano si usano in inglese;
- se un testo è già in italiano, copialo com'è.
Rispondi con SOLO un oggetto JSON in questa forma, con un elemento per ogni paper e lo stesso "id":
{"traduzioni": [{"id": 1, "titolo": "...", "abstract": "..."}]}

PAPER:
"""


class PaperTradotto(BaseModel):
    id: int
    titolo: str
    abstract: str


class Traduzioni(BaseModel):
    traduzioni: list[PaperTradotto]


def traduci(conn, paper: list[dict], llm: LLMClient, per_richiesta: int = 6) -> int:
    """Traduce i paper dati (dizionari con id, titolo, abstract). Restituisce quanti ne ha tradotti."""
    tradotti = 0
    for inizio in range(0, len(paper), per_richiesta):
        gruppo = paper[inizio:inizio + per_richiesta]
        ingresso = [{"id": p["id"], "titolo": p["titolo"], "abstract": p["abstract"]} for p in gruppo]
        risposta = llm.genera_json(ISTRUZIONI + json.dumps(ingresso, ensure_ascii=False, indent=1), Traduzioni)
        richiesti = {p["id"] for p in gruppo}
        for voce in risposta.dati.traduzioni:
            # Si salvano solo le traduzioni dei paper davvero richiesti e non vuote.
            if voce.id in richiesti and voce.titolo.strip() and voce.abstract.strip():
                db.salva_traduzione(conn, voce.id, voce.titolo.strip(), voce.abstract.strip())
                tradotti += 1
    return tradotti
