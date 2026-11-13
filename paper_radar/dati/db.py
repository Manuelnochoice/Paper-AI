"""Accesso al database SQLite.

Tutto il codice SQL dell'app sta in questo file: il resto del programma
chiama solo queste funzioni e non conosce i dettagli delle tabelle.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from paper_radar.modelli import PaperGrezzo
from paper_radar.servizi.deduplica import chiavi, normalizza_doi, normalizza_titolo

SCHEMA = Path(__file__).with_name("schema.sql")


def connetti(percorso: str | Path) -> sqlite3.Connection:
    """Apre il database (creandolo se non esiste) e prepara le tabelle."""
    # check_same_thread=False: Streamlit esegue l'app su più thread.
    conn = sqlite3.connect(str(percorso), check_same_thread=False)
    conn.row_factory = sqlite3.Row          # righe leggibili per nome di colonna
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    _aggiorna_schema(conn)
    conn.commit()
    return conn


def _aggiorna_schema(conn) -> None:
    """Aggiunge a un database creato da una versione precedente le colonne nuove.

    "CREATE TABLE IF NOT EXISTS" non modifica una tabella che esiste già:
    le colonne aggiunte in seguito vanno create a mano, una volta sola.
    """
    presenti = {riga["name"] for riga in conn.execute("PRAGMA table_info(paper)")}
    for colonna in ("titolo_it", "abstract_it"):
        if colonna not in presenti:
            conn.execute(f"ALTER TABLE paper ADD COLUMN {colonna} TEXT")


def _adesso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _oggi() -> str:
    return date.today().isoformat()


def _in_dizionario(riga: sqlite3.Row | None) -> dict | None:
    """Converte una riga in dizionario, decodificando le colonne JSON."""
    if riga is None:
        return None
    d = dict(riga)
    for colonna in ("autori", "riferimenti", "correlati"):
        if colonna in d:
            d[colonna] = json.loads(d[colonna] or "[]")
    return d


# ---------------------------------------------------------------- paper

def trova_esistente(conn, paper: PaperGrezzo) -> int | None:
    """Cerca un paper già salvato che corrisponde a quello dato (deduplica)."""
    for colonna, valore in chiavi(paper).items():
        riga = conn.execute(f"SELECT id FROM paper WHERE {colonna} = ? LIMIT 1", (valore,)).fetchone()
        if riga:
            return riga["id"]
    return None


def salva_paper(conn, paper: PaperGrezzo, area: str | None = None, origine: str = "feed") -> tuple[int, bool]:
    """Salva un paper se è nuovo; se esiste già ne completa i dati mancanti.

    Restituisce (id del paper, True se è nuovo per il feed).
    """
    esistente = trova_esistente(conn, paper)
    campi = {
        "abstract": paper.abstract,
        "doi": normalizza_doi(paper.doi),
        "arxiv_id": paper.arxiv_id,
        "pmid": paper.pmid,
        "pmcid": paper.pmcid,
        "openalex_id": paper.openalex_id,
        "sede": paper.sede,
        "url": paper.url,
        "url_pdf": paper.url_pdf,
        "n_citazioni": paper.n_citazioni,
        "data_pubblicazione": paper.data_pubblicazione,
    }

    if esistente is None:
        cur = conn.execute(
            """INSERT INTO paper (titolo, titolo_norm, autori, fonte, stato, riferimenti, correlati,
                                  origine, raccolto_il, abstract, doi, arxiv_id, pmid, pmcid, openalex_id,
                                  sede, url, url_pdf, n_citazioni, data_pubblicazione)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (paper.titolo, normalizza_titolo(paper.titolo), json.dumps(paper.autori, ensure_ascii=False),
             paper.fonte, paper.stato, json.dumps(paper.riferimenti), json.dumps(paper.correlati),
             origine, _adesso(), *campi.values()),
        )
        paper_id, nuovo = cur.lastrowid, origine == "feed"
    else:
        paper_id = esistente
        vecchio = dict(conn.execute("SELECT * FROM paper WHERE id = ?", (paper_id,)).fetchone())
        # Completa solo le colonne vuote: non si sovrascrive ciò che c'è già.
        da_aggiornare = {c: v for c, v in campi.items() if v not in (None, "") and vecchio[c] in (None, "")}
        if paper.riferimenti and vecchio["riferimenti"] in (None, "[]"):
            da_aggiornare["riferimenti"] = json.dumps(paper.riferimenti)
        if paper.correlati and vecchio["correlati"] in (None, "[]"):
            da_aggiornare["correlati"] = json.dumps(paper.correlati)
        if paper.stato != "sconosciuto" and vecchio["stato"] == "sconosciuto":
            da_aggiornare["stato"] = paper.stato
        # Un paper conosciuto solo come "collegato" che ora arriva dal feed diventa del feed.
        nuovo = origine == "feed" and vecchio["origine"] != "feed"
        if nuovo:
            da_aggiornare.update(origine="feed", raccolto_il=_adesso())
        if da_aggiornare:
            assegnazioni = ", ".join(f"{c} = ?" for c in da_aggiornare)
            conn.execute(f"UPDATE paper SET {assegnazioni} WHERE id = ?", (*da_aggiornare.values(), paper_id))

    if area:
        conn.execute("INSERT OR IGNORE INTO paper_area (paper_id, area) VALUES (?, ?)", (paper_id, area))
    conn.commit()
    return paper_id, nuovo


def leggi_paper(conn, paper_id: int) -> dict | None:
    d = _in_dizionario(conn.execute("SELECT * FROM paper WHERE id = ?", (paper_id,)).fetchone())
    if d:
        d["aree"] = [r["area"] for r in conn.execute(
            "SELECT area FROM paper_area WHERE paper_id = ? ORDER BY area", (paper_id,))]
    return d


def elenca_paper(conn, vista: str, aree: list[str] | None = None, dal: str | None = None,
                 al: str | None = None, testo: str = "", limite: int = 20, oggi: str | None = None) -> list[dict]:
    """Paper del feed, dal più recente.

    vista = 'novita'  : mai mostrati, oppure mostrati per la prima volta oggi
    vista = 'archivio': mostrati in un giorno precedente
    """
    oggi = oggi or _oggi()
    condizioni, valori = ["p.origine = 'feed'"], []
    if vista == "novita":
        condizioni.append("(p.mostrato_il IS NULL OR p.mostrato_il = ?)")
        valori.append(oggi)
    else:
        condizioni.append("p.mostrato_il < ?")
        valori.append(oggi)
    if aree:
        segnaposto = ",".join("?" * len(aree))
        condizioni.append(f"p.id IN (SELECT paper_id FROM paper_area WHERE area IN ({segnaposto}))")
        valori += aree
    if dal:
        condizioni.append("p.data_pubblicazione >= ?")
        valori.append(dal)
    if al:
        condizioni.append("p.data_pubblicazione <= ?")
        valori.append(al)
    if testo.strip():
        # Cerca sia nel testo originale sia nella traduzione italiana.
        condizioni.append("(p.titolo LIKE ? OR p.abstract LIKE ? OR p.titolo_it LIKE ? OR p.abstract_it LIKE ?)")
        valori += [f"%{testo.strip()}%"] * 4

    righe = conn.execute(
        f"""SELECT p.*, (SELECT GROUP_CONCAT(area) FROM paper_area WHERE paper_id = p.id) AS aree_testo,
                   EXISTS(SELECT 1 FROM analisi a WHERE a.paper_id = p.id) AS analizzato
            FROM paper p WHERE {' AND '.join(condizioni)}
            ORDER BY p.data_pubblicazione DESC, p.id DESC LIMIT ?""",
        (*valori, limite),
    ).fetchall()
    return [_in_dizionario(r) for r in righe]


def segna_mostrati(conn, ids: list[int], oggi: str | None = None) -> None:
    """Registra che questi paper sono comparsi nel feed: da domani saranno in archivio."""
    if not ids:
        return
    segnaposto = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE paper SET mostrato_il = ? WHERE mostrato_il IS NULL AND id IN ({segnaposto})",
        (oggi or _oggi(), *ids),
    )
    conn.commit()


def aggiorna_campi(conn, paper_id: int, **campi) -> None:
    """Aggiorna alcune colonne di un paper (le liste vengono salvate come JSON)."""
    campi = {c: json.dumps(v) if isinstance(v, list) else v for c, v in campi.items()}
    assegnazioni = ", ".join(f"{c} = ?" for c in campi)
    conn.execute(f"UPDATE paper SET {assegnazioni} WHERE id = ?", (*campi.values(), paper_id))
    conn.commit()


def id_da_openalex(conn, openalex_ids: list[str]) -> dict[str, int]:
    """Mappa id OpenAlex -> id interno, per i paper già nel database."""
    if not openalex_ids:
        return {}
    segnaposto = ",".join("?" * len(openalex_ids))
    righe = conn.execute(
        f"SELECT id, openalex_id FROM paper WHERE openalex_id IN ({segnaposto})", openalex_ids)
    return {r["openalex_id"]: r["id"] for r in righe}


def paper_con_abstract(conn, limite: int = 3000) -> list[dict]:
    """Paper con abstract, per il calcolo della similarità."""
    righe = conn.execute(
        "SELECT id, titolo, abstract FROM paper WHERE LENGTH(abstract) > 100 ORDER BY id DESC LIMIT ?",
        (limite,))
    return [dict(r) for r in righe]


def salva_traduzione(conn, paper_id: int, titolo_it: str, abstract_it: str) -> None:
    conn.execute("UPDATE paper SET titolo_it = ?, abstract_it = ? WHERE id = ?", (titolo_it, abstract_it, paper_id))
    conn.commit()


def conteggi_feed(conn, dal: str) -> dict:
    """Numeri per i grafici della panoramica: paper per area e per giorno, da una certa data."""
    per_area = conn.execute(
        """SELECT a.area, COUNT(*) AS n FROM paper_area a JOIN paper p ON p.id = a.paper_id
           WHERE p.origine = 'feed' AND p.data_pubblicazione >= ? GROUP BY a.area ORDER BY n DESC""", (dal,))
    per_giorno = conn.execute(
        """SELECT data_pubblicazione AS giorno, COUNT(*) AS n FROM paper
           WHERE origine = 'feed' AND data_pubblicazione >= ? GROUP BY giorno ORDER BY giorno""", (dal,))
    return {"per_area": {r["area"]: r["n"] for r in per_area},
            "per_giorno": {r["giorno"]: r["n"] for r in per_giorno}}


# ---------------------------------------------------------------- preferenze

def leggi_preferenza(conn, chiave: str, predefinito: str = "") -> str:
    riga = conn.execute("SELECT valore FROM preferenza WHERE chiave = ?", (chiave,)).fetchone()
    return riga["valore"] if riga else predefinito


def salva_preferenza(conn, chiave: str, valore: str) -> None:
    conn.execute(
        """INSERT INTO preferenza (chiave, valore) VALUES (?, ?)
           ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore""", (chiave, valore))
    conn.commit()


# ---------------------------------------------------------------- analisi

def leggi_analisi(conn, paper_id: int) -> dict | None:
    riga = conn.execute("SELECT * FROM analisi WHERE paper_id = ?", (paper_id,)).fetchone()
    if riga is None:
        return None
    d = dict(riga)
    d["contenuto"] = json.loads(d["contenuto"])
    return d


def salva_analisi(conn, paper_id: int, contenuto: dict, modello: str, base_testo: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO analisi (paper_id, contenuto, modello, base_testo, creata_il) VALUES (?, ?, ?, ?, ?)",
        (paper_id, json.dumps(contenuto, ensure_ascii=False), modello, base_testo, _adesso()),
    )
    # I termini del glossario finiscono anche nel glossario generale.
    conn.execute("DELETE FROM glossario WHERE paper_id = ?", (paper_id,))
    conn.executemany(
        "INSERT INTO glossario (termine, definizione, paper_id) VALUES (?, ?, ?)",
        [(t["termine"], t["definizione"], paper_id) for t in contenuto.get("glossario", [])],
    )
    conn.execute("DELETE FROM coda_analisi WHERE paper_id = ?", (paper_id,))
    conn.commit()


# ---------------------------------------------------------------- collegamenti

def salva_collegamento(conn, da_id: int, a_id: int, tipo: str) -> None:
    if da_id != a_id:
        conn.execute("INSERT OR IGNORE INTO collegamento (da_id, a_id, tipo) VALUES (?, ?, ?)", (da_id, a_id, tipo))


def collegamenti_di(conn, paper_id: int) -> list[dict]:
    """Archi che toccano il paper, con i dati essenziali del paper all'altro capo."""
    righe = conn.execute(
        """SELECT c.da_id, c.a_id, c.tipo, p.id AS altro_id, p.titolo, p.data_pubblicazione,
                  p.openalex_id, p.n_citazioni, p.abstract, p.sede
           FROM collegamento c
           JOIN paper p ON p.id = CASE WHEN c.da_id = :id THEN c.a_id ELSE c.da_id END
           WHERE c.da_id = :id OR c.a_id = :id""",
        {"id": paper_id},
    )
    return [dict(r) for r in righe]


def collegamenti_tra(conn, ids: list[int]) -> list[dict]:
    """Archi che uniscono tra loro i paper di un insieme."""
    if len(ids) < 2:
        return []
    segnaposto = ",".join("?" * len(ids))
    righe = conn.execute(
        f"SELECT da_id, a_id, tipo FROM collegamento WHERE da_id IN ({segnaposto}) AND a_id IN ({segnaposto})",
        (*ids, *ids))
    return [dict(r) for r in righe]


def impronta_grafo(conn) -> tuple[int, int]:
    """Numero di paper e di collegamenti: se cambia, i grafi vanno ricalcolati."""
    paper = conn.execute("SELECT COUNT(*) FROM paper").fetchone()[0]
    archi = conn.execute("SELECT COUNT(*) FROM collegamento").fetchone()[0]
    return paper, archi


# ---------------------------------------------------------------- da leggere

def salva_da_leggere(conn, paper_id: int, note: str = "") -> None:
    conn.execute(
        """INSERT INTO da_leggere (paper_id, note, aggiunto_il) VALUES (?, ?, ?)
           ON CONFLICT(paper_id) DO UPDATE SET note = excluded.note""",
        (paper_id, note, _adesso()))
    conn.commit()


def rimuovi_da_leggere(conn, paper_id: int) -> None:
    conn.execute("DELETE FROM da_leggere WHERE paper_id = ?", (paper_id,))
    conn.commit()


def nota_da_leggere(conn, paper_id: int) -> str | None:
    """Le note salvate, oppure None se il paper non è nella lista."""
    riga = conn.execute("SELECT note FROM da_leggere WHERE paper_id = ?", (paper_id,)).fetchone()
    return riga["note"] if riga else None


def elenca_da_leggere(conn) -> list[dict]:
    righe = conn.execute(
        """SELECT p.*, d.note, d.aggiunto_il,
                  (SELECT GROUP_CONCAT(area) FROM paper_area WHERE paper_id = p.id) AS aree_testo,
                  EXISTS(SELECT 1 FROM analisi a WHERE a.paper_id = p.id) AS analizzato
           FROM da_leggere d JOIN paper p ON p.id = d.paper_id ORDER BY d.aggiunto_il DESC""")
    return [_in_dizionario(r) for r in righe]


# ---------------------------------------------------------------- coda di analisi

def metti_in_coda(conn, paper_id: int) -> None:
    conn.execute("INSERT OR IGNORE INTO coda_analisi (paper_id, aggiunto_il) VALUES (?, ?)", (paper_id, _adesso()))
    conn.commit()


def togli_dalla_coda(conn, paper_id: int) -> None:
    conn.execute("DELETE FROM coda_analisi WHERE paper_id = ?", (paper_id,))
    conn.commit()


def segna_errore_coda(conn, paper_id: int, errore: str) -> None:
    conn.execute("UPDATE coda_analisi SET errore = ? WHERE paper_id = ?", (errore, paper_id))
    conn.commit()


def elenca_coda(conn) -> list[dict]:
    righe = conn.execute(
        """SELECT p.id, p.titolo, p.data_pubblicazione, c.aggiunto_il, c.errore
           FROM coda_analisi c JOIN paper p ON p.id = c.paper_id ORDER BY c.aggiunto_il""")
    return [dict(r) for r in righe]


def in_coda(conn, paper_id: int) -> bool:
    return conn.execute("SELECT 1 FROM coda_analisi WHERE paper_id = ?", (paper_id,)).fetchone() is not None


# ---------------------------------------------------------------- glossario

def cerca_glossario(conn, testo: str = "") -> list[dict]:
    righe = conn.execute(
        """SELECT g.termine, g.definizione, g.paper_id, p.titolo
           FROM glossario g JOIN paper p ON p.id = g.paper_id
           WHERE g.termine LIKE ? OR g.definizione LIKE ?
           ORDER BY g.termine COLLATE NOCASE""",
        (f"%{testo}%", f"%{testo}%"))
    return [dict(r) for r in righe]


# ---------------------------------------------------------------- uso del modello

class ContatoreSQLite:
    """Conta le richieste fatte oggi a ogni modello, salvandole nel database.

    Così il conteggio sopravvive alla chiusura dell'app.
    """

    def __init__(self, conn):
        self.conn = conn

    def leggi(self, giorno: str, modello: str) -> int:
        riga = self.conn.execute(
            "SELECT richieste FROM uso_llm WHERE giorno = ? AND modello = ?", (giorno, modello)).fetchone()
        return riga["richieste"] if riga else 0

    def imposta(self, giorno: str, modello: str, richieste: int) -> None:
        self.conn.execute(
            """INSERT INTO uso_llm (giorno, modello, richieste) VALUES (?, ?, ?)
               ON CONFLICT(giorno, modello) DO UPDATE SET richieste = excluded.richieste""",
            (giorno, modello, richieste))
        self.conn.commit()
