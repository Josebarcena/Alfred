# memory.py
import os, json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "State"
STATE.mkdir(parents=True, exist_ok=True)

MEM_FILE = STATE / "memory.json"
HIST_FILE = STATE / "history.jsonl"

def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

class Memory:
    def __init__(self):
        self.kv = _read_json(MEM_FILE, {})

    # --- clave/valor persistente ---
    def set(self, key: str, value: str):
        self.kv[str(key)] = str(value)
        _write_json(MEM_FILE, self.kv)
        return True

    def get(self, key: str):
        return self.kv.get(str(key))

    def delete(self, key: str):
        if str(key) in self.kv:
            del self.kv[str(key)]
            _write_json(MEM_FILE, self.kv)
            return True
        return False

    def all(self):
        return dict(self.kv)

    # --- historial persistente (opcional) ---
    def append_history(self, role: str, content: str):
        with open(HIST_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.utcnow().isoformat(timespec="seconds")+"Z",
                "role": role,
                "content": content
            }, ensure_ascii=False) + "\n")

def summarize_memory_for_prompt(mem: dict, max_items: int = 20) -> str:
    if not mem:
        return ""
    items = list(mem.items())[:max_items]
    lines = [f"- {k}: {v}" for k, v in items]
    return "Preferencias y datos guardados del usuario:\n" + "\n".join(lines)