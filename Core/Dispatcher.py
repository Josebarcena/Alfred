# dispatcher.py
import json, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORDERS_JSON = ROOT / "Orders.json"


def _parse_relaxed_json(stdout: str, stderr: str):
    """
    Intenta:
      1) json.loads(stdout) directo
      2) parsear la ÚLTIMA línea que parezca JSON
      3) buscar el último bloque que empiece por '{' y terminar en el último '}'
    Si todo falla, devuelve mensaje de error con stdout/stderr.
    """
    # 1) directo
    try:
        return json.loads(stdout) if stdout else {}
    except Exception:
        pass

    # 2) última línea que parezca JSON
    for line in reversed([ln.strip() for ln in stdout.splitlines() if ln.strip()]):
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                continue

    # 3) último bloque {...}
    start = stdout.rfind("{")
    end = stdout.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = stdout[start:end+1].strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # falló todo
    return {"ok": False, "error": "stdout no es JSON", "stdout": stdout, "stderr": stderr}

def load_orders():
    try:
        with open(ORDERS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"No se pudo leer Orders.json: {e}", "path": str(ORDERS_JSON)}


def build_cmd(script: str, spec: dict, args_map: dict):
    """
    Sustituye placeholders en spec['args'] con args_map y construye el comando.
    Soporta:
      - <obligatorio>  -> debe existir en args_map
      - [opcional]     -> si existe en args_map, se añade
      - literales      -> se añaden tal cual (p.ej., "busca")
    """
    arg_tpl = spec.get("args", [])


    script_path = Path(script).resolve()
    if not script_path.exists():
        return None, f"Script no encontrado: {script_path}"

    cmd = [sys.executable, str(script_path)]
    for token in arg_tpl:
        if token.startswith("<") and token.endswith(">"):
            key = token[1:-1]
            if key not in args_map or args_map[key] in (None, ""):
                return None, f"Falta argumento obligatorio: {key}"
            cmd.append(str(args_map[key]))
        elif token.startswith("[") and token.endswith("]"):
            key = token[1:-1]
            val = args_map.get(key)
            if val not in (None, ""):
                cmd.append(str(val))
        else:
            # literal
            cmd.append(token)
    return cmd, None

def run_command(cmd: list, timeout=60):
    def _decode(b: bytes) -> str:
        if b is None:
            return ""
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return b.decode("utf-8-sig", errors="strict")
            except Exception:
                return b.decode("mbcs", errors="replace")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=False,
            timeout=timeout
        )
        stdout = _decode(proc.stdout).strip()
        stderr = _decode(proc.stderr).strip()

        data = _parse_relaxed_json(stdout, stderr)

        data.setdefault("_meta", {})
        data["_meta"]["cmd"] = cmd
        data["_meta"]["returncode"] = proc.returncode

        if proc.returncode != 0 and not data.get("ok", False):
            if "error" not in data:
                data["error"] = f"Proceso terminó con código {proc.returncode}"
                data["stderr"] = stderr
            data["ok"] = False
        return data
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout ejecutando el comando", "_meta": {"cmd": cmd}}
    except Exception as e:
        return {"ok": False, "error": str(e), "_meta": {"cmd": cmd}}

def dispatch(domain: str, command: str, **kwargs):
    orders = load_orders()
    if isinstance(orders, dict) and orders.get("ok") is False:
        return orders  # error al cargar Orders.json

    if domain not in orders:
        return {"ok": False, "error": f"Dominio desconocido: {domain}"}

    cmds = orders[domain].get("commands", {})
    if command not in cmds:
        return {"ok": False, "error": f"Comando desconocido para '{domain}': {command}"}
    spec = cmds[command]
    script = orders[domain].get("script")
    if not script:
        return None, "Spec inválida (falta 'script' o 'args')."

    cmd, err = build_cmd(script, spec, kwargs)

    if err:
        return {"ok": False, "error": err}

    result = run_command(cmd)
    # añade info de resolución para depurar
    result.setdefault("_meta", {})
    result["_meta"]["orders_path"] = str(ORDERS_JSON)
    return result