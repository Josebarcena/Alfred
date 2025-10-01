# bridge.py
import json, sys
from Core.Dispatcher import dispatch

def _run_one(order: dict) -> dict:
    """
    Ejecuta una única orden del tipo:
      {"domain":"chrome","command":"abre","args":{"url":"youtube.com"}}
    """
    domain  = order.get("domain")
    command = order.get("command")
    args    = order.get("args") or {}
    if not domain or not command:
        return {"ok": False, "error": "Faltan 'domain' o 'command' en la orden.", "order": order}
    
    result = dispatch(domain, command, **args)
    return result

def run_payload(payload: str) -> dict:
    """
    Acepta:
      - Una orden: {"domain":..., "command":..., "args":{...}}
      - Varias: {"orders":[ {...}, {...} ]}
    Devuelve JSON con el resultado (ok True/False).
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        return {"ok": False, "error": f"JSON inválido: {e}", "raw": payload}

    # Multi-órdenes
    if isinstance(data, dict) and isinstance(data.get("orders"), list):
        results = []
        all_ok = True
        for order in data["orders"]:
            res = _run_one(order)
            results.append(res)
            all_ok = all_ok and bool(res.get("ok"))
        return {"ok": all_ok, "results": results}

    # Orden única
    if isinstance(data, dict):
        return _run_one(data)

    return {"ok": False, "error": "Estructura no reconocida. Esperaba un objeto o {\"orders\":[...]}"}

if __name__ == "__main__":
    # Si hay argumento, úsalo; si no, lee desde STDIN
    payload = sys.argv[1] if len(sys.argv) >= 2 else sys.stdin.read()
    out = run_payload(payload.strip())
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0 if out.get("ok") else 1)