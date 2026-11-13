# 🔭 Paper Radar

[🇮🇹 Italiano](README.md) · 🇬🇧 English

A local app to **follow new science and understand it**. It collects papers
published in the last few days across eleven fields and, for the ones you pick,
produces an expert-level explanation, a plain-language explanation, a
reliability and bias card, the paper's place in the wider picture, and a graph
of related papers.

It runs locally on Windows (macOS and Linux work too). Stack: **Python,
Streamlit, SQLite**, with the **Gemini** free tier for the analyses.

> The interface, the analyses and the code comments are in Italian.

## What it does

- **Collection without repeats.** Recent papers only, sorted by date. Every
  paper already shown moves to the *Archive* the next day, so *What's new* only
  lists papers you have never seen.
- **Two explanations.** One for people in the field, one for everyone else.
- **Reliability card.** Study type, preprint or journal, sample size, stated
  limitations, possible biases, declared conflicts of interest. The evaluation
  grid depends on the study type (clinical, experimental, computational,
  theoretical, review, other).
- **Checked quotes.** Every claim carries a sentence copied from the paper, and
  the code checks that the sentence really appears in the text. Missing
  information is reported as "non rilevabile" (not detectable).
- **Context from real data.** The wider-picture section uses only the related
  papers returned by OpenAlex (references, citations, related works), never the
  model's memory.
- **Interactive graph.** Edges come from OpenAlex citations and from abstract
  similarity (TF-IDF, computed locally). Nodes can be dragged, the wheel zooms
  and clicking a node opens that paper.
- **Lists in Italian.** Titles and abstracts are translated when they appear in
  a list, in batches and only once, with the lighter model.
- **Automatic collection.** The first launch of each day fetches new papers in
  every field.
- **Reading tools.** A "to read" list with personal notes, a searchable
  glossary, tables and charts, light or dark theme.

## Screenshots

To be added: save the images in `docs/` (list of new papers, reliability
card, graph) and link them here.

## Step-by-step installation (Windows)

1. **Install Python 3.10 or later** from [python.org](https://www.python.org/downloads/)
   and tick "Add Python to PATH".
2. **Get the project**: `git clone <repository-url>`, or download the ZIP from
   GitHub and extract it.
3. **Create the two free keys**:
   - Gemini: <https://aistudio.google.com/apikey>
   - OpenAlex: <https://openalex.org/settings/api>
4. **Create the `.env` file**: copy `.env.example`, rename it to `.env` and
   paste the keys after the `=` sign. `.env` never reaches GitHub (it is listed
   in `.gitignore`).
5. **Check that everything works**: double-click `verifica.bat`. The first run
   installs the libraries (a few minutes), then runs the tests and checks keys,
   sources and the graph against real data.
6. **Start the app**: double-click `avvia.bat`. Your browser opens
   <http://localhost:8501>.

On macOS or Linux, or by hand:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/verifica_configurazione.py
streamlit run app.py
```

## How to use it

1. On launch the app collects the day's papers by itself. To fetch more, pick
   the fields in the sidebar (none = all) and press **Cerca nuovi paper**.
2. Open a paper and press **Analizza ora**, or use **Metti in coda** on several
   papers and then **Elabora la coda**.
3. Read the tabs. In "Contesto e grafo", click nodes to move between related
   papers.

A paper is analysed only when you ask, and each analysis is stored in the
database and never redone. The sidebar shows the requests left for today.

## Configuration

Everything that may change lives in two files, with no code changes:

- `config/aree.yaml`: fields with their sources and categories. Copy a block to
  add a field.
- `config/impostazioni.yaml`: number of days, automatic collection, Gemini
  models with their limits (RPM and RPD), translation model, graph thresholds.

Gemini free-tier limits are per project: yours are listed at
<https://aistudio.google.com/rate-limit>. Copy them into `impostazioni.yaml`.

## Architecture

```
app.py                     entry point and sidebar
config/                    aree.yaml, impostazioni.yaml
paper_radar/
├── fonti/                 one module per source + http.py (timeouts, retries)
│   └── openalex, arxiv, pubmed, biorxiv (also medRxiv), chemrxiv
├── llm/
│   ├── llm_client.py      the ONLY module that talks to the model
│   ├── rate_limiter.py    per-minute and per-day limits
│   ├── schemi.py          JSON shape (Pydantic)
│   ├── griglie.py         evaluation grids per study type
│   └── prompt.py          the analysis prompt
├── servizi/
│   ├── raccolta.py        collection from the sources
│   ├── deduplica.py       duplicate detection
│   ├── testo_completo.py  open-access PDFs and PMC XML, otherwise the abstract
│   ├── traduzione.py      titles and abstracts in Italian
│   ├── contesto.py        related papers from OpenAlex
│   ├── citazioni.py       quote verification
│   ├── analisi.py         analysis orchestration
│   └── grafo.py           nodes and edges (citations + similarity)
├── dati/                  schema.sql and db.py (all SQL lives here)
└── ui/                    pages, components, SVG charts and the interactive graph (vis-network)
tests/                     automated tests (no network)
scripts/                   setup check and model comparison
esempi/                    fixed paper set and real outputs
```

Each layer only uses the one below: interface → services → sources / model / database.

**How an analysis is built**

1. If it is already in the database, it is read from there.
2. Related papers are fetched from OpenAlex.
3. The text is retrieved: full text when legally available (arXiv, PMC open
   access, open-access PDFs listed by OpenAlex), otherwise the abstract; the
   card states which one was used. An abstract-only analysis can be redone with
   **Riprova col testo completo**, which spends a request only if the text is found.
4. A single Gemini request returns everything as JSON.
5. The JSON is validated with Pydantic; malformed output triggers a retry.
6. The code verifies the quotes, completes the grid and removes from the
   context any paper that OpenAlex did not provide.

**How the free tier is respected**

- The analysis queue is processed one paper at a time.
- A rate limiter per model waits when the minute is full and stops when the
  daily quota is used up.
- On 429 errors it retries with increasing waits; if they persist it falls back
  to the lighter model.
- To switch provider, write a class with a `genera(modello, prompt)` method and
  pass it to `LLMClient`.

## Tests

```bash
python -m pytest
```

The tests use no network. They cover collection, deduplication, JSON
validation, the rate limiter, quote verification, translation, full text and the graph.

## Comparing model versions

`esempi/set_fisso.yaml` lists a small fixed set of papers. The script redoes
the analysis from scratch on those papers and saves the results per model:

```bash
python scripts/rianalizza_set_fisso.py                          # models from the configuration
python scripts/rianalizza_set_fisso.py --modello gemini-3.5-flash-lite
```

The folder already holds one real output produced by the app
(`esempi/output/app/`). On Windows: double-click `esempi.bat`. Results go to
`esempi/output/<model>/`, with a `riepilogo.md` comparing text basis, study
type and verified quotes. It uses one request per paper.

## Known limitations

- **Few dependencies, on purpose.** TF-IDF, tables and charts (SVG) are plain Python:
  on some Windows PCs "Smart App Control" blocks the binary files of NumPy,
  pandas and PyArrow, and the app has to work anyway. For the same reason the
  graph uses a bundled copy of
  [vis-network](https://visjs.github.io/vis-network/) (Apache-2.0 or MIT)
  instead of a Streamlit component.
- **Clicking a node reloads the page**: sidebar filters go back to their
  defaults.

- **The analysis is written by a language model and can be wrong.** The
  automatic check confirms that quotes exist in the text, not that the
  interpretation is right. It does not replace reading the paper.
- **Full text exists only for open-access papers.** Paywalled articles cannot
  be read, and some sites refuse automated downloads. The analysis then uses
  the abstract: limitations, conflicts of interest and method details come out
  as "non rilevabile".
- **Translations are automatic** and spend requests of the lighter model (one
  batch of papers per request). They can be switched off in the sidebar.
- **Brand-new papers have few links.** OpenAlex takes days or weeks to record
  references and citations; until then context and graph rely mostly on
  similarity. The "Aggiorna i collegamenti" button retries later.
- **"Published in a journal" does not guarantee peer review**: it is inferred
  from OpenAlex metadata.
- **The request counter is local**: it cannot see requests made with the same
  key by other programs.
- **TF-IDF similarity compares words, not meaning**, and works better once the
  database holds many papers.
- **The queue runs while the app is open**: there is no background process.
- The Gemini free tier may use submitted text to improve Google products; only
  public papers are sent.
