"""Testo completo: ordine dei tentativi e ripiego sull'abstract."""
from paper_radar.servizi import testo_completo
from paper_radar.servizi.testo_completo import _tentativi, _testo_da_pdf, recupera_testo


def test_ordine_dei_tentativi():
    assert _tentativi({"arxiv_id": "2611.00001", "url_pdf": "https://arxiv.org/pdf/2611.00001"}) == [
        ("pdf", "https://arxiv.org/pdf/2611.00001")]
    tentativi = _tentativi({"pmcid": "PMC123", "url_pdf": "https://rivista.org/articolo.pdf"})
    assert [tipo for tipo, _ in tentativi] == ["xml", "pdf"]
    assert _tentativi({"abstract": "solo abstract"}) == []


def test_una_pagina_web_non_viene_scambiata_per_pdf():
    assert _testo_da_pdf(b"<html>Accesso negato</html>") == ""


def test_senza_testo_completo_si_usa_l_abstract(monkeypatch):
    def rete_assente(*argomenti, **opzioni):
        raise ConnectionError("rete non disponibile")

    monkeypatch.setattr(testo_completo, "richiesta", rete_assente)
    paper = {"abstract": "Un abstract.", "url_pdf": "https://rivista.org/articolo.pdf"}
    assert recupera_testo(paper) == ("Un abstract.", "abstract")
