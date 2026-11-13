"""Griglie di valutazione dell'affidabilità, una per tipo di studio.

Ogni griglia è un elenco di criteri. Il modello sceglie il tipo di studio e
valuta i criteri di quella griglia; il codice controlla poi che ci siano tutti.
Per aggiungere o modificare un criterio basta cambiare queste liste.
"""
from __future__ import annotations

GRIGLIE: dict[str, list[str]] = {
    "clinico": [
        "Gruppo di controllo presente",
        "Assegnazione casuale (randomizzazione)",
        "Cecità (singolo o doppio cieco)",
        "Dimensione del campione giustificata",
        "Esiti (endpoint) definiti in anticipo o studio registrato",
        "Abbandoni e dati mancanti riportati",
        "Analisi statistica descritta con misure di incertezza",
    ],
    "sperimentale": [
        "Condizioni di controllo adeguate",
        "Repliche o ripetizioni dell'esperimento",
        "Metodi descritti in modo riproducibile",
        "Analisi statistica descritta con misure di incertezza",
        "Dati o materiali resi disponibili",
        "Dimensione del campione riportata",
    ],
    "computazionale": [
        "Codice reso disponibile",
        "Dati resi disponibili o pubblici",
        "Confronto con metodi di riferimento (baseline)",
        "Valutazione su dati separati da quelli di addestramento",
        "Variabilità dei risultati riportata (più esecuzioni, intervalli)",
        "Analisi di ablazione o di sensibilità",
    ],
    "teorico": [
        "Ipotesi e assunzioni dichiarate",
        "Dimostrazioni o derivazioni complete",
        "Confronto con risultati precedenti",
        "Predizioni verificabili o confronto con dati",
        "Limiti di validità discussi",
    ],
    "revisione": [
        "Strategia di ricerca della letteratura descritta",
        "Criteri di inclusione ed esclusione dichiarati",
        "Qualità degli studi inclusi valutata",
        "Sintesi quantitativa (meta-analisi) o metodo di sintesi descritto",
        "Rischio di bias di pubblicazione discusso",
    ],
    "altro": [
        "Domanda di ricerca chiara",
        "Metodi descritti",
        "Dati o prove a sostegno delle conclusioni",
        "Limiti discussi",
    ],
}

TIPI_STUDIO = list(GRIGLIE)


def griglie_per_prompt() -> str:
    """Testo delle griglie da inserire nel prompt."""
    righe = []
    for tipo, criteri in GRIGLIE.items():
        righe.append(f'- tipo "{tipo}":')
        righe += [f"    * {c}" for c in criteri]
    return "\n".join(righe)
