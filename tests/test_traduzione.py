"""Traduzione: più paper per richiesta, salvata nel database e mai ripetuta."""
import json

from paper_radar.dati import db
from paper_radar.llm.llm_client import LLMClient
from paper_radar.llm.rate_limiter import ContatoreInMemoria
from paper_radar.servizi.traduzione import traduci
from tests.conftest import crea_paper
from tests.test_llm_client import ProviderFinto


def risposta(*ids):
    return json.dumps({"traduzioni": [{"id": i, "titolo": f"Titolo {i}", "abstract": f"Riassunto {i}"} for i in ids]})


def crea_llm(risposte):
    provider = ProviderFinto(risposte)
    return LLMClient(provider, [{"nome": "leggero", "rpm": 100, "rpd": 50}], ContatoreInMemoria()), provider


def test_traduce_a_gruppi_e_salva(conn):
    ids = [db.salva_paper(conn, crea_paper(n))[0] for n in (1, 2, 3)]
    llm, provider = crea_llm([risposta(ids[0], ids[1]), risposta(ids[2])])
    paper = sorted(db.elenca_paper(conn, "novita"), key=lambda p: p["id"])

    assert traduci(conn, paper, llm, per_richiesta=2) == 3
    assert len(provider.chiamate) == 2                         # 3 paper, 2 per richiesta
    assert db.leggi_paper(conn, ids[0])["titolo_it"] == f"Titolo {ids[0]}"
    # La ricerca per parola chiave trova anche il testo italiano.
    assert len(db.elenca_paper(conn, "novita", testo="Riassunto")) == 3


def test_ignora_traduzioni_di_paper_non_richiesti(conn):
    paper_id, _ = db.salva_paper(conn, crea_paper(1))
    llm, _ = crea_llm([risposta(paper_id, 999)])
    assert traduci(conn, db.elenca_paper(conn, "novita"), llm) == 1


def test_database_vecchio_riceve_le_colonne_nuove(tmp_path):
    import sqlite3
    # Un database come lo creava la prima versione: stesso schema, senza le colonne delle traduzioni.
    schema_vecchio = "\n".join(riga for riga in db.SCHEMA.read_text(encoding="utf-8").splitlines()
                               if "titolo_it" not in riga and "abstract_it" not in riga)
    percorso = tmp_path / "vecchio.db"
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(schema_vecchio)
    vecchio.close()
    conn = db.connetti(percorso)
    colonne = {riga["name"] for riga in conn.execute("PRAGMA table_info(paper)")}
    assert {"titolo_it", "abstract_it"} <= colonne


def test_preferenze(conn):
    assert db.leggi_preferenza(conn, "tema_scuro", "0") == "0"
    db.salva_preferenza(conn, "tema_scuro", "1")
    db.salva_preferenza(conn, "tema_scuro", "1")
    assert db.leggi_preferenza(conn, "tema_scuro") == "1"
