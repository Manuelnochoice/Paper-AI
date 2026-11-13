"""Costruzione del grafo dei paper collegati.

Gli archi nascono solo da dati reali:
- "cita"      : citazioni e riferimenti presi da OpenAlex;
- "correlato" : paper correlati secondo OpenAlex;
- "simile"    : similarità tra abstract, calcolata in locale con TF-IDF
                (scritto qui sotto in Python puro, senza librerie esterne).
Il modello linguistico non decide nessun arco.

Questo modulo produce solo dati (nodi e archi); il disegno è in ui/componenti.py.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from paper_radar.dati import db

# Parole inglesi molto comuni, che non dicono nulla sull'argomento di un paper.
PAROLE_VUOTE = frozenset("""
the and for are was were with that this from have has had not but can will which their its our
been also than then these those such into over under between both more most other some any each
via using used use based show shows shown showed study studies paper results result method methods
approach propose proposed present presented new novel however while where when what how may might
could would should across among within without after before during about against through there here
they them his her she him who whom all one two three first second well due per out upon only very
""".split())


def parole(testo: str) -> list[str]:
    """Le parole significative di un testo: minuscole, almeno 3 lettere, non "vuote"."""
    return [p for p in re.findall(r"[a-z][a-z0-9-]{2,}", testo.lower()) if p not in PAROLE_VUOTE]


def vettori_tfidf(testi: list[str]) -> list[dict[str, float]]:
    """Trasforma ogni testo in un vettore TF-IDF (dizionario parola -> peso).

    TF  (term frequency): quanto una parola è frequente NEL testo.
    IDF (inverse document frequency): quanto è rara NEGLI ALTRI testi.
    Una parola pesa molto se compare spesso in un testo ma in pochi testi:
    è così che "qubit" conta più di "analysis".
    Ogni vettore viene poi normalizzato a lunghezza 1, così il prodotto tra
    due vettori è direttamente la similarità del coseno (0 = nulla in comune,
    1 = testi identici).
    """
    conteggi = [Counter(parole(t)) for t in testi]
    in_quanti_testi = Counter(p for c in conteggi for p in c)       # document frequency
    n = len(testi)
    vettori = []
    for conteggio in conteggi:
        vettore = {
            p: (1 + math.log(frequenza)) * (math.log((1 + n) / (1 + in_quanti_testi[p])) + 1)
            for p, frequenza in conteggio.items()
        }
        lunghezza = math.sqrt(sum(peso * peso for peso in vettore.values())) or 1.0
        vettori.append({p: peso / lunghezza for p, peso in vettore.items()})
    return vettori


def coseno(a: dict[str, float], b: dict[str, float]) -> float:
    """Similarità del coseno tra due vettori già normalizzati."""
    if len(a) > len(b):
        a, b = b, a                      # scorre il più corto: meno confronti
    return sum(peso * b.get(p, 0.0) for p, peso in a.items())


def piu_simili(corpus: list[dict], paper_id: int, soglia: float, massimo: int) -> list[tuple[int, float]]:
    """I paper con l'abstract più simile a quello dato: lista di (id, similarità)."""
    ids = [p["id"] for p in corpus]
    if paper_id not in ids or len(corpus) < 2:
        return []
    vettori = vettori_tfidf([f"{p['titolo']}. {p['abstract']}" for p in corpus])
    centro = vettori[ids.index(paper_id)]

    candidati = []
    for altro_id, vettore in zip(ids, vettori):
        if altro_id != paper_id:
            punteggio = coseno(centro, vettore)
            if punteggio >= soglia:
                candidati.append((altro_id, punteggio))
    candidati.sort(key=lambda coppia: coppia[1], reverse=True)
    return candidati[:massimo]


def costruisci_grafo(conn, paper_id: int, soglia: float = 0.15, max_simili: int = 8) -> dict:
    """Restituisce {"nodi": [...], "archi": [...]} per il paper indicato.

    Ogni nodo: id, titolo, anno, ruolo ("centro", "collegato" o "simile").
    Ogni arco: da, a, tipo ("cita", "correlato", "simile") e, per "simile", il peso.
    """
    centro = db.leggi_paper(conn, paper_id)
    nodi = {paper_id: {"id": paper_id, "titolo": centro["titolo"],
                       "anno": centro["data_pubblicazione"][:4], "ruolo": "centro"}}
    archi: list[dict] = []
    coppie_unite: set[frozenset] = set()

    # 1. Archi che toccano il paper centrale (citazioni e correlati da OpenAlex).
    for arco in db.collegamenti_di(conn, paper_id):
        nodi.setdefault(arco["altro_id"], {
            "id": arco["altro_id"], "titolo": arco["titolo"],
            "anno": (arco["data_pubblicazione"] or "")[:4], "ruolo": "collegato"})
        archi.append({"da": arco["da_id"], "a": arco["a_id"], "tipo": arco["tipo"]})
        coppie_unite.add(frozenset((arco["da_id"], arco["a_id"])))

    # 2. Archi tra i vicini (es. due riferimenti che si citano a vicenda).
    vicini = [i for i in nodi if i != paper_id]
    for arco in db.collegamenti_tra(conn, vicini):
        archi.append({"da": arco["da_id"], "a": arco["a_id"], "tipo": arco["tipo"]})
        coppie_unite.add(frozenset((arco["da_id"], arco["a_id"])))

    # 3. Archi di similarità tra abstract, solo dove non c'è già un altro arco.
    corpus = db.paper_con_abstract(conn)
    titoli = {p["id"]: p["titolo"] for p in corpus}
    for altro_id, peso in piu_simili(corpus, paper_id, soglia, max_simili):
        if frozenset((paper_id, altro_id)) in coppie_unite:
            continue
        if altro_id not in nodi:
            altro = db.leggi_paper(conn, altro_id)
            nodi[altro_id] = {"id": altro_id, "titolo": titoli[altro_id],
                              "anno": altro["data_pubblicazione"][:4], "ruolo": "simile"}
        archi.append({"da": paper_id, "a": altro_id, "tipo": "simile", "peso": round(peso, 2)})

    return {"nodi": list(nodi.values()), "archi": archi}
