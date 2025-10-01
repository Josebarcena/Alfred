import json, re, os, uuid
ALIAS_PATH =  "LLM/Alias.json"


def _norm(text: str) -> str:
    text = text.strip().lower()
    return re.sub(r"\s+", " ", text)

def ensure_rule_ids(db: dict) -> bool:
    """Añade un id a cada regla que no lo tenga. Devuelve True si hubo cambios."""
    changed = False
    for canon, rules in db.items():
        for r in rules:
            if "id" not in r:
                r["id"] = uuid.uuid4().hex
                changed = True
    if changed:
        save_alias_db(db)
    return changed

def load_alias_db():
    if not os.path.exists(ALIAS_PATH): return {}
    with open(ALIAS_PATH, "r", encoding="utf-8") as f: return json.load(f)

def save_alias_db(db): 
    with open(ALIAS_PATH, "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, indent=2)

def alias_update(rule_id: str, new_pattern: str | None, new_args_map: dict | None, db: dict):
    for canon, rules in db.items():
        for r in rules:
            if r.get("id") == rule_id:
                if new_pattern is not None:
                    r["pattern"] = new_pattern
                if new_args_map is not None:
                    r["args_map"] = new_args_map
                save_alias_db(db)
                return True, canon
    return False, ""


def try_alias(nl: str, alias_db: dict):
    nl = _norm(nl)
    best = None
    for canon, rules in alias_db.items():  # canon = "domain.command"
        for r in rules:
            pat = _norm(r["pattern"]).replace("*", "(.*)")
            m = re.fullmatch(pat, nl)
            if not m:
                continue
            args = {}
            for k, v in r.get("args_map", {}).items():
                args[k] = v
                for i, g in enumerate(m.groups(), 1):
                    args[k] = args[k].replace(f"${i}", g.strip())
            score = float(r.get("weight", 1.0))
            if not best or score > best[0]:
                dom, cmd = canon.split(".")
                best = (
                    score,
                    {
                        "domain": dom,
                        "command": cmd,
                        "args": args,
                        "rule_id": r.get("id"),
                        "canon": canon,
                        "weight": score,
                    },
                )
    return best[1] if best else None

def learn_alias(nl: str, domain: str, command: str, args: dict, alias_db: dict):
    key = f"{domain}.{command}"
    alias_db.setdefault(key, [])
    for r in alias_db[key]:
        if r["pattern"] == nl:
            r["weight"] = min(2.0, r.get("weight", 1.0) + 0.1)
            save_alias_db(alias_db)
            return
    # nueva regla con id
    alias_db[key].append({
        "id": uuid.uuid4().hex,
        "pattern": nl,
        "args_map": args,
        "weight": 0.5
    })
    save_alias_db(alias_db)

def alias_adjust(rule_id: str, delta: float, db: dict, mode: str = "inc"):
    changed = False
    for canon, rules in db.items():
        for r in rules:
            if r.get("id") == rule_id:
                w = float(r.get("weight", 1.0))
                w = min(5.0, w + delta) if mode == "inc" else max(0.0, w - delta)
                r["weight"] = w
                save_alias_db(db)
                return True, canon, w
    return False, "", 0.0

def alias_delete(rule_id: str, db: dict):
    for canon, rules in list(db.items()):
        new_rules = [r for r in rules if r.get("id") != rule_id]
        if len(new_rules) != len(rules):
            db[canon] = new_rules
            save_alias_db(db)
            return True, canon
    return False, ""