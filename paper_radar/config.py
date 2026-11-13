"""Lettura della configurazione: file YAML e chiavi segrete dal file .env.

Le chiavi API non compaiono mai nel codice: vengono lette dalle variabili
d'ambiente, che `python-dotenv` carica dal file `.env` nella cartella del progetto.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Cartella principale del progetto (quella che contiene app.py).
RADICE = Path(__file__).resolve().parent.parent

# "utf-8-sig" tollera il segno invisibile (BOM) che Blocco note di Windows
# a volte aggiunge all'inizio dei file.
load_dotenv(RADICE / ".env", encoding="utf-8-sig")


def _leggi_yaml(percorso: Path) -> dict:
    with open(percorso, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def carica_impostazioni() -> dict:
    """Impostazioni generali (config/impostazioni.yaml)."""
    return _leggi_yaml(RADICE / "config" / "impostazioni.yaml")


def carica_aree() -> dict:
    """Aree scientifiche e fonti associate (config/aree.yaml)."""
    return _leggi_yaml(RADICE / "config" / "aree.yaml")


def chiave(nome: str) -> str | None:
    """Restituisce una chiave segreta (es. GEMINI_API_KEY) oppure None se manca."""
    valore = os.getenv(nome, "").strip()
    return valore or None


def percorso_database(impostazioni: dict) -> Path:
    percorso = RADICE / impostazioni.get("database", "dati/paper_radar.db")
    percorso.parent.mkdir(parents=True, exist_ok=True)
    return percorso
