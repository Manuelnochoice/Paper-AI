"""Strumenti comuni ai test: database temporaneo e paper di prova."""
import pytest

from paper_radar.dati import db
from paper_radar.modelli import PaperGrezzo


@pytest.fixture
def conn(tmp_path):
    """Un database vuoto, creato in una cartella temporanea e buttato a fine test."""
    connessione = db.connetti(tmp_path / "test.db")
    yield connessione
    connessione.close()


def crea_paper(n: int = 1, **campi) -> PaperGrezzo:
    """Un paper di prova; `campi` sovrascrive i valori predefiniti."""
    base = dict(
        titolo=f"A study of interesting scientific phenomenon number {n}",
        fonte="openalex",
        abstract="We study an interesting phenomenon with careful experiments and report results. " * 3,
        autori=["Ada Lovelace", "Alan Turing"],
        data_pubblicazione="2026-11-10",
        doi=f"10.1234/test.{n}",
        openalex_id=f"W{n}",
    )
    base.update(campi)
    return PaperGrezzo(**base)
