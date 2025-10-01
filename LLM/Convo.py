# convo.py — feedback natural con Ollama
from __future__ import annotations
import os, json, requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")

SYSTEM = (
    "Eres un mayordomo britanico que explica resultados de comandos de forma ironica elegante,  directa y amistosa.\n"
    "Habla en español. No inventes efectos que no estén en los datos. Sé conciso.\n"
)

def _safe(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)

def llm_feedback(payload: dict, result: dict) -> str:
    """
    Devuelve una frase natural evaluando el resultado.
    Si Ollama falla, retorna un fallback simple.
    """
    ok = bool(result.get("ok"))
    meta = result.get("_meta", {})
    stderr = result.get("stderr") or ""
    stdout = result.get("stdout") or ""
    data = result.get("data") or {}

    prompt = f"""
Datos de la acción (JSON):
- payload:
{_safe(payload)}

- resultado:
{_safe(result)}

Tarea:
1) Di si salió bien o mal.
2) Explica en 1 frase el motivo clave (usa stderr/stdout/meta si aplica).
3) Sugerencia breve (siguiente paso o arreglo). No repitas el JSON, habla natural.
Usa un único párrafo y como máximo 2 frases, salvo que haga falta una viñeta para la sugerencia.
"""

    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": SYSTEM + "\n\n" + prompt,
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=30,
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception:
        # Fallback simple
        if ok:
            return "✅ Hecho. Parece que todo salió bien."
        msg = result.get("error") or (stderr[:200] if stderr else "Hubo un problema.")
        return f"⚠️ No se pudo completar: {msg}"