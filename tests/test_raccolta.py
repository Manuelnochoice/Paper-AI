"""Raccolta: solo paper recenti, mai riproposti, e nessun blocco se una fonte fallisce."""
from datetime import date

from paper_radar.dati import db
from paper_radar.fonti.http import ErroreFonte
from paper_radar.servizi.raccolta import raccogli_area
from tests.conftest import crea_paper

OGGI = date(2026, 11, 12)
IMPOSTAZIONI = {"raccolta": {"giorni": 7, "max_nuovi_per_fonte": 2, "max_pagine": 5}}
AREA = {"nome": "Fisica", "fonti": {"finta": {}}}


class FonteFinta:
    """Fonte che restituisce pagine preparate, senza usare la rete."""

    def __init__(self, pagine):
        self._pagine = pagine
        self.pagine_lette = 0

    def pagine(self, opzioni, dal, al):
        for pagina in self._pagine:
            self.pagine_lette += 1
            yield pagina


class FonteRotta:
    def pagine(self, opzioni, dal, al):
        raise ErroreFonte("esempio.org: il server non ha risposto in tempo, dopo 3 tentativi")
        yield   # rende la funzione un generatore


def test_salva_solo_i_paper_recenti(conn):
    fonte = FonteFinta([[crea_paper(1), crea_paper(2, data_pubblicazione="2026-01-01")]])
    esito = raccogli_area(conn, "fisica", AREA, {"finta": fonte}, IMPOSTAZIONI, oggi=OGGI)
    assert (esito.trovati, esito.nuovi) == (1, 1)


def test_seconda_raccolta_non_ripropone_e_cerca_piu_a_fondo(conn):
    """Il difetto della vecchia versione: sempre gli stessi paper."""
    pagine = [[crea_paper(1), crea_paper(2)], [crea_paper(3), crea_paper(4)]]

    primo = raccogli_area(conn, "fisica", AREA, {"finta": FonteFinta(pagine)}, IMPOSTAZIONI, oggi=OGGI)
    assert primo.nuovi == 2                      # si ferma al limite di 2 nuovi

    fonte = FonteFinta(pagine)
    secondo = raccogli_area(conn, "fisica", AREA, {"finta": fonte}, IMPOSTAZIONI, oggi=OGGI)
    assert secondo.nuovi == 2                    # i paper 3 e 4, non di nuovo 1 e 2
    assert fonte.pagine_lette == 2               # ha dovuto leggere la seconda pagina

    terzo = raccogli_area(conn, "fisica", AREA, {"finta": FonteFinta(pagine)}, IMPOSTAZIONI, oggi=OGGI)
    assert terzo.nuovi == 0


def test_paper_mostrati_passano_in_archivio_il_giorno_dopo(conn):
    raccogli_area(conn, "fisica", AREA, {"finta": FonteFinta([[crea_paper(1)]])}, IMPOSTAZIONI, oggi=OGGI)
    novita = db.elenca_paper(conn, "novita", oggi="2026-11-12")
    assert len(novita) == 1
    db.segna_mostrati(conn, [novita[0]["id"]], oggi="2026-11-12")

    # Lo stesso giorno resta tra le novità; il giorno dopo è in archivio.
    assert len(db.elenca_paper(conn, "novita", oggi="2026-11-12")) == 1
    assert db.elenca_paper(conn, "novita", oggi="2026-11-13") == []
    assert len(db.elenca_paper(conn, "archivio", oggi="2026-11-13")) == 1


def test_filtri_per_area_parola_e_date(conn):
    db.salva_paper(conn, crea_paper(1, titolo="Quantum entanglement in superconducting circuits today"), area="fisica")
    db.salva_paper(conn, crea_paper(2, data_pubblicazione="2026-11-01"), area="chimica")
    assert len(db.elenca_paper(conn, "novita", aree=["fisica"])) == 1
    assert len(db.elenca_paper(conn, "novita", testo="entanglement")) == 1
    assert len(db.elenca_paper(conn, "novita", dal="2026-11-05")) == 1
    assert len(db.elenca_paper(conn, "novita")) == 2


def test_una_fonte_rotta_non_blocca_le_altre(conn):
    area = {"nome": "Fisica", "fonti": {"rotta": {}, "finta": {}, "inesistente": {}}}
    fonti = {"rotta": FonteRotta(), "finta": FonteFinta([[crea_paper(1)]])}
    esito = raccogli_area(conn, "fisica", area, fonti, IMPOSTAZIONI, oggi=OGGI)
    assert esito.nuovi == 1
    assert len(esito.errori) == 2
    assert "non ha risposto in tempo" in esito.errori[0]
