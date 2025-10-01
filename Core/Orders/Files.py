import os, subprocess, sys, json, re

# ---------- utilidades IO ----------
def print(obj: dict):
    """Imprime SOLO JSON por stdout y sale con código coherente."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.exit(0 if obj.get("ok") else 1)

def _dbg(*args):
    """Logs a stderr (seguro para el Bridge)."""
    print(*args, file=sys.stderr)

# ---------- normalización ----------
def _norm_unidad(u):
    """Acepta C / C: / C:\ y devuelve C:\ (o None si no es válida)."""
    if u is None:
        return None
    try:
        s = str(u).strip().replace("/", "\\").upper()
    except Exception:
        return None

    # "C" o "C:" (con o sin una barra final)
    m = re.fullmatch(r"([A-Z])(?::\\?)?$", s)
    if m:
        return m.group(1) + ":\\"

    # "C:\"
    if re.fullmatch(r"[A-Z]:\\", s):
        return s

    return None

def _parse_unidad_y_archivo(a, b):
    """Detecta cuál de (a,b) es unidad y cuál archivo. Devuelve (unidad_normalizada, archivo) o (None, None)."""
    u1, u2 = _norm_unidad(a), _norm_unidad(b)
    if u1:
        return u1, (b or "")
    if u2:
        return u2, (a or "")
    return None, None

def find_file(root_dir, filename, skip_dirs=None):
    """
    Busca recursivamente 'filename' bajo 'root_dir', evitando carpetas de AV.
    Devuelve: {"ok": True, "path": "..."} | {"ok": False, "error": "..."}
    """
    root = _norm_unidad(root_dir)
    if root is None or not os.path.isdir(root):
        return {"ok": False, "error": f"Raíz inválida o no accesible: {root_dir}"}

    if not isinstance(filename, str) or not filename.strip():
        return {"ok": False, "error": "Falta 'archivo'"}
    name = filename.strip().lower()

    if skip_dirs is None:
        skip_dirs = [
            r"norton", r"symantec", r"mcafee", r"avast", r"avg", r"kaspersky",
            r"eset", r"nod32", r"bitdefender", r"trend", r"trendmicro", r"sophos",
            r"panda", r"f-secure", r"fsecure", r"malwarebytes", r"webroot",
            r"zonealarm", r"comodo", r"drweb", r"secureanywhere"
        ]
    skip_re = re.compile("|".join(skip_dirs), re.IGNORECASE)

    for dirpath, dirs, files in os.walk(root, topdown=True, onerror=lambda e: None):
        dirs[:] = [d for d in dirs if not skip_re.search(os.path.join(dirpath, d))]
        for f in files:
            if f.lower() == name:
                return {"ok": True, "path": os.path.join(dirpath, f)}
    return {"ok": False, "error": f"'{name}' no encontrado bajo {root}"}

def run_file(path: str):
    """Lanza un ejecutable en Windows sin bloquear el script."""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    try:
        if not path:
            return {"ok": False, "error": "Ruta vacía."}
        if not os.path.exists(path):
            return {"ok": False, "error": f"No existe el archivo: {path}"}
        subprocess.Popen(
            [path],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "launched": path}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print({"ok": False, "error": "Uso: python Files.py [busca <raiz> <archivo> | abre <archivo> [raiz]]"})

    command = sys.argv[1].lower()
    if command == "busca":
        if len(sys.argv) < 4:
            print({"ok": False, "error": "Uso: python Files.py busca <raiz> <archivo>"})
        # acepta ambos órdenes
        unidad, archivo = _parse_unidad_y_archivo(sys.argv[2], sys.argv[3])
        if unidad is None:
            print({"ok": False, "error": "Indica raíz válida (C / C: / C:\\) y archivo"})
        print(find_file(unidad, archivo))

    elif command == "abre":
        # soporta:
        #   abre <archivo>                → raíz por defecto C:\
        #   abre <archivo> <raiz>         → detecta raíz
        #   abre <raiz> <archivo>         → detecta raíz
        if len(sys.argv) == 3:
            unidad, archivo = "C:\\", sys.argv[2]
        elif len(sys.argv) >= 4:
            unidad, archivo = _parse_unidad_y_archivo(sys.argv[2], sys.argv[3])
            if unidad is None:
                print({"ok": False, "error": "Indica raíz válida (C / C: / C:\\) y archivo"})
        else:
            print({"ok": False, "error": "Uso: python Files.py abre <archivo> [raiz]"})

        found = find_file(unidad, archivo)
        if not found.get("ok"):
            print(found)
        print(run_file(found["path"]))

    else:
        print({"ok": False, "error": "Comando no reconocido. Usa: busca, abre."})