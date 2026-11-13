"""Client del modello: JSON validato, nuovi tentativi, errori 429 e fallback."""
import json

import pytest
from pydantic import BaseModel

from paper_radar.llm.llm_client import ErroreLLM, LLMClient, TroppeRichieste, estrai_json
from paper_radar.llm.rate_limiter import ContatoreInMemoria


class Schema(BaseModel):
    titolo: str
    voto: int


VALIDO = json.dumps({"titolo": "ok", "voto": 7})
MODELLI = [{"nome": "grande", "rpm": 100, "rpd": 10}, {"nome": "leggero", "rpm": 100, "rpd": 10}]


class ProviderFinto:
    """Restituisce in ordine le risposte preparate; un'eccezione viene sollevata."""

    def __init__(self, risposte):
        self.risposte = list(risposte)
        self.chiamate = []          # (modello, prompt) di ogni chiamata

    def genera(self, modello, prompt):
        self.chiamate.append((modello, prompt))
        risposta = self.risposte.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta


def crea(risposte, modelli=MODELLI):
    provider = ProviderFinto(risposte)
    client = LLMClient(provider, modelli, ContatoreInMemoria(), tentativi_json=2, tentativi_429=2,
                       dormi=lambda secondi: None)
    return client, provider


def test_estrai_json_toglie_i_recinti_markdown():
    assert estrai_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_risposta_valida_al_primo_colpo():
    client, provider = crea([VALIDO])
    risposta = client.genera_json("prompt", Schema)
    assert risposta.dati.voto == 7
    assert risposta.modello == "grande"
    assert len(provider.chiamate) == 1


def test_json_malformato_viene_richiesto_di_nuovo():
    client, provider = crea(["{ questo non è json", VALIDO])
    risposta = client.genera_json("prompt", Schema)
    assert risposta.dati.titolo == "ok"
    assert risposta.richieste == 2
    assert "non era valida" in provider.chiamate[1][1]     # il secondo prompt spiega l'errore


def test_json_con_campi_mancanti_e_rifiutato():
    client, _ = crea([json.dumps({"titolo": "manca il voto"}), VALIDO])
    assert client.genera_json("prompt", Schema).dati.voto == 7


def test_errore_429_riprova_e_poi_riesce():
    client, provider = crea([TroppeRichieste(), VALIDO])
    assert client.genera_json("prompt", Schema).modello == "grande"
    assert len(provider.chiamate) == 2


def test_quota_esaurita_passa_al_modello_leggero():
    client, provider = crea([TroppeRichieste(), TroppeRichieste(), TroppeRichieste(), VALIDO])
    risposta = client.genera_json("prompt", Schema)
    assert risposta.modello == "leggero"
    assert client.quote()[0]["rimaste"] == 0        # il modello grande è segnato come esaurito


def test_tutti_i_modelli_esauriti_da_un_errore_chiaro():
    solo_uno = [{"nome": "grande", "rpm": 100, "rpd": 0}]
    client, provider = crea([], modelli=solo_uno)
    with pytest.raises(ErroreLLM) as errore:
        client.genera_json("prompt", Schema)
    assert errore.value.quota_esaurita
    assert provider.chiamate == []                  # non ha nemmeno provato a chiamare


def test_ogni_richiesta_viene_contata():
    client, _ = crea(["non json", VALIDO])
    client.genera_json("prompt", Schema)
    assert client.quote()[0]["rimaste"] == 8
