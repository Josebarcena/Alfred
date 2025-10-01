import json, requests
# --- Ollama fallback (mínimo) ---
def _ollama_generate_json_from_chunk(chunk: str, orders_spec: dict, model: str = "llama3.1") -> dict | None:
    """
    Intenta que Ollama devuelva un JSON válido de una única orden o 'orders':[] para múltiples.
    Devuelve el dict ya cargado con json.loads o None si falla.
    """
    prompt = (
        "Convierte la instrucción de usuario en JSON de órdenes siguiendo este esquema.\n"
        "Salida STRICTA:\n"
        '- Si es UNA orden: {"domain": "...", "command": "...", "args": {...}}\n'
        '- Si son VARIAS:  {"orders": [ {"domain": "...", "command": "...", "args": {...}}, ... ]}\n'
        "NO añadas texto fuera del JSON. NO inventes dominios/comandos/parametros; usa solo los de Orders.json.\n"
        "Si algún parámetro no aplica, omítelo de 'args'.\n\n"
        f"Orders.json:\n{json.dumps(orders_spec, ensure_ascii=False)}\n\n"
        f"Instrucción:\n{chunk}\n"
    )

    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=10
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if not text:
            return None
        return json.loads(text)  # devolver dict
    except Exception:
        return None
    
def _ollama_propose_alias_from_chunk(chunk: str, orders_spec: dict, model: str = "llama3.1") -> tuple[str, dict] | None:
    """
    Devuelve (pattern, args_map) o None.
    pattern: string con '*' para wildcards (máximo 2-3 si puedes), en minúsculas.
    args_map: { param_name: "$1" | "$2" | texto literal }
    """
    try:
        import requests
    except Exception:
        return None

    prompt = (
        "Diseña un alias para mapear la instrucción del usuario a un comando existente.\n"
        "Salida STRICTA (JSON solo): {\"pattern\":\"...\", \"args_map\":{...}}\n"
        "Reglas:\n"
        "- Usa '*' como comodín (equivale a (.*)). Máximo 3.\n"
        "- Usa valores $1, $2, ... en args_map para extraer de los comodines.\n"
        "- Usa SOLO nombres de parámetros que existan en Orders.json.\n"
        "- NO inventes dominios ni comandos; solo su patrón.\n\n"
        f"Orders.json:\n{json.dumps(orders_spec, ensure_ascii=False)}\n\n"
        f"Instrucción del usuario:\n{chunk}\n"
    )
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=10
        )
        resp.raise_for_status()
        txt = resp.json().get("response", "").strip()
        if not txt:
            return None
        data = json.loads(txt)
        pat = data.get("pattern")
        amap = data.get("args_map")
        if isinstance(pat, str) and isinstance(amap, dict):
            return (pat.strip().lower(), amap)
    except Exception:
        pass
    return None