"""Verifica delle citazioni testuali.

Il modello deve sostenere ogni affermazione con una frase copiata dal paper.
Qui controlliamo, con semplice codice, che quella frase esista davvero nel
testo: è una difesa concreta contro le citazioni inventate.
"""
from __future__ import annotations

import re
import unicodedata

VERIFICATA = "verificata"            # la frase c'è, identica
APPROSSIMATA = "approssimata"        # la frase c'è quasi tutta (piccole differenze)
NON_VERIFICATA = "non verificata"    # la frase non è stata trovata


def normalizza(testo: str) -> str:
    """Riduce il testo a parole minuscole separate da uno spazio.

    Così non contano maiuscole, punteggiatura, virgolette tipografiche,
    ritorni a capo o parole spezzate dal trattino a fine riga.
    """
    testo = unicodedata.normalize("NFKC", testo or "").lower()
    testo = re.sub(r"-\s*\n\s*", "", testo)             # "experi-\nment" -> "experiment"
    return " ".join(re.findall(r"[a-z0-9à-ÿ]+", testo))


def verifica_citazione(citazione: str | None, testo_normalizzato: str) -> str | None:
    """Confronta una citazione con il testo (già normalizzato) del paper."""
    if not citazione or not citazione.strip():
        return None
    frase = normalizza(citazione)
    if not frase:
        return None
    if frase in testo_normalizzato:
        return VERIFICATA

    # Confronto "morbido": dividiamo la citazione in gruppi di 4 parole consecutive
    # e contiamo quanti compaiono nel testo. Se sono almeno il 70% la citazione è
    # sostanzialmente presente (es. il modello ha saltato una parola o una formula).
    parole = frase.split()
    if len(parole) < 6:
        return NON_VERIFICATA
    gruppi = [" ".join(parole[i:i + 4]) for i in range(len(parole) - 3)]
    presenti = sum(1 for g in gruppi if g in testo_normalizzato)
    return APPROSSIMATA if presenti / len(gruppi) >= 0.7 else NON_VERIFICATA


def verifica_tutte(dati, testo_normalizzato: str) -> dict[str, int]:
    """Percorre tutta l'analisi e compila il campo "verifica" accanto a ogni citazione.

    Restituisce il conteggio per esito, es. {"verificata": 9, "non verificata": 1}.
    """
    conteggio: dict[str, int] = {}

    def visita(nodo):
        if isinstance(nodo, dict):
            if "citazione" in nodo:
                esito = verifica_citazione(nodo.get("citazione"), testo_normalizzato)
                nodo["verifica"] = esito
                if esito:
                    conteggio[esito] = conteggio.get(esito, 0) + 1
            for valore in nodo.values():
                visita(valore)
        elif isinstance(nodo, list):
            for elemento in nodo:
                visita(elemento)

    visita(dati)
    return conteggio
