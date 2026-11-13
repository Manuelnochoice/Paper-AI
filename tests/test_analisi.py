"""Analisi: schema, verifica delle citazioni, griglia, contesto e cache."""
import json

import pytest
from pydantic import ValidationError

from paper_radar.dati import db
from paper_radar.llm.griglie import GRIGLIE
from paper_radar.llm.llm_client import LLMClient
from paper_radar.llm.rate_limiter import ContatoreInMemoria
from paper_radar.llm.schemi import Analisi
from paper_radar.servizi import analisi as servizio
from paper_radar.servizi.citazioni import normalizza, verifica_citazione
from tests.conftest import crea_paper
from tests.test_llm_client import ProviderFinto

TESTO = ("We enrolled 120 patients in a randomized, double-blind trial. "
         "The primary outcome improved by 12% (p = 0.03). "
         "A limitation of this study is the short follow-up period.")


def analisi_di_esempio() -> dict:
    return {
        "spiegazione_formale": "Studio clinico randomizzato in doppio cieco su 120 pazienti con esito primario migliorato.",
        "spiegazione_semplice": "I ricercatori hanno provato una cura su 120 persone, senza che sapessero chi la riceveva.",
        "punti_chiave": ["120 pazienti", "miglioramento del 12%"],
        "dati_chiave": [{"etichetta": "Miglioramento", "valore": "12%", "citazione": "improved by 12% (p = 0.03)"}],
        "affidabilita": {
            "tipo_studio": "Clinico",
            "dimensione_campione": {"testo": "120 pazienti", "citazione": "We enrolled 120 patients"},
            "limiti_dichiarati": [{"testo": "Follow-up breve", "citazione": "the short follow-up period"}],
            "possibili_bias": [{"testo": "Bias inventato", "citazione": "this sentence is not in the paper at all"}],
            "conflitti_interesse": {"testo": "non rilevabile", "citazione": None},
            "griglia": [
                {"criterio": "Assegnazione casuale (randomizzazione)", "esito": "Si",
                 "motivazione": "Dichiarato.", "citazione": "randomized, double-blind trial"},
                {"criterio": "Criterio inventato dal modello", "esito": "no", "motivazione": "", "citazione": None},
            ],
            "sintesi": "Studio ben disegnato ma con follow-up breve.",
        },
        "contesto": {
            "sintesi": "Prosegue il lavoro di [W50].",
            "collegamenti": [{"id": "W50", "relazione": "studio precedente"},
                             {"id": "W999", "relazione": "paper inventato dal modello"}],
        },
        "glossario": [{"termine": "doppio cieco", "definizione": "Né pazienti né medici sanno chi riceve la cura."}],
    }


class OpenAlexFinto:
    """Restituisce un solo paper collegato (W50), citato dal paper analizzato."""

    def per_id(self, ids):
        return [crea_paper(50)] if "W50" in ids else []

    def citanti(self, openalex_id, massimo):
        return []


IMPOSTAZIONI = {
    "llm": {"max_caratteri_testo": 60000},
    "contesto": {"max_riferimenti": 5, "max_citanti": 5, "max_correlati": 5},
}


def test_schema_rifiuta_analisi_incompleta():
    incompleta = analisi_di_esempio()
    del incompleta["affidabilita"]
    with pytest.raises(ValidationError):
        Analisi.model_validate(incompleta)


def test_schema_uniforma_esito_e_tipo_di_studio():
    analisi = Analisi.model_validate(analisi_di_esempio())
    assert analisi.affidabilita.tipo_studio == "clinico"
    assert analisi.affidabilita.griglia[0].esito == "sì"


def test_verifica_citazione():
    testo = normalizza(TESTO)
    assert verifica_citazione("We enrolled 120 patients", testo) == "verificata"
    assert verifica_citazione("we enrolled  120 PATIENTS", testo) == "verificata"       # maiuscole e spazi non contano
    # Una parola in più ("clearly") su una frase lunga: quasi identica.
    quasi = "We enrolled 120 patients in a randomized, double-blind trial. The primary outcome clearly improved by 12%"
    assert verifica_citazione(quasi, testo) == "approssimata"
    assert verifica_citazione("Patients were recruited from twelve hospitals in Europe", testo) == "non verificata"
    assert verifica_citazione(None, testo) is None


def test_analisi_completa_con_controlli_e_cache(conn):
    paper_id, _ = db.salva_paper(conn, crea_paper(1, abstract=TESTO, riferimenti=["W50"]))
    provider = ProviderFinto([json.dumps(analisi_di_esempio())])
    llm = LLMClient(provider, [{"nome": "finto", "rpm": 100, "rpd": 10}], ContatoreInMemoria())

    risultato = servizio.analizza(conn, paper_id, llm, OpenAlexFinto(), IMPOSTAZIONI)
    contenuto = risultato["contenuto"]
    aff = contenuto["affidabilita"]

    assert risultato["base_testo"] == "abstract"
    # Citazioni: quella vera è verificata, quella inventata è segnalata.
    assert aff["dimensione_campione"]["verifica"] == "verificata"
    assert aff["possibili_bias"][0]["verifica"] == "non verificata"
    # Griglia: tutti e soli i criteri previsti per uno studio clinico.
    assert [v["criterio"] for v in aff["griglia"]] == GRIGLIE["clinico"]
    assert aff["griglia"][1]["esito"] == "sì"
    assert aff["griglia"][0]["esito"] == "non rilevabile"
    # Contesto: resta solo il paper davvero fornito da OpenAlex.
    assert [c["id"] for c in contenuto["contesto"]["collegamenti"]] == ["W50"]
    # Il prompt conteneva il paper collegato.
    assert "[W50]" in provider.chiamate[0][1]
    # Glossario generale aggiornato.
    assert db.cerca_glossario(conn, "cieco")[0]["termine"] == "doppio cieco"

    # Seconda richiesta: arriva dal database, il modello non viene richiamato.
    servizio.analizza(conn, paper_id, llm, OpenAlexFinto(), IMPOSTAZIONI)
    assert len(provider.chiamate) == 1


def test_senza_paper_collegati_il_contesto_e_non_rilevabile(conn):
    paper_id, _ = db.salva_paper(conn, crea_paper(1, abstract=TESTO))
    provider = ProviderFinto([json.dumps(analisi_di_esempio())])
    llm = LLMClient(provider, [{"nome": "finto", "rpm": 100, "rpd": 10}], ContatoreInMemoria())
    contenuto = servizio.analizza(conn, paper_id, llm, OpenAlexFinto(), IMPOSTAZIONI)["contenuto"]
    assert contenuto["contesto"] == {"sintesi": "non rilevabile", "collegamenti": []}


def test_riprova_col_testo_completo_non_spreca_richieste(conn, monkeypatch):
    """Se il testo completo non si trova, l'analisi esistente resta e il modello non viene chiamato."""
    paper_id, _ = db.salva_paper(conn, crea_paper(1, abstract=TESTO))
    provider = ProviderFinto([json.dumps(analisi_di_esempio())])
    llm = LLMClient(provider, [{"nome": "finto", "rpm": 100, "rpd": 10}], ContatoreInMemoria())
    servizio.analizza(conn, paper_id, llm, OpenAlexFinto(), IMPOSTAZIONI)

    with pytest.raises(servizio.ErroreAnalisi):
        servizio.analizza(conn, paper_id, llm, OpenAlexFinto(), IMPOSTAZIONI, solo_se_testo_completo=True)
    assert len(provider.chiamate) == 1
    assert db.leggi_analisi(conn, paper_id)["base_testo"] == "abstract"
