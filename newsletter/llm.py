"""Appel au modèle d'IA (API Google Gemini, offre gratuite), sans bibliothèque externe.

La clé est lue dans la variable d'environnement GEMINI_API_KEY (un secret GitHub).
Le modèle se fixe avec GEMINI_MODEL ; sinon, le plus récent des modèles « flash » stables
proposés à la clé est choisi automatiquement (Google retire régulièrement les anciens).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
EXCLUDED = ("lite", "image", "tts", "audio", "live", "embedding", "thinking", "exp", "preview", "8b")
_resolved_model: str | None = None
TIMEOUT_S = 300
RETRIES = 4


class LLMError(RuntimeError):
    pass


def _version(name: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", name.split("/")[-1])[:3])


def resolve_model(key: str) -> str:
    """Modèle fixé par GEMINI_MODEL, sinon le plus récent modèle flash stable disponible."""
    global _resolved_model
    if os.environ.get("GEMINI_MODEL"):
        return os.environ["GEMINI_MODEL"]
    if _resolved_model:
        return _resolved_model
    request = urllib.request.Request(MODELS_URL, headers={"x-goog-api-key": key})
    with urllib.request.urlopen(request, timeout=60) as response:
        models = json.loads(response.read()).get("models", [])
    candidates = [
        m["name"].split("/")[-1] for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
        and "flash" in m["name"] and not any(x in m["name"] for x in EXCLUDED)
    ]
    if not candidates:
        raise LLMError("Aucun modèle Gemini flash disponible pour cette clé ; fixer GEMINI_MODEL.")
    _resolved_model = max(candidates, key=_version)
    print(f"    Modèle choisi : {_resolved_model}")
    return _resolved_model


def generate(prompt: str, *, system: str = "", as_json: bool = False, temperature: float = 0.4) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError("La variable GEMINI_API_KEY est absente (secret GitHub à créer).")
    model = resolve_model(key)

    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    request = urllib.request.Request(
        API_URL.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )

    last_error = ""
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                payload = json.loads(response.read())
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                return text
            last_error = f"réponse vide : {json.dumps(payload)[:300]}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            last_error = f"HTTP {exc.code} : {detail}"
            if exc.code not in (429, 500, 502, 503, 504):
                break  # erreur de clé ou de requête : inutile de réessayer
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError) as exc:
            last_error = str(exc)
        time.sleep(15 * (attempt + 1))  # quota gratuit : on laisse passer la minute
    raise LLMError(f"Échec de l'appel à {model} : {last_error}")


def generate_json(prompt: str, *, system: str = "", temperature: float = 0.2):
    text = generate(prompt, system=system, as_json=True, temperature=temperature)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text)
