"""Pezzi riutilizzabili dell'interfaccia: schede dei paper e tabelle."""
from __future__ import annotations

import streamlit as st

from paper_radar.dati import db
from paper_radar.modelli import ETICHETTE_STATO

SIMBOLI_VERIFICA = {
    "verificata": "✅ citazione trovata nel testo",
    "approssimata": "🟡 citazione trovata con piccole differenze",
    "non verificata": "⚠️ citazione NON trovata nel testo: trattala con cautela",
}


def accorcia(testo: str, lunghezza: int) -> str:
    testo = testo or ""
    return testo if len(testo) <= lunghezza else testo[:lunghezza - 1].rstrip() + "…"


def in_italiano() -> bool:
    """True se l'interruttore "Testo in italiano" è acceso."""
    return bool(st.session_state.get("in_italiano"))


def titolo_da_mostrare(paper: dict) -> str:
    return paper["titolo_it"] if in_italiano() and paper.get("titolo_it") else paper["titolo"]


def abstract_da_mostrare(paper: dict) -> str:
    return paper["abstract_it"] if in_italiano() and paper.get("abstract_it") else paper["abstract"]


def autori_brevi(autori: list[str]) -> str:
    if not autori:
        return "Autori non indicati"
    return ", ".join(autori[:3]) + (" e altri" if len(autori) > 3 else "")


# ---------------------------------------------------------------- navigazione
# Le funzioni qui sotto sono "callback": Streamlit le esegue quando si preme
# un pulsante, prima di ridisegnare la pagina.

def apri_paper(paper_id: int) -> None:
    st.session_state["storia"].append(st.session_state.get("paper_id"))
    st.session_state["paper_id"] = paper_id


def torna_indietro() -> None:
    storia = st.session_state["storia"]
    st.session_state["paper_id"] = storia.pop() if storia else None


def cambia_da_leggere(conn, paper_id: int) -> None:
    if db.nota_da_leggere(conn, paper_id) is None:
        db.salva_da_leggere(conn, paper_id)
    else:
        db.rimuovi_da_leggere(conn, paper_id)


# ---------------------------------------------------------------- schede

def riga_dettagli(paper: dict, nomi_aree: dict) -> str:
    """Riga grigia sotto il titolo: autori, data, sede, stato, aree."""
    parti = [autori_brevi(paper["autori"]), paper["data_pubblicazione"] or "data n.d."]
    if paper.get("sede"):
        parti.append(paper["sede"])
    parti.append(ETICHETTE_STATO.get(paper["stato"], paper["stato"]).split(" (")[0])
    aree = paper.get("aree") or (paper.get("aree_testo") or "").split(",")
    parti += [nomi_aree.get(a, a) for a in aree if a]
    return " · ".join(parti)


def scheda_paper(conn, paper: dict, nomi_aree: dict, prefisso: str) -> None:
    """Riquadro di un paper nell'elenco, con i pulsanti principali."""
    pid = paper["id"]
    with st.container(border=True):
        testo, azioni = st.columns([5, 1.3])
        with testo:
            analizzato = " ✅" if paper.get("analizzato") else ""
            st.markdown(f"**{titolo_da_mostrare(paper)}**{analizzato}")
            if titolo_da_mostrare(paper) != paper["titolo"]:
                st.caption(f"Titolo originale: {paper['titolo']}")
            st.caption(riga_dettagli(paper, nomi_aree))
            st.write(accorcia(abstract_da_mostrare(paper), 320))
            if paper.get("note"):
                st.info(f"📝 {paper['note']}")
        with azioni:
            st.button("Apri", key=f"{prefisso}_apri_{pid}", type="primary", width="stretch",
                      on_click=apri_paper, args=(pid,))
            salvato = db.nota_da_leggere(conn, pid) is not None
            st.button("★ Salvato" if salvato else "☆ Da leggere", key=f"{prefisso}_salva_{pid}",
                      width="stretch", on_click=cambia_da_leggere, args=(conn, pid))
            if not paper.get("analizzato"):
                in_coda = db.in_coda(conn, pid)
                st.button("In coda ✓" if in_coda else "Metti in coda", key=f"{prefisso}_coda_{pid}",
                          width="stretch", disabled=in_coda, on_click=db.metti_in_coda, args=(conn, pid))


def citazione(voce: dict) -> None:
    """Mostra la citazione testuale e l'esito della verifica automatica."""
    if voce.get("citazione"):
        st.markdown(f"> «{voce['citazione']}»")
        st.caption(SIMBOLI_VERIFICA.get(voce.get("verifica"), ""))


# ---------------------------------------------------------------- tabelle
# Le tabelle sono scritte in Markdown, senza librerie aggiuntive.
# I grafici stanno in grafici.py.

def tabella(righe: list[dict]) -> None:
    """Mostra una lista di dizionari come tabella (le chiavi sono le intestazioni)."""
    if not righe:
        return

    def cella(valore) -> str:
        # La barra verticale e i ritorni a capo romperebbero la tabella Markdown.
        return str(valore).replace("|", "/").replace("\n", " ")

    intestazioni = list(righe[0])
    linee = ["| " + " | ".join(intestazioni) + " |", "|" + "---|" * len(intestazioni)]
    linee += ["| " + " | ".join(cella(r[i]) for i in intestazioni) + " |" for r in righe]
    st.markdown("\n".join(linee))
