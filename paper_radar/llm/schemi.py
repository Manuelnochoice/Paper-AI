"""Forma dell'analisi che il modello deve restituire (schemi Pydantic).

Pydantic controlla che il JSON abbia tutti i campi, con i tipi giusti.
Se manca qualcosa solleva un errore e `llm_client` chiede al modello di riprovare.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from paper_radar.llm.griglie import TIPI_STUDIO

NON_RILEVABILE = "non rilevabile"


class Affermazione(BaseModel):
    """Un'affermazione sul paper, con la frase del paper che la sostiene."""

    testo: str
    citazione: Optional[str] = None      # frase copiata dal paper, in lingua originale
    # Compilato dal codice (non dal modello) dopo aver cercato la citazione nel testo:
    # "verificata", "approssimata", "non verificata" oppure None se non c'è citazione.
    verifica: Optional[str] = None


class VoceGriglia(BaseModel):
    criterio: str
    esito: Literal["sì", "parziale", "no", "non rilevabile"]
    motivazione: str = ""
    citazione: Optional[str] = None
    verifica: Optional[str] = None

    @field_validator("esito", mode="before")
    @classmethod
    def _uniforma_esito(cls, valore):
        # Il modello a volte scrive "Si", "SÌ", "si": li portiamo a una forma sola.
        valore = str(valore).strip().lower()
        return {"si": "sì", "sí": "sì", "yes": "sì", "non rilevabile.": NON_RILEVABILE}.get(valore, valore)


class Affidabilita(BaseModel):
    tipo_studio: str
    dimensione_campione: Affermazione
    limiti_dichiarati: list[Affermazione] = Field(default_factory=list)
    possibili_bias: list[Affermazione] = Field(default_factory=list)
    conflitti_interesse: Affermazione
    griglia: list[VoceGriglia] = Field(default_factory=list)
    sintesi: str

    @field_validator("tipo_studio", mode="before")
    @classmethod
    def _uniforma_tipo(cls, valore):
        valore = str(valore).strip().lower()
        return valore if valore in TIPI_STUDIO else "altro"


class CollegamentoContesto(BaseModel):
    id: str            # id OpenAlex di un paper collegato, es. "W2100837269"
    relazione: str     # come si rapporta al paper analizzato


class Contesto(BaseModel):
    sintesi: str
    collegamenti: list[CollegamentoContesto] = Field(default_factory=list)


class Termine(BaseModel):
    termine: str
    definizione: str


class DatoChiave(BaseModel):
    """Un numero o risultato importante, per la tabella riassuntiva."""

    etichetta: str
    valore: str
    citazione: Optional[str] = None
    verifica: Optional[str] = None


class Analisi(BaseModel):
    spiegazione_formale: str = Field(min_length=50)
    spiegazione_semplice: str = Field(min_length=50)
    punti_chiave: list[str] = Field(default_factory=list)
    dati_chiave: list[DatoChiave] = Field(default_factory=list)
    affidabilita: Affidabilita
    contesto: Contesto
    glossario: list[Termine] = Field(default_factory=list)
