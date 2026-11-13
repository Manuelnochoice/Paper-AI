-- Schema del database SQLite di Paper Radar.

-- Ogni paper visto dall'app: sia quelli raccolti nel feed (origine = 'feed')
-- sia quelli scoperti come collegati a un altro paper (origine = 'collegato').
CREATE TABLE IF NOT EXISTS paper (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    titolo             TEXT NOT NULL,
    titolo_norm        TEXT,               -- titolo senza punteggiatura, per la deduplica
    titolo_it          TEXT,               -- titolo tradotto in italiano (NULL = non ancora tradotto)
    abstract_it        TEXT,               -- abstract tradotto in italiano
    abstract           TEXT DEFAULT '',
    autori             TEXT DEFAULT '[]',  -- elenco JSON
    data_pubblicazione TEXT DEFAULT '',    -- AAAA-MM-GG
    doi                TEXT,
    arxiv_id           TEXT,
    pmid               TEXT,
    pmcid              TEXT,
    openalex_id        TEXT,
    fonte              TEXT,
    sede               TEXT DEFAULT '',
    stato              TEXT DEFAULT 'sconosciuto',  -- preprint | rivista | sconosciuto
    url                TEXT DEFAULT '',
    url_pdf            TEXT DEFAULT '',
    n_citazioni        INTEGER,
    riferimenti        TEXT DEFAULT '[]',  -- id OpenAlex dei paper citati (JSON)
    correlati          TEXT DEFAULT '[]',  -- id OpenAlex dei paper correlati (JSON)
    origine            TEXT DEFAULT 'feed',
    raccolto_il        TEXT,               -- quando è entrato nel database
    mostrato_il        TEXT,               -- giorno in cui è comparso nel feed (NULL = mai)
    collegamenti_il    TEXT                -- ultimo aggiornamento dei collegamenti OpenAlex
);
CREATE INDEX IF NOT EXISTS idx_paper_doi      ON paper(doi);
CREATE INDEX IF NOT EXISTS idx_paper_arxiv    ON paper(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_paper_pmid     ON paper(pmid);
CREATE INDEX IF NOT EXISTS idx_paper_openalex ON paper(openalex_id);
CREATE INDEX IF NOT EXISTS idx_paper_titolo   ON paper(titolo_norm);
CREATE INDEX IF NOT EXISTS idx_paper_data     ON paper(data_pubblicazione);

-- Un paper può appartenere a più aree.
CREATE TABLE IF NOT EXISTS paper_area (
    paper_id INTEGER NOT NULL REFERENCES paper(id),
    area     TEXT NOT NULL,
    PRIMARY KEY (paper_id, area)
);

-- Analisi prodotta dal modello: una sola per paper, mai rifatta.
CREATE TABLE IF NOT EXISTS analisi (
    paper_id    INTEGER PRIMARY KEY REFERENCES paper(id),
    contenuto   TEXT NOT NULL,     -- JSON validato
    modello     TEXT NOT NULL,
    base_testo  TEXT NOT NULL,     -- 'testo completo' oppure 'abstract'
    creata_il   TEXT NOT NULL
);

-- Archi del grafo che nascono da dati reali di OpenAlex.
-- tipo = 'cita'      : da_id cita a_id
-- tipo = 'correlato' : OpenAlex indica a_id come correlato a da_id
CREATE TABLE IF NOT EXISTS collegamento (
    da_id INTEGER NOT NULL REFERENCES paper(id),
    a_id  INTEGER NOT NULL REFERENCES paper(id),
    tipo  TEXT NOT NULL,
    PRIMARY KEY (da_id, a_id, tipo)
);

CREATE TABLE IF NOT EXISTS da_leggere (
    paper_id    INTEGER PRIMARY KEY REFERENCES paper(id),
    note        TEXT DEFAULT '',
    aggiunto_il TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossario (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    termine     TEXT NOT NULL,
    definizione TEXT NOT NULL,
    paper_id    INTEGER REFERENCES paper(id)
);

-- Paper in attesa di analisi.
CREATE TABLE IF NOT EXISTS coda_analisi (
    paper_id    INTEGER PRIMARY KEY REFERENCES paper(id),
    aggiunto_il TEXT NOT NULL,
    errore      TEXT
);

-- Preferenze dell'utente e piccoli promemoria dell'app (tema, ultima raccolta automatica...).
CREATE TABLE IF NOT EXISTS preferenza (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL
);

-- Richieste fatte al modello, per giorno: serve al limite giornaliero (RPD).
CREATE TABLE IF NOT EXISTS uso_llm (
    giorno    TEXT NOT NULL,
    modello   TEXT NOT NULL,
    richieste INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (giorno, modello)
);
