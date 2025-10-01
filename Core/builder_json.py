import json, re
from typing import List, Dict, Tuple, Optional
from LLM.Aliaser import try_alias, learn_alias, ensure_rule_ids
from LLM.Ollama import _ollama_generate_json_from_chunk, _ollama_propose_alias_from_chunk
import shlex

ORDERS_SPEC = "Core/Orders.json"

def _is_valid_order(d: dict) -> bool: 
    return ( isinstance(d, dict) 
            and isinstance(d.get("domain"), str) 
            and d.get("domain") 
            and isinstance(d.get("command"), str) 
            and d.get("command") 
            and (d.get("args") 
                 is None or isinstance(d.get("args"), dict)) )

def _split_param_name(x: str) -> Tuple[str, bool]:
    """
    Devuelve (nombre, es_obligatorio).
    - '<cancion>'  -> ('cancion', True)
    - '[device]'   -> ('device',  False)
    - literales    -> (literal, None)  # para el trigger del comando
    """
    x = x.strip()
    if x.startswith("<") and x.endswith(">"):
        return x[1:-1].strip(), True
    if x.startswith("[") and x.endswith("]"):
        return x[1:-1].strip(), False
    return x, None  # literal


def _find_command_spec(orders_spec: Dict, domain: str, command_literal: str):
    dom = orders_spec.get(domain)
    if not dom:
        return None
    cmds = dom.get("commands") or {}
    for cmd_name, cmd_spec in cmds.items():
        args_sig = cmd_spec.get("args") or []
        # El primer elemento de la firma debe ser el literal del comando
        if not args_sig:
            continue
        lit, kind = _split_param_name(args_sig[0])
        if kind is None and lit.lower() == command_literal.lower():
            return cmd_name, cmd_spec
    return None


def _tokenize(text: str) -> List[str]:
    """
    Tokeniza respetando comillas:
      spotify play "little dark age"  -> ['spotify','play','little dark age']
    """
    try:
        return shlex.split(text, posix=True)
    except Exception:
        # fallback muy simple
        return text.strip().split()


def _map_args(signature: List[str], tokens: List[str]) -> Optional[Dict]:
    """
    signature: p.ej. ["play","<cancion>","[prefer_device]"]
    tokens:    p.ej. ["spotify","play","little","dark","age","computer"]  (OJO: sin 'domain' ni literal)
               En esta función se espera SOLO lo que va DESPUÉS del literal.
    Regla:
      - Asigna obligatorios primero (uno por token).
      - Luego opcionales (si quedan tokens).
      - Si sobran tokens, concatena al ÚLTIMO parámetro asignado con espacios.
    """
    # separamos partes de la firma
    if not signature:
        return {}

    # quitar el literal de comando (primer elemento debe ser literal)
    lit_name, lit_kind = _split_param_name(signature[0])
    if lit_kind is not None:
        return None  # la firma no empieza con literal -> inválida para este parser

    # parámetros nombrados
    param_defs = [ _split_param_name(x) for x in signature[1:] ]
    required_names = [name for (name, is_req) in param_defs if is_req is True]
    optional_names = [name for (name, is_req) in param_defs if is_req is False]

    # mínimo tokens para obligatorios
    if len(tokens) < len(required_names):
        return None

    args: Dict[str, str] = {}

    # 1) obligatorios de izquierda a derecha
    idx = 0
    for name in required_names:
        if idx >= len(tokens):
            return None
        args[name] = tokens[idx]
        idx += 1

    # 2) opcionales de izquierda a derecha
    for name in optional_names:
        if idx >= len(tokens):
            break
        args[name] = tokens[idx]
        idx += 1

    # 3) ¿sobraron tokens? -> se añaden al ÚLTIMO parámetro asignado
    if idx < len(tokens):
        # último param asignado = el último opcional si existe; si no, el último obligatorio
        last_key = optional_names[len([k for k in optional_names if k in args]) - 1] if optional_names and any(k in args for k in optional_names) else (required_names[-1] if required_names else None)
        if not last_key:
            return None  # no hay dónde ponerlos; muy raro
        extra = " ".join(tokens[idx:])
        args[last_key] = (args.get(last_key, "") + " " + extra).strip()

    return args


# === Parser principal ===

def try_parse_json_orders(text: str, orders_spec: Dict) -> Optional[List[Dict]]:
    """
    Intenta parsear `text` como:
      A) JSON:
         - Orden única: {"domain":..., "command":..., "args":{...}}
         - Múltiples:   {"orders":[ {...}, {...} ]}
      B) NL según Orders.json:
         - "<domain> <literal_comando> [parametros...]"
    Devuelve lista de órdenes normalizadas si es válido; si no, None.
    """
    s = (text).strip()
    if not s:
        return None

    # --- A) JSON directo ---
    try:
        data = json.loads(s)
        def _is_valid_order(d: dict) -> bool:
            return (
                isinstance(d, dict) and
                isinstance(d.get("domain"), str) and d.get("domain") and
                isinstance(d.get("command"), str) and d.get("command") and
                (d.get("args") is None or isinstance(d.get("args"), dict))
            )

        if isinstance(data, dict) and isinstance(data.get("orders"), list):
            orders = []
            for it in data["orders"]:
                if not _is_valid_order(it):
                    return None
                orders.append({
                    "domain": it["domain"],
                    "command": it["command"],
                    "args": it.get("args") or {}
                })
            return orders

        if isinstance(data, dict) and _is_valid_order(data):
            return [{
                "domain": data["domain"],
                "command": data["command"],
                "args": data.get("args") or {}
            }]
        # si no cuadra JSON, seguimos con NL
    except Exception:
        pass

    # --- B) NL por Orders.json ---
    tokens_all = _tokenize(s)
    if len(tokens_all) < 2:
        return None

    domain = tokens_all[0].lower()
    cmd_literal = tokens_all[1].lower()

    found = _find_command_spec(orders_spec, domain, cmd_literal)
    if not found:
        return None

    cmd_name, cmd_spec = found
    signature = cmd_spec.get("args") or []
    rest = tokens_all[2:]  # tras domain + literal

    mapped = _map_args(signature, rest)
    if mapped is None:
        return None

    

    return [{
        "domain": domain,
        "command": cmd_name,   # OJO: aquí usamos el nombre lógico del comando
        "args": mapped
    }]
    

def split_chunks(text: str) -> List[str]:
    # separadores: ';' o '&&'
    return [c.strip() for c in re.split(r"\s*(?:;|&&)\s*", text.strip()) if c.strip()]

def chunk_to_order(chunk: str, alias_db: dict) -> Tuple[Dict, str | None]:
    """
    Devuelve (order, rule_id|None) si hay alias.
    Si NO hay alias, este helper ya no fabrica 'None' — la parte JSON se gestiona en build_payload_from_text.
    """
    m = try_alias(chunk, alias_db)
    if m:
        return (
            {
                "domain":  m["domain"],
                "command": m["command"],
                "args":    m.get("args", {}) or {}
            },
            m.get("rule_id")
        )
    # Indicaremos al caller que no hubo alias devolviendo (None, None)
    return (None, None)

def build_payload_from_text(text: str, alias_db: dict) -> Tuple[str, List[str], str | None]:
    global ORDERS_SPEC
    orders_spec = json.load(open(ORDERS_SPEC, "r", encoding="utf-8"))

    s = text.strip()
    if not s:
        raise ValueError("Entrada vacía")

    # 1) JSON directo
    direct = try_parse_json_orders(s, orders_spec)
    if direct:
        obj = direct[0] if len(direct) == 1 else {"orders": direct}
        return json.dumps(obj, ensure_ascii=False), [], None

    chunks = split_chunks(s)
    orders: List[Dict] = []
    avisos: List[str] = []
    last_rule_id: str | None = None

    for c in chunks:
        # a) alias
        order, rule_id = chunk_to_order(c, alias_db)
        if order is not None:
            orders.append(order)
            if rule_id:
                last_rule_id = rule_id
            continue

        # b) parser NL interno
        parsed = try_parse_json_orders(c, orders_spec)
        if parsed:
            orders.extend(parsed)
            continue

        # c) Fallback: Ollama JSON
        data = _ollama_generate_json_from_chunk(c, orders_spec, model="llama3.1")
        if data:
            try:
                new_orders: list[dict] = []
                if isinstance(data, dict) and isinstance(data.get("orders"), list):
                    for it in data["orders"]:
                        if isinstance(it, dict) and it.get("domain") and it.get("command"):
                            new_orders.append({
                                "domain": it["domain"],
                                "command": it["command"],
                                "args": it.get("args") or {}
                            })
                elif isinstance(data, dict) and data.get("domain") and data.get("command"):
                    new_orders.append({
                        "domain": data["domain"],
                        "command": data["command"],
                        "args": data.get("args") or {}
                    })
                else:
                    avisos.append(f"Ollama devolvió JSON inválido para: '{c}'")
                    continue

                # ✅ Añadimos las órdenes resueltas por Ollama
                orders.extend(new_orders)

                # ✅ Nueva: pedir a Ollama un alias para aprender de este chunk
                alias_suggestion = _ollama_propose_alias_from_chunk(c, orders_spec, model="llama3.1")
                if alias_suggestion:
                    pat, amap = alias_suggestion
                    # ¿A qué domain.command lo asociamos? al primero de new_orders (suficiente para memoria)
                    dom = new_orders[0]["domain"]; cmd = new_orders[0]["command"]
                    learn_alias(pat, dom, cmd, amap, alias_db)  # crea y persiste
                    ensure_rule_ids(alias_db)
                    # buscamos el id recién creado para devolverlo como last_rule_id
                    for r in alias_db.get(f"{dom}.{cmd}", []):
                        if r["pattern"] == pat and r.get("args_map") == amap:
                            last_rule_id = r.get("id") or last_rule_id
                            break
                continue
            except Exception:
                avisos.append(f"Ollama devolvió algo no-JSON para: '{c}'")
                continue

        # d) nada funcionó
        avisos.append(f"sin alias, NL ni Ollama → '{c}' (ignorado)")

    if not orders:
        raise ValueError("Ningún fragmento fue reconocible (ni alias, ni NL, ni Ollama).")

    obj = orders[0] if len(orders) == 1 else {"orders": orders}
    return json.dumps(obj, ensure_ascii=False), avisos, last_rule_id