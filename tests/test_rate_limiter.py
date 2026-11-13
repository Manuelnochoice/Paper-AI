"""Rate limiter: limiti al minuto (RPM) e al giorno (RPD), senza attese reali."""
import pytest

from paper_radar.llm.rate_limiter import ContatoreInMemoria, QuotaGiornalieraEsaurita, RateLimiter


class OrologioFinto:
    """Orologio controllato dal test: 'dormire' fa solo avanzare il tempo."""

    def __init__(self):
        self.adesso = 0.0
        self.attese = []

    def __call__(self):
        return self.adesso

    def dormi(self, secondi):
        self.attese.append(secondi)
        self.adesso += secondi


def crea(rpm=2, rpd=5, giorno=lambda: "2026-11-12"):
    orologio = OrologioFinto()
    limitatore = RateLimiter("modello", rpm, rpd, ContatoreInMemoria(), orologio=orologio,
                             dormi=orologio.dormi, giorno=giorno)
    return limitatore, orologio


def test_entro_il_limite_non_aspetta():
    limitatore, orologio = crea(rpm=2)
    limitatore.acquisisci()
    limitatore.acquisisci()
    assert orologio.attese == []


def test_oltre_il_limite_al_minuto_aspetta_il_tempo_giusto():
    limitatore, orologio = crea(rpm=2)
    limitatore.acquisisci()          # secondo 0
    orologio.adesso = 10
    limitatore.acquisisci()          # secondo 10
    limitatore.acquisisci()          # minuto pieno: deve aspettare che scada la prima (al secondo 60)
    assert orologio.attese == [50]


def test_conta_le_richieste_del_giorno():
    limitatore, _ = crea(rpm=100, rpd=5)
    for _ in range(3):
        limitatore.acquisisci()
    assert limitatore.rimaste_oggi() == 2


def test_quota_giornaliera_esaurita_solleva_errore():
    limitatore, _ = crea(rpm=100, rpd=2)
    limitatore.acquisisci()
    limitatore.acquisisci()
    with pytest.raises(QuotaGiornalieraEsaurita):
        limitatore.acquisisci()


def test_il_giorno_dopo_la_quota_riparte():
    giorno = ["2026-11-12"]
    limitatore, _ = crea(rpm=100, rpd=1, giorno=lambda: giorno[0])
    limitatore.acquisisci()
    assert limitatore.rimaste_oggi() == 0
    giorno[0] = "2026-11-13"
    assert limitatore.rimaste_oggi() == 1
