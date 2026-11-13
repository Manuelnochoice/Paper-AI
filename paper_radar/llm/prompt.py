"""Costruzione del prompt di analisi.

Il prompt è in un file a parte così è facile leggerlo e migliorarlo.
VERSIONE_PROMPT va aumentata a ogni modifica: serve a confrontare i risultati.
"""
from __future__ import annotations

from paper_radar.llm.griglie import griglie_per_prompt

VERSIONE_PROMPT = "1"

ISTRUZIONI = """Sei un assistente che aiuta a capire i paper scientifici. Scrivi in italiano.
Rispondi con SOLO un oggetto JSON valido, senza testo prima o dopo.

REGOLE (importanti)
1. Basati SOLO sul TESTO DEL PAPER riportato sotto. Non usare conoscenze esterne e non inventare nulla.
2. Ogni campo "citazione" deve essere una frase copiata PAROLA PER PAROLA dal testo del paper,
   nella lingua originale (non tradurla), lunga al massimo 40 parole.
3. Se un'informazione non è nel testo scrivi "non rilevabile" nel campo "testo" (o "esito") e null in "citazione".
4. "contesto": usa SOLO i PAPER COLLEGATI elencati sotto, mai la tua memoria. Quando ne nomini uno
   indica il suo id tra parentesi quadre, ad esempio [W2100837269]. Se l'elenco è vuoto, in
   "sintesi" scrivi "non rilevabile" e lascia "collegamenti" vuoto.
5. "affidabilita.tipo_studio": scegli uno tra clinico, sperimentale, computazionale, teorico,
   revisione, altro. In "griglia" valuta TUTTI e SOLI i criteri della griglia di quel tipo,
   copiando il testo del criterio. "esito" può essere: "sì", "parziale", "no", "non rilevabile".
6. "possibili_bias": distorsioni che potrebbero influenzare i risultati (selezione del campione,
   mancanza di controllo, finanziamento, sovra-adattamento...). Per ognuna cita la frase del
   paper che la fa sospettare. Non elencare bias generici senza appiglio nel testo.
7. "spiegazione_formale": per chi è del settore (metodi, risultati con numeri, novità). 150-250 parole.
   "spiegazione_semplice": per chi non è del settore, senza gergo, con un esempio o paragone. 120-200 parole.
8. "dati_chiave": da 0 a 6 numeri o risultati importanti presenti nel testo, con citazione.
9. "glossario": da 4 a 10 termini tecnici del paper, con definizione semplice.

GRIGLIE DI VALUTAZIONE
{griglie}

FORMA DEL JSON
{{
  "spiegazione_formale": "...",
  "spiegazione_semplice": "...",
  "punti_chiave": ["...", "..."],
  "dati_chiave": [{{"etichetta": "...", "valore": "...", "citazione": "..."}}],
  "affidabilita": {{
    "tipo_studio": "...",
    "dimensione_campione": {{"testo": "...", "citazione": "..."}},
    "limiti_dichiarati": [{{"testo": "...", "citazione": "..."}}],
    "possibili_bias": [{{"testo": "...", "citazione": "..."}}],
    "conflitti_interesse": {{"testo": "...", "citazione": null}},
    "griglia": [{{"criterio": "...", "esito": "...", "motivazione": "...", "citazione": null}}],
    "sintesi": "giudizio complessivo in 2-3 frasi"
  }},
  "contesto": {{
    "sintesi": "...",
    "collegamenti": [{{"id": "W...", "relazione": "..."}}]
  }},
  "glossario": [{{"termine": "...", "definizione": "..."}}]
}}
"""


def _elenco_collegati(collegati: list[dict]) -> str:
    if not collegati:
        return "(nessun paper collegato disponibile)"
    righe = []
    for c in collegati:
        anno = (c.get("data_pubblicazione") or "")[:4] or "anno n.d."
        riassunto = (c.get("abstract") or "")[:350]
        righe.append(f"[{c['openalex_id']}] ({c['relazione']}, {anno}) {c['titolo']}\n    {riassunto}")
    return "\n".join(righe)


def costruisci_prompt(paper: dict, testo: str, base_testo: str, collegati: list[dict]) -> str:
    """Mette insieme istruzioni, testo del paper e paper collegati.

    `collegati` è una lista di dizionari con: openalex_id, titolo,
    data_pubblicazione, abstract, relazione (es. "citato dal paper").
    """
    nota = ""
    if base_testo == "abstract":
        nota = ("\nNOTA: hai a disposizione solo l'abstract. Molte informazioni (limiti, conflitti "
                "di interesse, dettagli dei metodi) probabilmente non ci sono: in quel caso "
                'scrivi "non rilevabile".\n')
    return (
        ISTRUZIONI.format(griglie=griglie_per_prompt())
        + nota
        + f"\nTITOLO: {paper['titolo']}\n"
        + f"\nTESTO DEL PAPER ({base_testo}):\n\"\"\"\n{testo}\n\"\"\"\n"
        + f"\nPAPER COLLEGATI (da OpenAlex):\n{_elenco_collegati(collegati)}\n"
    )
