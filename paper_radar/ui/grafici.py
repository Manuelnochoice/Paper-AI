"""Piccoli grafici disegnati in SVG, senza librerie esterne.

SVG è un formato di immagine fatto di testo: un grafico a barre è solo un
elenco di rettangoli con posizione e misura. Scriverli a mano tiene il
progetto leggero e funziona su qualunque PC. `currentColor` fa sì che le
scritte prendano il colore del tema (chiaro o scuro).
"""
from __future__ import annotations

from html import escape

import streamlit as st

BLU = "#2E6F95"
COLORI_ESITO = {"sì": "#3A8F5C", "parziale": "#E0A526", "no": "#D1495B", "non rilevabile": "#9AA5B1"}
COLORI_VERIFICA = {"verificata": "#3A8F5C", "approssimata": "#E0A526", "non verificata": "#D1495B"}


def _mostra(svg: str) -> None:
    st.html(f'<div style="width:100%;overflow-x:auto">{svg}</div>')


def barre_orizzontali(valori: dict[str, int], colori: dict[str, str] | None = None, larghezza: int = 460) -> None:
    """Una barra per voce, con etichetta a sinistra e numero a destra."""
    massimo = max(valori.values(), default=0)
    if massimo == 0:
        return
    riga, margine = 26, 150                       # altezza di una riga, spazio per le etichette
    spazio_barre = larghezza - margine - 40
    parti = []
    for i, (etichetta, n) in enumerate(valori.items()):
        y = i * riga
        lunga = max(spazio_barre * n / massimo, 1 if n else 0)
        colore = (colori or {}).get(etichetta, BLU)
        parti.append(
            f'<text x="{margine - 8}" y="{y + 17}" text-anchor="end" font-size="13" fill="currentColor">'
            f'{escape(str(etichetta)[:22])}</text>'
            f'<rect x="{margine}" y="{y + 4}" width="{lunga:.1f}" height="18" rx="3" fill="{colore}"/>'
            f'<text x="{margine + lunga + 6:.1f}" y="{y + 17}" font-size="13" fill="currentColor">{n}</text>')
    altezza = len(valori) * riga + 4
    _mostra(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {larghezza} {altezza}" '
            f'width="{larghezza}" height="{altezza}" font-family="sans-serif">{"".join(parti)}</svg>')


def colonne(valori: dict[str, int], larghezza: int = 640, altezza: int = 200) -> None:
    """Una colonna per voce (es. un anno o un giorno), con il numero sopra."""
    massimo = max(valori.values(), default=0)
    if massimo == 0:
        return
    passo = (larghezza - 20) / len(valori)
    larga = min(passo * 0.7, 46)
    base = altezza - 26                           # riga di base delle colonne
    ogni = max(len(valori) // 12, 1)              # con molte colonne si scrive un'etichetta ogni tante
    parti = [f'<line x1="10" y1="{base}" x2="{larghezza - 10}" y2="{base}" stroke="currentColor" opacity="0.3"/>']
    for i, (etichetta, n) in enumerate(valori.items()):
        x = 10 + i * passo + (passo - larga) / 2
        alta = (base - 22) * n / massimo
        parti.append(f'<rect x="{x:.1f}" y="{base - alta:.1f}" width="{larga:.1f}" height="{alta:.1f}" rx="3" fill="{BLU}"/>')
        parti.append(f'<text x="{x + larga / 2:.1f}" y="{base - alta - 5:.1f}" text-anchor="middle" '
                     f'font-size="12" fill="currentColor">{n}</text>')
        if i % ogni == 0:
            parti.append(f'<text x="{x + larga / 2:.1f}" y="{altezza - 8}" text-anchor="middle" '
                         f'font-size="12" fill="currentColor">{escape(str(etichetta))}</text>')
    _mostra(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {larghezza} {altezza}" '
            f'width="{larghezza}" height="{altezza}" font-family="sans-serif">{"".join(parti)}</svg>')


def barra_composta(valori: dict[str, int], colori: dict[str, str], larghezza: int = 460) -> None:
    """Un'unica barra divisa in tratti colorati (es. citazioni verificate / non trovate), con legenda."""
    totale = sum(valori.values())
    if totale == 0:
        return
    parti, x = [], 0.0
    for etichetta, n in valori.items():
        lunga = larghezza * n / totale
        if n:
            parti.append(f'<rect x="{x:.1f}" y="0" width="{lunga:.1f}" height="18" fill="{colori.get(etichetta, BLU)}"/>')
        x += lunga
    legenda, x = [], 0
    for etichetta, n in valori.items():
        legenda.append(f'<rect x="{x}" y="28" width="11" height="11" rx="2" fill="{colori.get(etichetta, BLU)}"/>'
                       f'<text x="{x + 16}" y="38" font-size="12" fill="currentColor">{escape(etichetta)}: {n}</text>')
        x += 150
    _mostra(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {larghezza} 46" width="{larghezza}" '
            f'height="46" font-family="sans-serif">{"".join(parti)}{"".join(legenda)}</svg>')
