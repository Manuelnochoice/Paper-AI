"""Grafo: gli archi nascono da citazioni reali e dalla similarità tra abstract."""
from paper_radar.dati import db
from paper_radar.servizi.grafo import costruisci_grafo
from tests.conftest import crea_paper

QUANTUM = "Quantum error correction with superconducting qubits and surface codes reduces logical error rates. " * 3
QUANTUM_2 = "Surface codes on superconducting qubits: quantum error correction below threshold logical error. " * 3
CUCINA = "A traditional recipe for tomato sauce with basil, garlic and olive oil cooked slowly for hours. " * 3


def test_archi_da_citazioni_e_similarita(conn):
    centro, _ = db.salva_paper(conn, crea_paper(1, titolo="Quantum error correction at scale in practice", abstract=QUANTUM))
    citato, _ = db.salva_paper(conn, crea_paper(2, titolo="Foundations of the surface code approach", abstract=""), origine="collegato")
    simile, _ = db.salva_paper(conn, crea_paper(3, titolo="Below threshold surface code experiments", abstract=QUANTUM_2))
    diverso, _ = db.salva_paper(conn, crea_paper(4, titolo="Slow cooked tomato sauce: a culinary study", abstract=CUCINA))
    db.salva_collegamento(conn, centro, citato, "cita")
    conn.commit()

    grafo = costruisci_grafo(conn, centro, soglia=0.15, max_simili=5)
    ruoli = {n["id"]: n["ruolo"] for n in grafo["nodi"]}
    archi = {(a["da"], a["a"], a["tipo"]) for a in grafo["archi"]}

    assert ruoli == {centro: "centro", citato: "collegato", simile: "simile"}
    assert (centro, citato, "cita") in archi
    assert (centro, simile, "simile") in archi
    assert diverso not in ruoli              # abstract non simile: nessun arco


def test_paper_isolato_ha_solo_se_stesso(conn):
    centro, _ = db.salva_paper(conn, crea_paper(1))
    grafo = costruisci_grafo(conn, centro)
    assert len(grafo["nodi"]) == 1 and grafo["archi"] == []
