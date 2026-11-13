"""Disegno del grafo interattivo dei paper collegati.

I dati (nodi e archi) arrivano da servizi/grafo.py; qui c'è solo il disegno.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from paper_radar.ui.componenti import accorcia

COLORI_NODO = {"centro": "#D1495B", "collegato": "#2E6F95", "simile": "#3A8F5C"}
COLORI_ARCO = {"cita": "#2E6F95", "correlato": "#8A8F98", "simile": "#3A8F5C"}

LIBRERIA_GRAFO = Path(__file__).with_name("vis-network.min.js")

# Pagina HTML del grafo. I segnaposto __...__ vengono sostituiti da disegna_grafo().
MODELLO_GRAFO = """
<div id="grafo" style="height:560px; border:1px solid __BORDO__; border-radius:8px; background:__SFONDO__"></div>
<script>__LIBRERIA__</script>
<script>
  const dati = {nodes: new vis.DataSet(__NODI__), edges: new vis.DataSet(__ARCHI__)};
  const opzioni = {
    nodes: {shape: "dot", font: {size: 13, color: "__TESTO__"}},
    edges: {width: 1.5, font: {size: 11, color: "__TESTO__", strokeWidth: 3, strokeColor: "__SFONDO__"}, smooth: {type: "continuous"}},
    physics: {solver: "barnesHut", barnesHut: {gravitationalConstant: -6000, springLength: 150}, stabilization: {iterations: 200}},
    interaction: {hover: true, tooltipDelay: 150}
  };
  const rete = new vis.Network(document.getElementById("grafo"), dati, opzioni);
  // Un clic su un nodo (diverso da quello centrale) apre quel paper.
  rete.on("click", function (evento) {
    if (evento.nodes.length === 1 && evento.nodes[0] !== __CENTRO__) {
      // Il grafo vive in un riquadro (iframe) che non può cambiare l'indirizzo della
      // pagina. Può però aggiungere un collegamento alla pagina principale e "cliccarlo".
      const principale = window.parent.document;
      const collegamento = principale.createElement("a");
      collegamento.href = window.parent.location.pathname + "?paper=" + evento.nodes[0];
      principale.body.appendChild(collegamento);
      collegamento.click();
    }
  });
</script>
"""


def _json_sicuro(dati) -> str:
    """JSON da inserire dentro un tag <script>.

    I titoli dei paper arrivano da fonti esterne: se uno contenesse "</script>"
    chiuderebbe il tag in anticipo. Scrivere "<\\/" al posto di "</" lo impedisce
    senza cambiare il significato del testo.
    """
    return json.dumps(dati).replace("</", "<\\/")


def legenda_grafo() -> None:
    def pallino(colore: str, testo: str) -> str:
        return f"<span style='color:{colore}'>●</span> {testo}"

    st.markdown(
        " &nbsp; ".join([
            pallino(COLORI_NODO["centro"], "questo paper"),
            pallino(COLORI_NODO["collegato"], "citazione o correlato (OpenAlex)"),
            pallino(COLORI_NODO["simile"], "abstract simile (linea tratteggiata, con punteggio)"),
        ]),
        unsafe_allow_html=True,
    )
    st.caption("Le frecce vanno dal paper che cita a quello citato. Clicca un nodo per aprire quel paper.")


def disegna_grafo(grafo: dict) -> None:
    """Disegna il grafo interattivo: i nodi si trascinano, la rotella fa lo zoom.

    Il disegno è affidato a vis-network, una libreria JavaScript inclusa nel
    progetto (nessun download a ogni avvio). Python prepara nodi e archi e li
    passa alla pagina come JSON. Un clic su un nodo ricarica l'app con
    "?paper=<id>" nell'indirizzo: app.py legge quel valore e apre il paper.
    """
    nodi = [{
        "id": n["id"],
        "label": accorcia(n["titolo"], 34),
        "title": f"{n['titolo']} ({n['anno'] or 'anno n.d.'})",       # testo al passaggio del mouse
        "size": 30 if n["ruolo"] == "centro" else 18,
        "color": COLORI_NODO[n["ruolo"]],
    } for n in grafo["nodi"]]
    archi = [{
        "from": a["da"],
        "to": a["a"],
        "color": COLORI_ARCO[a["tipo"]],
        "dashes": a["tipo"] == "simile",
        "label": str(a["peso"]) if a["tipo"] == "simile" else "",
        "arrows": "to" if a["tipo"] == "cita" else "",                # freccia solo per le citazioni
        "title": {"cita": "cita", "correlato": "correlato (OpenAlex)", "simile": "abstract simili"}[a["tipo"]],
    } for a in grafo["archi"]]
    centro = next(n["id"] for n in grafo["nodi"] if n["ruolo"] == "centro")

    pagina = MODELLO_GRAFO.replace("__LIBRERIA__", LIBRERIA_GRAFO.read_text(encoding="utf-8"))
    pagina = pagina.replace("__NODI__", _json_sicuro(nodi)).replace("__ARCHI__", _json_sicuro(archi))
    pagina = pagina.replace("__CENTRO__", str(centro))
    # Colori di sfondo e scritte secondo il tema scelto nella barra laterale.
    scuro = bool(st.session_state.get("tema_scuro"))
    for segnaposto, colore in (("__SFONDO__", "#0e1117" if scuro else "#ffffff"),
                               ("__TESTO__", "#e6e9ef" if scuro else "#1f2933"),
                               ("__BORDO__", "#3a3f4b" if scuro else "#e3e6ea")):
        pagina = pagina.replace(segnaposto, colore)
    if hasattr(st, "iframe"):
        st.iframe(pagina, height=580)
    else:                                   # versioni di Streamlit meno recenti
        import streamlit.components.v1 as components
        components.html(pagina, height=580)
