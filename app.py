"""Paper Radar: punto di ingresso dell'app Streamlit.

Avvio:  streamlit run app.py

Questo file contiene solo la barra laterale e la scelta della pagina;
le pagine sono in paper_radar/ui/pagine.py.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from streamlit import config as configurazione_streamlit

st.set_page_config(page_title="Paper Radar", page_icon="🔭", layout="wide")


# ---------------------------------------------------------------- ricarica del codice
# Streamlit rilegge questo file a ogni ridisegno, ma tiene in memoria i moduli
# importati. Di solito si accorge da solo quando un file cambia; nelle cartelle
# sincronizzate (OneDrive) a volte no. Questo controllo lo fa in modo esplicito:
# se un file del progetto è stato modificato, i moduli vengono ricaricati.

@st.cache_resource
def _memoria_codice() -> dict:
    return {"impronta": None}


def _impronta_codice() -> float:
    """Data di modifica più recente tra i file Python e di configurazione del progetto."""
    radice = Path(__file__).parent
    file = list((radice / "paper_radar").rglob("*.py")) + list((radice / "config").glob("*.yaml"))
    return max(f.stat().st_mtime for f in file)


_impronta = _impronta_codice()
if _memoria_codice()["impronta"] != _impronta:
    for nome in [n for n in sys.modules if n.startswith("paper_radar")]:
        del sys.modules[nome]
    st.cache_resource.clear()
    st.cache_data.clear()
_memoria_codice()["impronta"] = _impronta

from paper_radar import config                                        # noqa: E402
from paper_radar.dati import db                                       # noqa: E402
from paper_radar.llm.llm_client import GeminiProvider, LLMClient      # noqa: E402
from paper_radar.servizi.raccolta import crea_fonti, raccogli_area    # noqa: E402
from paper_radar.ui import pagine                                     # noqa: E402

SEZIONI = ["Novità", "Archivio", "Da leggere", "Coda di analisi", "Glossario"]


@st.cache_resource
def risorse() -> dict:
    """Oggetti creati una volta sola e riusati a ogni ridisegno della pagina."""
    impostazioni = config.carica_impostazioni()
    aree = config.carica_aree()
    conn = db.connetti(config.percorso_database(impostazioni))

    llm = llm_traduzione = None
    chiave_gemini = config.chiave("GEMINI_API_KEY")
    if chiave_gemini:
        opzioni = impostazioni["llm"]
        provider = GeminiProvider(chiave_gemini, opzioni["temperatura"])
        contatore = db.ContatoreSQLite(conn)
        comuni = dict(tentativi_json=opzioni["tentativi_json"], tentativi_429=opzioni["tentativi_429"])
        llm = LLMClient(provider, opzioni["modelli"], contatore, **comuni)
        # Le traduzioni usano solo il modello leggero, per non consumare la quota delle analisi.
        leggero = [m for m in opzioni["modelli"] if m["nome"] == impostazioni["traduzione"]["modello"]]
        if leggero:
            llm_traduzione = LLMClient(provider, leggero, contatore, **comuni)
    return {
        "impostazioni": impostazioni,
        "aree": aree,
        "nomi_aree": {codice: a["nome"] for codice, a in aree.items()},
        "conn": conn,
        "fonti": crea_fonti(impostazioni),
        "llm": llm,
        "llm_traduzione": llm_traduzione,
    }


def chiudi_paper() -> None:
    """Cambiando sezione si esce dalla pagina del paper."""
    st.session_state["paper_id"] = None
    st.session_state["storia"] = []


def applica_tema(scuro: bool) -> None:
    """Imposta il tema chiaro o scuro. Il cambio diventa visibile al ridisegno successivo."""
    voluto = "dark" if scuro else "light"
    if configurazione_streamlit.get_option("theme.base") != voluto:
        configurazione_streamlit.set_option("theme.base", voluto)
        st.rerun()


def salva_interruttore(conn, chiave: str) -> None:
    """Ricorda nel database la posizione di un interruttore della barra laterale."""
    db.salva_preferenza(conn, chiave, "1" if st.session_state[chiave] else "0")


def cerca_nuovi_paper(r: dict, aree_scelte: list[str], titolo: str = "Cerco") -> None:
    """Interroga le fonti per le aree scelte, mostrando l'avanzamento."""
    codici = aree_scelte or list(r["aree"])
    barra = st.sidebar.progress(0.0, text="Avvio la raccolta…")
    nuovi, errori = 0, []
    for n, codice in enumerate(codici):
        barra.progress(n / len(codici), text=f"{titolo}: {r['nomi_aree'][codice]} ({n + 1} di {len(codici)})")
        esito = raccogli_area(r["conn"], codice, r["aree"][codice], r["fonti"], r["impostazioni"])
        nuovi += esito.nuovi
        errori += esito.errori
    barra.empty()
    st.session_state["esito_raccolta"] = {"nuovi": nuovi, "errori": errori}


def raccolta_automatica(r: dict) -> None:
    """La prima volta che l'app viene aperta in un giorno, cerca da sola i nuovi paper."""
    oggi = date.today().isoformat()
    if not r["impostazioni"]["raccolta"].get("automatica", True):
        return
    if db.leggi_preferenza(r["conn"], "raccolta_automatica") == oggi:
        return
    # Si segna subito la data: se la pagina viene ricaricata a metà, la raccolta non riparte.
    db.salva_preferenza(r["conn"], "raccolta_automatica", oggi)
    with st.spinner("Raccolta automatica di oggi: cerco i nuovi paper in tutte le aree (qualche minuto)…"):
        cerca_nuovi_paper(r, [], titolo="Raccolta di oggi")


def barra_laterale(r: dict) -> tuple[str, dict]:
    """Disegna la barra laterale. Restituisce la sezione scelta e i filtri."""
    conn = r["conn"]
    barra = st.sidebar
    barra.title("🔭 Paper Radar")
    sezione = barra.radio("Sezione", SEZIONI, key="sezione", on_change=chiudi_paper, label_visibility="collapsed")

    barra.subheader("Filtri")
    aree_scelte = barra.multiselect("Aree", list(r["aree"]), format_func=r["nomi_aree"].get,
                                    placeholder="Tutte le aree")
    oggi = date.today()
    periodo = barra.date_input("Pubblicati tra", value=(oggi - timedelta(days=30), oggi), format="DD/MM/YYYY")
    testo = barra.text_input("Parola chiave", placeholder="nel titolo o nell'abstract")

    if barra.button("🔄 Cerca nuovi paper", type="primary", width="stretch",
                    help="Interroga le fonti per le aree scelte (tutte, se non ne scegli nessuna)."):
        cerca_nuovi_paper(r, aree_scelte)
    esito = st.session_state.get("esito_raccolta")
    if esito:
        if esito["nuovi"]:
            barra.success(f"{esito['nuovi']} nuovi paper trovati.")
        else:
            barra.info("Nessun paper nuovo rispetto a quelli già visti.")
        if esito["errori"]:
            with barra.expander(f"⚠️ {len(esito['errori'])} fonti con problemi"):
                for errore in esito["errori"]:
                    st.write(f"- {errore}")

    barra.subheader("Aspetto")
    barra.toggle("Testo in italiano", key="in_italiano", on_change=salva_interruttore, args=(conn, "in_italiano"),
                 help="Traduce titolo e abstract negli elenchi. Usa il modello leggero, un gruppo di paper per richiesta.")
    barra.toggle("Tema scuro", key="tema_scuro", on_change=salva_interruttore, args=(conn, "tema_scuro"))

    barra.subheader("Richieste rimaste oggi")
    if r["llm"] is None:
        barra.warning("Manca GEMINI_API_KEY nel file .env")
    else:
        for quota in r["llm"].quote():
            barra.progress(quota["rimaste"] / max(quota["totale"], 1),
                           text=f"{quota['modello']}: {quota['rimaste']} di {quota['totale']}")
        barra.caption("Conteggio locale; i limiti si impostano in config/impostazioni.yaml.")
    if not config.chiave("OPENALEX_API_KEY"):
        barra.warning("Manca OPENALEX_API_KEY nel file .env: OpenAlex risponderà solo a poche richieste.")

    # Il selettore delle date restituisce una sola data finché non si sceglie la seconda.
    dal, al = (periodo if len(periodo) == 2 else (periodo[0], oggi)) if isinstance(periodo, tuple) else (periodo, oggi)
    filtri = {"aree": aree_scelte, "dal": dal.isoformat(), "al": al.isoformat(), "testo": testo}
    return sezione, filtri


def main() -> None:
    r = risorse()
    conn = r["conn"]
    st.session_state.setdefault("paper_id", None)
    st.session_state.setdefault("storia", [])
    # Gli interruttori partono dalla posizione salvata l'ultima volta.
    st.session_state.setdefault("in_italiano", db.leggi_preferenza(conn, "in_italiano", "1") == "1")
    st.session_state.setdefault("tema_scuro", db.leggi_preferenza(conn, "tema_scuro", "0") == "1")
    applica_tema(st.session_state["tema_scuro"])

    # Un clic su un nodo del grafo ricarica la pagina con "?paper=<id>" nell'indirizzo.
    richiesto = st.query_params.get("paper", "")
    if richiesto.isdigit():
        st.session_state["paper_id"] = int(richiesto)
        st.query_params.clear()

    raccolta_automatica(r)
    sezione, filtri = barra_laterale(r)

    if st.session_state["paper_id"] is not None:
        pagine.pagina_paper(r, st.session_state["paper_id"])
    elif sezione == "Novità":
        pagine.pagina_elenco(r, "novita", filtri)
    elif sezione == "Archivio":
        pagine.pagina_elenco(r, "archivio", filtri)
    elif sezione == "Da leggere":
        pagine.pagina_da_leggere(r)
    elif sezione == "Coda di analisi":
        pagine.pagina_coda(r)
    else:
        pagine.pagina_glossario(r)


main()
