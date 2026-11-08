"""Fiche pays du jour : choix du pays et données de base (Wikipédia, Banque mondiale).

Les 197 pays passent chacun leur tour, dans un ordre mélangé une fois pour toutes :
aucun pays ne revient avant que tous les autres soient passés.
"""

from __future__ import annotations

import csv
import json
import random
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "pays.csv"
START = date(2026, 1, 1)
USER_AGENT = "newsletter-collector/1.0 (projet personnel)"

INDICATORS = {
    "SP.POP.TOTL": "Population",
    "NY.GDP.MKTP.CD": "PIB (dollars courants)",
    "NY.GDP.PCAP.CD": "PIB par habitant (dollars courants)",
    "NY.GDP.MKTP.KD.ZG": "Croissance du PIB (%)",
    "FP.CPI.TOTL.ZG": "Inflation (%)",
    "SP.DYN.LE00.IN": "Espérance de vie (années)",
    "SL.UEM.TOTL.ZS": "Chômage (% de la population active)",
}


def all_countries() -> list[dict]:
    with DATA.open(encoding="utf-8") as f:
        countries = list(csv.DictReader(f, delimiter=";"))
    random.Random(2026).shuffle(countries)  # ordre fixe, mais pas alphabétique
    return countries


def country_of_the_day(day: date) -> dict:
    countries = all_countries()
    return countries[(day - START).days % len(countries)]


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def wikipedia_summary(title: str) -> str:
    url = "https://fr.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
    try:
        return _get_json(url).get("extract", "")
    except Exception as exc:
        return f"(résumé Wikipédia indisponible : {exc})"


def world_bank_indicators(iso3: str) -> dict[str, str]:
    """Dernière valeur connue de chaque indicateur, avec son année."""
    values = {}
    for code, label in INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/{iso3}/indicator/{code}?format=json&mrv=1"
        try:
            data = _get_json(url)
            point = data[1][0] if len(data) > 1 and data[1] else None
        except Exception:
            point = None
        if point and point.get("value") is not None:
            values[label] = f"{point['value']:,.1f} ({point['date']})".replace(",", " ")
    return values


def country_context(country: dict, articles: list[dict]) -> dict:
    names = {country["nom"].lower(), country["name"].lower()}
    related = [
        a for a in articles
        if any(n in (a["title"] + " " + a["summary"]).lower() for n in names)
    ][:15]
    return {
        "nom": country["nom"],
        "iso3": country["iso3"],
        "wikipedia": wikipedia_summary(country["wiki"]),
        "indicateurs": world_bank_indicators(country["iso3"]),
        "articles": related,
    }
