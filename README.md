# 🔭 Paper Radar

🇮🇹 Italiano · [🇬🇧 English](README.en.md)

App locale per **seguire le novità scientifiche e capirle**. Raccoglie i paper
usciti negli ultimi giorni in undici aree e, per quelli che scegli, produce una
spiegazione formale, una spiegazione per non addetti, una scheda di affidabilità
e bias, la collocazione nel quadro più ampio e un grafo dei paper collegati.

Gira in locale su Windows (funziona anche su macOS e Linux). Stack: **Python,
Streamlit, SQLite**, con il piano gratuito di **Gemini** per le analisi.

## Cosa fa

- **Raccolta senza ripetizioni.** Solo paper recenti, ordinati per data. Ogni
  paper già mostrato passa in *Archivio* dal giorno dopo: tra le *Novità* trovi
  solo ciò che non hai mai visto.
- **Due spiegazioni.** Una per chi è del settore, una per tutti gli altri.
- **Scheda di affidabilità.** Tipo di studio, preprint o rivista, campione,
  limiti dichiarati, possibili bias, conflitti di interesse. La griglia di
  valutazione cambia con il tipo di studio (clinico, sperimentale,
  computazionale, teorico, revisione, altro).
- **Citazioni controllate.** Ogni affermazione porta una frase copiata dal
  paper, e il codice verifica che quella frase esista davvero nel testo. Se
  un'informazione manca, la scheda dice "non rilevabile".
- **Contesto da dati reali.** La collocazione nel quadro più ampio usa solo i
  paper collegati forniti da OpenAlex (riferimenti, citazioni, correlati), non
  la memoria del modello.
- **Grafo interattivo.** Gli archi nascono da citazioni OpenAlex e dalla
  similarità tra abstract (TF-IDF, calcolata in locale). I nodi si trascinano,
  la rotella fa lo zoom e un clic su un nodo apre quel paper.
- **Strumenti di lettura.** Lista "da leggere" con note personali, glossario
  consultabile, tabelle e grafici.

## Screenshot

Da aggiungere: salva le immagini in `docs/` (elenco delle novità, scheda di
affidabilità, grafo) e inseriscile qui.

## Installazione passo passo (Windows)

1. **Installa Python 3.10 o successivo** da [python.org](https://www.python.org/downloads/),
   spuntando "Add Python to PATH".
2. **Scarica il progetto**: `git clone <indirizzo-del-repository>` oppure
   scarica lo ZIP da GitHub ed estrailo.
3. **Crea le due chiavi gratuite**:
   - Gemini: <https://aistudio.google.com/apikey>
   - OpenAlex: <https://openalex.org/settings/api>
4. **Crea il file `.env`**: copia `.env.example`, rinominalo `.env` e incolla
   le chiavi dopo il segno `=`. Il file `.env` non finisce mai su GitHub
   (è in `.gitignore`).
5. **Controlla che tutto funzioni**: doppio clic su `verifica.bat`. La prima
   volta installa le librerie (qualche minuto), poi esegue i test e prova
   chiavi, fonti e grafo con dati reali.
6. **Avvia l'app**: doppio clic su `avvia.bat`. Si apre il browser su
   <http://localhost:8501>.

Su macOS o Linux, oppure a mano:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/verifica_configurazione.py
streamlit run app.py
```

## Come si usa

1. Nella barra laterale scegli le aree (nessuna = tutte) e premi
   **Cerca nuovi paper**.
2. Apri un paper e premi **Analizza ora**, oppure usa **Metti in coda** su più
   paper e poi **Elabora la coda**.
3. Leggi le schede. In "Contesto e grafo" clicca i nodi per spostarti tra i
   paper collegati.

Un paper viene analizzato solo quando lo chiedi, e ogni analisi è salvata nel
database: non viene mai rifatta. La barra laterale mostra le richieste rimaste
oggi.

## Configurazione

Tutto ciò che può cambiare sta in due file, senza toccare il codice:

- `config/aree.yaml`: aree scientifiche con fonti e categorie. Per aggiungere
  un'area basta copiare un blocco.
- `config/impostazioni.yaml`: giorni da considerare, modelli Gemini con i loro
  limiti (RPM e RPD), soglie del grafo.

I limiti gratuiti di Gemini dipendono dal progetto: i tuoi sono su
<https://aistudio.google.com/rate-limit>. Riportali in `impostazioni.yaml`.

## Architettura

```
app.py                     avvio e barra laterale
config/                    aree.yaml, impostazioni.yaml
paper_radar/
├── fonti/                 un modulo per fonte + http.py (timeout, retry)
│   └── openalex, arxiv, pubmed, biorxiv (anche medRxiv), chemrxiv
├── llm/
│   ├── llm_client.py      UNICO punto di contatto con il modello
│   ├── rate_limiter.py    limiti al minuto e al giorno
│   ├── schemi.py          forma del JSON (Pydantic)
│   ├── griglie.py         griglie di valutazione per tipo di studio
│   └── prompt.py          il prompt di analisi
├── servizi/
│   ├── raccolta.py        raccolta dalle fonti
│   ├── deduplica.py       riconoscimento dei doppioni
│   ├── testo_completo.py  PDF arXiv e XML di PMC, altrimenti abstract
│   ├── contesto.py        paper collegati da OpenAlex
│   ├── citazioni.py       verifica delle citazioni testuali
│   ├── analisi.py         orchestrazione dell'analisi
│   └── grafo.py           nodi e archi (citazioni + similarità)
├── dati/                  schema.sql e db.py (tutto l'SQL sta qui)
└── ui/                    pagine, componenti e grafo interattivo (vis-network)
tests/                     test automatici (senza rete)
scripts/                   verifica e confronto tra modelli
esempi/                    set fisso di paper e output reali
```

Ogni strato usa solo quello sotto: interfaccia → servizi → fonti / modello / database.

**Come nasce un'analisi**

1. Se è già nel database, viene letta da lì.
2. Si scaricano da OpenAlex i paper collegati.
3. Si recupera il testo: completo se disponibile legalmente (arXiv, PMC open
   access), altrimenti l'abstract; la scheda dichiara quale.
4. Una sola richiesta a Gemini restituisce tutto in JSON.
5. Il JSON è validato con Pydantic; se è malformato si riprova.
6. Il codice verifica le citazioni, completa la griglia e scarta dal contesto
   ogni paper non fornito da OpenAlex.

**Come si rispetta il piano gratuito**

- Coda di analisi elaborata un paper alla volta.
- Rate limiter per modello: aspetta se il minuto è pieno, si ferma se la quota
  del giorno è finita.
- Sugli errori 429 riprova con attese crescenti; se persistono passa al modello
  più leggero.
- Per cambiare provider basta una nuova classe con il metodo
  `genera(modello, prompt)` da passare a `LLMClient`.

## Test

```bash
python -m pytest
```

I test non usano la rete: coprono raccolta, deduplica, validazione del JSON,
rate limiter, verifica delle citazioni e grafo.

## Confrontare versioni del modello

`esempi/set_fisso.yaml` elenca un piccolo insieme fisso di paper. Lo script
rifà l'analisi da zero su quei paper e salva i risultati per modello:

```bash
python scripts/rianalizza_set_fisso.py                          # modelli in configurazione
python scripts/rianalizza_set_fisso.py --modello gemini-3.5-flash-lite
```

La cartella contiene già un output reale prodotto dall'app
(`esempi/output/app/`). Su Windows: doppio clic su `esempi.bat`. I risultati vanno in
`esempi/output/<modello>/`, con un `riepilogo.md` che confronta base del testo,
tipo di studio e citazioni verificate. Usa una richiesta per paper.

## Limiti noti

- **Poche dipendenze, per scelta.** TF-IDF, tabelle e barre sono scritti in
  Python puro: su alcuni PC Windows il "Controllo app intelligente" blocca i
  file binari di NumPy, pandas e PyArrow, e l'app deve funzionare lo stesso.
  Per questo il grafo usa una copia locale di
  [vis-network](https://visjs.github.io/vis-network/) (licenza Apache-2.0 o MIT)
  invece di un componente Streamlit.
- **Un clic su un nodo ricarica la pagina**: i filtri della barra laterale
  tornano ai valori iniziali.

- **L'analisi è prodotta da un modello linguistico e può sbagliare.** La
  verifica automatica controlla che le citazioni esistano nel testo, non che
  l'interpretazione sia corretta. Non sostituisce la lettura del paper.
- **Spesso si lavora sul solo abstract.** In quel caso limiti, conflitti di
  interesse e dettagli dei metodi risultano "non rilevabili".
- **I paper appena usciti hanno pochi collegamenti.** OpenAlex impiega giorni
  o settimane a registrare riferimenti e citazioni; nel frattempo contesto e
  grafo si basano soprattutto sulla similarità. Il pulsante "Aggiorna i
  collegamenti" permette di riprovare.
- **"Pubblicato su rivista" non garantisce la revisione tra pari**: è dedotto
  dai metadati di OpenAlex.
- **Il conteggio delle richieste è locale**: non vede le richieste fatte con la
  stessa chiave da altri programmi.
- **La similarità TF-IDF guarda le parole, non il significato**, e funziona
  meglio quando il database contiene già molti paper.
- **La coda si elabora con l'app aperta**: non c'è un processo in background.
- Il piano gratuito di Gemini può usare i testi inviati per migliorare i
  prodotti Google: qui si inviano solo paper pubblici.
