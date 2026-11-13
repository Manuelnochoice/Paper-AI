"""Deduplica: lo stesso paper non deve entrare due volte nel database."""
from paper_radar.dati import db
from paper_radar.servizi.deduplica import normalizza_doi, normalizza_titolo
from tests.conftest import crea_paper


def test_normalizza_doi_toglie_prefisso_e_maiuscole():
    assert normalizza_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert normalizza_doi("10.48550/arXiv.2411.01234v2") == "10.48550/arxiv.2411.01234"
    assert normalizza_doi(None) is None


def test_normalizza_titolo_ignora_punteggiatura_e_accenti():
    assert normalizza_titolo("Deep Learning: A Réview!") == normalizza_titolo("deep learning - a review")


def test_stesso_doi_non_crea_doppioni(conn):
    primo, nuovo1 = db.salva_paper(conn, crea_paper(1), area="fisica")
    secondo, nuovo2 = db.salva_paper(conn, crea_paper(1, fonte="arxiv", openalex_id=None), area="fisica")
    assert primo == secondo
    assert (nuovo1, nuovo2) == (True, False)
    assert conn.execute("SELECT COUNT(*) FROM paper").fetchone()[0] == 1


def test_stesso_paper_da_fonti_diverse_riconosciuto_dal_titolo(conn):
    da_openalex = crea_paper(1, doi="10.1101/2026.11.01.123456")
    da_arxiv = crea_paper(1, fonte="arxiv", doi="10.48550/arxiv.2611.00001", arxiv_id="2611.00001", openalex_id=None)
    primo, _ = db.salva_paper(conn, da_openalex)
    secondo, nuovo = db.salva_paper(conn, da_arxiv)
    assert primo == secondo and not nuovo
    # I dati mancanti vengono completati con quelli della seconda fonte.
    assert db.leggi_paper(conn, primo)["arxiv_id"] == "2611.00001"


def test_paper_diversi_restano_distinti(conn):
    primo, _ = db.salva_paper(conn, crea_paper(1))
    secondo, _ = db.salva_paper(conn, crea_paper(2))
    assert primo != secondo


def test_un_paper_puo_avere_piu_aree(conn):
    paper_id, _ = db.salva_paper(conn, crea_paper(1), area="fisica")
    db.salva_paper(conn, crea_paper(1), area="astronomia")
    assert db.leggi_paper(conn, paper_id)["aree"] == ["astronomia", "fisica"]
