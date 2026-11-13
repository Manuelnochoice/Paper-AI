"""Le pagine dell'app: elenchi, pagina del paper, coda, glossario."""
from __future__ import annotations

from collections import Counter

import streamlit as st

from paper_radar.dati import db
from paper_radar.fonti.http import ErroreFonte
from paper_radar.llm.llm_client import ErroreLLM
from paper_radar.llm.schemi import NON_RILEVABILE
from paper_radar.modelli import ETICHETTE_STATO
from paper_radar.servizi import contesto as servizio_contesto
from paper_radar.servizi.analisi import ErroreAnalisi, analizza
from paper_radar.servizi.grafo import costruisci_grafo
from paper_radar.servizi.traduzione import traduci
from paper_radar.ui import componenti as ui
from paper_radar.ui import grafici, grafo_interattivo

SIMBOLI_ESITO = {"sì": "🟢 sì", "parziale": "🟡 parziale", "no": "🔴 no", NON_RILEVABILE: "⚪ non rilevabile"}


@st.cache_data(show_spinner=False)
def _grafo(_conn, paper_id: int, soglia: float, max_simili: int, impronta: tuple) -> dict:
    """Grafo di un paper, tenuto in memoria finché il database non cambia.

    Streamlit ridisegna la pagina a ogni clic: senza questa memoria il grafo
    verrebbe ricalcolato ogni volta. `impronta` cambia quando arrivano nuovi
    paper o collegamenti, e fa scattare il ricalcolo. Il trattino basso in
    `_conn` dice a Streamlit di non usare quel parametro come chiave.
    """
    return costruisci_grafo(_conn, paper_id, soglia, max_simili)


# ================================================================ elenchi

def pagina_elenco(r: dict, vista: str, filtri: dict) -> None:
    """Novità oppure Archivio: elenco di schede con 'Mostra altri'."""
    conn = r["conn"]
    titolo = "Novità" if vista == "novita" else "Archivio"
    st.header(titolo)
    if vista == "novita":
        st.caption("Paper mai visti prima. Da domani quelli che vedi qui passano in Archivio.")
    else:
        st.caption("Paper già comparsi tra le novità nei giorni scorsi.")

    limite = st.session_state.setdefault(f"limite_{vista}", 20)
    paper = db.elenca_paper(conn, vista, limite=limite + 1, **filtri)
    if not paper:
        if vista == "novita":
            st.info("Nessuna novità con questi filtri. Premi **Cerca nuovi paper** nella barra laterale "
                    "per interrogare le fonti, oppure allarga le date.")
        else:
            st.info("L'archivio è vuoto con questi filtri.")
        return

    _panoramica(r, filtri)
    if _traduci_mancanti(r, paper[:limite]):
        paper = db.elenca_paper(conn, vista, limite=limite + 1, **filtri)      # rilegge con le traduzioni

    for p in paper[:limite]:
        ui.scheda_paper(conn, p, r["nomi_aree"], prefisso=vista)
    if vista == "novita":
        db.segna_mostrati(conn, [p["id"] for p in paper[:limite]])

    if len(paper) > limite:
        if st.button("Mostra altri 20", width="stretch"):
            st.session_state[f"limite_{vista}"] += 20
            st.rerun()


def _traduci_mancanti(r: dict, paper: list[dict]) -> bool:
    """Traduce in italiano i paper dell'elenco che non lo sono ancora. True se ne ha tradotti."""
    mancanti = [p for p in paper if not p.get("titolo_it")]
    if not (ui.in_italiano() and mancanti and r["llm_traduzione"]):
        return False
    try:
        with st.spinner(f"Traduco in italiano {len(mancanti)} paper (solo la prima volta che compaiono)…"):
            return traduci(r["conn"], mancanti, r["llm_traduzione"],
                           r["impostazioni"]["traduzione"]["paper_per_richiesta"]) > 0
    except ErroreLLM as e:
        st.caption(f"Traduzione non riuscita, mostro il testo originale. {e}")
        return True          # alcuni gruppi possono essere stati tradotti prima dell'errore


def _panoramica(r: dict, filtri: dict) -> None:
    """Due grafici sulla raccolta: paper per area e per giorno di pubblicazione."""
    numeri = db.conteggi_feed(r["conn"], filtri["dal"])
    if not numeri["per_giorno"]:
        return
    with st.expander("📊 Panoramica della raccolta"):
        sinistra, destra = st.columns(2)
        with sinistra:
            st.caption("Paper per area")
            grafici.barre_orizzontali({r["nomi_aree"].get(a, a): n for a, n in numeri["per_area"].items()})
        with destra:
            st.caption("Paper per giorno di pubblicazione")
            grafici.colonne({giorno[8:] + "/" + giorno[5:7]: n for giorno, n in numeri["per_giorno"].items()}, larghezza=460)


def pagina_da_leggere(r: dict) -> None:
    st.header("Da leggere")
    paper = db.elenca_da_leggere(r["conn"])
    _traduci_mancanti(r, paper)
    paper = db.elenca_da_leggere(r["conn"])
    if not paper:
        st.info("Non hai ancora salvato nessun paper. Usa il pulsante **☆ Da leggere** su una scheda.")
    for p in paper:
        ui.scheda_paper(r["conn"], p, r["nomi_aree"], prefisso="leggere")


def pagina_glossario(r: dict) -> None:
    st.header("Glossario")
    st.caption("Tutti i termini tecnici raccolti dai paper che hai analizzato.")
    ricerca = st.text_input("Cerca un termine", placeholder="es. entropia")
    voci = db.cerca_glossario(r["conn"], ricerca)
    if not voci:
        st.info("Nessun termine trovato. Il glossario si riempie a ogni paper analizzato.")
    for i, v in enumerate(voci):
        with st.container(border=True):
            st.markdown(f"**{v['termine']}** — {v['definizione']}")
            st.button(f"Dal paper: {ui.accorcia(v['titolo'], 90)}", key=f"gloss_{i}", type="tertiary",
                      on_click=ui.apri_paper, args=(v["paper_id"],))


# ================================================================ coda

def pagina_coda(r: dict) -> None:
    conn = r["conn"]
    st.header("Coda di analisi")
    st.caption("I paper in coda vengono analizzati uno alla volta, rispettando i limiti del piano gratuito.")
    coda = db.elenca_coda(conn)
    if not coda:
        st.info("La coda è vuota. Usa **Metti in coda** su una scheda per aggiungere un paper.")
        return

    for voce in coda:
        with st.container(border=True):
            testo, azioni = st.columns([6, 1])
            testo.markdown(f"**{voce['titolo']}**")
            if voce["errore"]:
                testo.warning(f"Ultimo tentativo non riuscito: {voce['errore']}")
            azioni.button("Togli", key=f"togli_{voce['id']}", width="stretch",
                          on_click=db.togli_dalla_coda, args=(conn, voce["id"]))

    if r["llm"] is None:
        st.error("Manca GEMINI_API_KEY nel file .env: non posso analizzare.")
        return
    if st.button(f"Elabora la coda ({len(coda)} paper)", type="primary"):
        barra = st.progress(0.0, text="Avvio…")
        riusciti = 0
        for n, voce in enumerate(coda):
            barra.progress(n / len(coda), text=f"Analizzo {n + 1} di {len(coda)}: {ui.accorcia(voce['titolo'], 70)}")
            try:
                analizza(conn, voce["id"], r["llm"], r["fonti"]["openalex"], r["impostazioni"])
                riusciti += 1
            except (ErroreLLM, ErroreAnalisi) as e:
                db.segna_errore_coda(conn, voce["id"], str(e))
                if getattr(e, "quota_esaurita", False):     # inutile continuare con gli altri
                    st.warning("Quota di oggi esaurita: la coda riprenderà quando la riavvii domani.")
                    break
        barra.progress(1.0, text=f"Fatto: {riusciti} paper analizzati.")
        st.rerun()


# ================================================================ pagina del paper

def pagina_paper(r: dict, paper_id: int) -> None:
    conn = r["conn"]
    paper = db.leggi_paper(conn, paper_id)
    if paper is None:
        st.error("Paper non trovato.")
        return
    analisi = db.leggi_analisi(conn, paper_id)

    st.button("← Indietro", on_click=ui.torna_indietro)
    st.title(ui.titolo_da_mostrare(paper))
    if ui.titolo_da_mostrare(paper) != paper["titolo"]:
        st.caption(f"Titolo originale: {paper['titolo']}")
    st.caption(ui.riga_dettagli(paper, r["nomi_aree"]))

    # --- pulsanti principali
    colonne = st.columns([1.4, 1.4, 1.4, 1, 1, 2])
    vuole_analisi = False
    if analisi is None:
        vuole_analisi = colonne[0].button("🔎 Analizza ora", type="primary", width="stretch",
                                          disabled=r["llm"] is None,
                                          help="Usa 1 richiesta del piano gratuito (di più solo in caso di errori).")
        in_coda = db.in_coda(conn, paper_id)
        colonne[1].button("In coda ✓" if in_coda else "Metti in coda", width="stretch", disabled=in_coda,
                          on_click=db.metti_in_coda, args=(conn, paper_id))
    salvato = db.nota_da_leggere(conn, paper_id) is not None
    colonne[2].button("★ Salvato" if salvato else "☆ Da leggere", width="stretch",
                      on_click=ui.cambia_da_leggere, args=(conn, paper_id))
    if paper["url"]:
        colonne[3].link_button("Fonte ↗", paper["url"], width="stretch")
    if paper["url_pdf"]:
        colonne[4].link_button("PDF ↗", paper["url_pdf"], width="stretch")

    if salvato:
        with st.expander("📝 Le mie note", expanded=bool(db.nota_da_leggere(conn, paper_id))):
            note = st.text_area("Note personali", value=db.nota_da_leggere(conn, paper_id) or "",
                                label_visibility="collapsed", placeholder="Scrivi qui i tuoi appunti…")
            if st.button("Salva note"):
                db.salva_da_leggere(conn, paper_id, note)
                st.toast("Note salvate")

    if r["llm"] is None and analisi is None:
        st.warning("Per analizzare i paper serve GEMINI_API_KEY nel file .env (vedi README).")

    rifare = False
    if analisi is not None and analisi["base_testo"] == "abstract" and r["llm"] is not None:
        rifare = colonne[0].button("📄 Riprova col testo completo", width="stretch",
                                   help="Cerca il PDF ad accesso aperto e rifà l'analisi sul testo intero. "
                                        "Usa 1 richiesta solo se il testo viene trovato.")

    if vuole_analisi or rifare:
        with st.status("Analisi in corso…", expanded=True) as stato:
            try:
                analizza(conn, paper_id, r["llm"], r["fonti"]["openalex"], r["impostazioni"],
                         avanzamento=stato.write, solo_se_testo_completo=rifare)
            except (ErroreLLM, ErroreAnalisi) as e:
                stato.update(label="Analisi non riuscita", state="error")
                st.error(str(e))
                return
            stato.update(label="Analisi completata", state="complete")
        st.rerun()

    # --- schede
    formale, semplice, affidabilita, contesto, glossario, originale = st.tabs(
        ["Spiegazione formale", "Spiegazione semplice", "Affidabilità e bias",
         "Contesto e grafo", "Glossario", "Abstract"])

    senza_analisi = "Questo paper non è ancora stato analizzato. Premi **🔎 Analizza ora** qui sopra."
    dati = analisi["contenuto"] if analisi else None

    with formale:
        if dati:
            _avviso_base(analisi)
            st.write(dati["spiegazione_formale"])
            _tabella_dati_chiave(dati)
        else:
            st.info(senza_analisi)
    with semplice:
        if dati:
            st.write(dati["spiegazione_semplice"])
            if dati["punti_chiave"]:
                st.subheader("In breve")
                for punto in dati["punti_chiave"]:
                    st.markdown(f"- {punto}")
        else:
            st.info(senza_analisi)
    with affidabilita:
        if dati:
            _scheda_affidabilita(paper, analisi)
        else:
            st.info(senza_analisi)
    with contesto:
        _scheda_contesto(r, paper, dati)
    with glossario:
        if dati and dati["glossario"]:
            for voce in dati["glossario"]:
                st.markdown(f"**{voce['termine']}** — {voce['definizione']}")
        else:
            st.info(senza_analisi if not dati else "Nessun termine in glossario per questo paper.")
    with originale:
        if ui.abstract_da_mostrare(paper) != paper["abstract"]:
            st.write(paper["abstract_it"])
            st.caption("Traduzione automatica: per i dettagli fa fede il testo originale.")
            with st.expander("Testo originale"):
                st.write(paper["abstract"])
        else:
            st.write(paper["abstract"] or "Abstract non disponibile.")


def _avviso_base(analisi: dict) -> None:
    """Dichiara su quale testo si basa l'analisi."""
    if analisi["base_testo"] == "abstract":
        st.warning("Questa analisi si basa **solo sull'abstract**: il testo completo non era disponibile "
                   "ad accesso aperto. Limiti, conflitti di interesse e dettagli dei metodi potrebbero "
                   "non essere rilevabili.")
    else:
        st.success("Analisi basata sul **testo completo** del paper.")
    st.caption(f"Modello: {analisi['modello']} · analisi del {analisi['creata_il'][:10]}")


def _tabella_dati_chiave(dati: dict) -> None:
    if not dati["dati_chiave"]:
        return
    st.subheader("Numeri e risultati chiave")
    ui.tabella([{
        "Dato": d["etichetta"], "Valore": d["valore"],
        "Citazione dal paper": d.get("citazione") or "—",
        "Verifica": (d.get("verifica") or "—"),
    } for d in dati["dati_chiave"]])


def _scheda_affidabilita(paper: dict, analisi: dict) -> None:
    aff = analisi["contenuto"]["affidabilita"]
    _avviso_base(analisi)

    c1, c2, c3 = st.columns(3)
    c1.metric("Tipo di studio", aff["tipo_studio"].capitalize())
    c2.metric("Pubblicazione", "Preprint" if paper["stato"] == "preprint" else
              "Rivista" if paper["stato"] == "rivista" else "Non rilevabile",
              help=ETICHETTE_STATO.get(paper["stato"]))
    c3.metric("Campione", ui.accorcia(aff["dimensione_campione"]["testo"], 28),
              help=aff["dimensione_campione"]["testo"])
    ui.citazione(aff["dimensione_campione"])

    st.write(aff["sintesi"])

    st.subheader(f"Griglia di valutazione: studio {aff['tipo_studio']}")
    sinistra, destra = st.columns([3, 1])
    with sinistra:
        ui.tabella([{
            "Criterio": v["criterio"], "Esito": SIMBOLI_ESITO.get(v["esito"], v["esito"]),
            "Motivazione": v["motivazione"],
        } for v in aff["griglia"]])
    with destra:
        conteggio = Counter(v["esito"] for v in aff["griglia"])
        st.caption("Criteri per esito")
        grafici.barre_orizzontali({e: conteggio.get(e, 0) for e in SIMBOLI_ESITO}, grafici.COLORI_ESITO, larghezza=300)
    with st.expander("Citazioni a sostegno della griglia"):
        for v in aff["griglia"]:
            if v.get("citazione"):
                st.markdown(f"**{v['criterio']}**")
                ui.citazione(v)

    for titolo, voci, vuoto in [
        ("Limiti dichiarati dagli autori", aff["limiti_dichiarati"], "Nessun limite dichiarato rilevabile nel testo."),
        ("Possibili bias", aff["possibili_bias"], "Nessun bias rilevabile dal testo disponibile."),
    ]:
        st.subheader(titolo)
        if not voci:
            st.write(vuoto)
        for voce in voci:
            st.markdown(f"- {voce['testo']}")
            ui.citazione(voce)

    st.subheader("Conflitti di interesse dichiarati")
    st.write(aff["conflitti_interesse"]["testo"])
    ui.citazione(aff["conflitti_interesse"])

    verifiche = analisi["contenuto"].get("meta", {}).get("verifica_citazioni", {})
    if verifiche:
        st.subheader("Controllo automatico delle citazioni")
        st.caption("Quante delle frasi citate dal modello sono state ritrovate nel testo del paper.")
        grafici.barra_composta({e: verifiche.get(e, 0) for e in grafici.COLORI_VERIFICA}, grafici.COLORI_VERIFICA)


def _scheda_contesto(r: dict, paper: dict, dati: dict | None) -> None:
    conn, paper_id = r["conn"], paper["id"]
    collegati = servizio_contesto.collegati(conn, paper_id)

    st.subheader("Collocazione nel quadro più ampio")
    if dati:
        st.write(dati["contesto"]["sintesi"])
        per_openalex = {c["openalex_id"]: c for c in collegati}
        for legame in dati["contesto"]["collegamenti"]:
            altro = per_openalex.get(legame["id"])
            if altro:
                st.button(f"[{legame['id']}] {ui.accorcia(altro['titolo'], 80)}", key=f"ctx_{legame['id']}",
                          type="tertiary", help=legame["relazione"], on_click=ui.apri_paper, args=(altro["altro_id"],))
                st.caption(legame["relazione"])
        st.caption("Basato solo sui paper collegati forniti da OpenAlex, non sulla memoria del modello.")
    else:
        st.info("La collocazione nel quadro più ampio compare dopo l'analisi. "
                "Il grafo qui sotto invece usa solo dati e funziona anche senza.")

    # --- recupero o aggiornamento dei collegamenti
    etichetta = "Aggiorna i collegamenti da OpenAlex" if paper["collegamenti_il"] else "Recupera i collegamenti da OpenAlex"
    if st.button(etichetta, help="Non usa richieste del modello."):
        with st.spinner("Interrogo OpenAlex…"):
            try:
                trovati = servizio_contesto.aggiorna_collegamenti(conn, paper_id, r["fonti"]["openalex"], r["impostazioni"])
                st.toast(f"{trovati} paper collegati trovati")
            except ErroreFonte as e:
                st.error(f"Collegamenti non recuperati: {e}")
            else:
                st.rerun()
    if paper["collegamenti_il"] and not collegati:
        st.caption("OpenAlex non ha ancora riferimenti o citazioni per questo paper (succede spesso con quelli "
                   "usciti da pochi giorni). Riprova più avanti con il pulsante qui sopra.")

    # --- grafo
    st.subheader("Grafo dei paper collegati")
    g = r["impostazioni"]["grafo"]
    grafo = _grafo(conn, paper_id, g["soglia_similarita"], g["max_simili"], db.impronta_grafo(conn))
    if len(grafo["nodi"]) < 2:
        st.info("Ancora nessun collegamento da disegnare: recupera i collegamenti da OpenAlex "
                "oppure raccogli altri paper per trovare abstract simili.")
    else:
        grafo_interattivo.legenda_grafo()
        grafo_interattivo.disegna_grafo(grafo)

    # --- tabella e grafico dei collegati
    if collegati:
        st.subheader("Paper collegati")
        ordinati = sorted(collegati, key=lambda c: c["data_pubblicazione"] or "", reverse=True)
        ui.tabella([{
            "Titolo": c["titolo"], "Anno": (c["data_pubblicazione"] or "")[:4] or "—",
            "Relazione": c["relazione"],
            "Citazioni ricevute": c["n_citazioni"] if c["n_citazioni"] is not None else "—",
        } for c in ordinati])
        anni = Counter((c["data_pubblicazione"] or "")[:4] for c in collegati if c["data_pubblicazione"])
        if len(anni) > 1:
            st.caption("Anni di pubblicazione dei paper collegati: mostra quanto è recente la letteratura su cui poggia.")
            grafici.colonne(dict(sorted(anni.items())))
        citati = {ui.accorcia(c["titolo"], 22): c["n_citazioni"] for c in
                  sorted(collegati, key=lambda c: c["n_citazioni"] or 0, reverse=True)[:8] if c["n_citazioni"]}
        if citati:
            st.caption("I paper collegati più citati: indicano i lavori di riferimento dell'argomento.")
            grafici.barre_orizzontali(citati, larghezza=640)
