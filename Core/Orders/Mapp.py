# winapps.py
import sys, re, json
import ctypes
import psutil
import win32gui, win32con, win32process, win32api

# ---------- DPI-aware ----------
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# ---------- Utilidades JSON ----------
def jprint(d: dict, ok_field: str = "ok"):
    """Imprime JSON y sale con código acorde a d[ok_field]."""
    print(json.dumps(d, ensure_ascii=False))
    sys.exit(0 if d.get(ok_field) else 1)

# ---------- Monitores ----------
def get_monitors():
    """
    Devuelve lista de dicts con info de cada monitor según GetMonitorInfo.
    Claves típicas: 'Monitor' (L,T,R,B) y 'Work' (L,T,R,B) si está disponible.
    """
    mons = []
    try:
        for hMon, _hdc, _rect in win32api.EnumDisplayMonitors(None, None):
            info = win32api.GetMonitorInfo(hMon)
            mons.append(info)
    except Exception:
        pass
    return mons

# ---------- Ventanas ----------
def _enum_windows():
    hwnds = []
    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            if title.strip():
                hwnds.append(hwnd)
    win32gui.EnumWindows(_cb, None)
    return hwnds

def _pid_of(hwnd):
    return win32process.GetWindowThreadProcessId(hwnd)[1]

def _proc_name(hwnd):
    try:
        return psutil.Process(_pid_of(hwnd)).name()
    except Exception:
        return ""

def _find_windows(titulo_regex: str | None = None, proc_hint: str | None = None):
    """
    Devuelve lista de (hwnd, title, procname).
    1) Intenta por título (regex, case-insensitive).
    2) Si no hay resultados, intenta por proceso:
       - Usa proc_hint si lo pasas,
       - o lo infiere de titulo_regex (ej. 'Spotify' -> 'spotify').
    """
    hwnds = _enum_windows()
    out = []

    # 1) por título
    if titulo_regex:
        pat = None
        try:
            pat = re.compile(titulo_regex, re.IGNORECASE)
        except re.error:
            pat = None
        if pat:
            for h in hwnds:
                title = win32gui.GetWindowText(h) or ""
                if pat.search(title):
                    out.append((h, title, _proc_name(h)))
    if out:
        return out

    # 2) por proceso
    hint = (proc_hint or "").strip().lower()
    if not hint and titulo_regex:
        # inferir 'spotify' de 'Spotify', 'Spot ify!!', etc.
        hint = re.sub(r"[^a-z0-9]+", "", titulo_regex.strip().lower())

    if hint:
        for h in hwnds:
            pname = (_proc_name(h) or "").lower()
            root = pname.rsplit(".", 1)[0]
            if hint == root or hint in pname:
                out.append((h, win32gui.GetWindowText(h) or "", pname))

    return out

# ---------- Mover ventana ----------
def move_app(hwnd: int, monitor_index: int, mode: str = "max", grid: tuple | None = None):
    mons = get_monitors()
    if not mons:
        return {"ok": False, "error": "No se pudieron enumerar monitores."}
    if monitor_index < 0 or monitor_index >= len(mons):
        return {"ok": False, "error": f"Monitor {monitor_index} inválido (hay {len(mons)})."}

    info = mons[monitor_index]
    # Preferir área de trabajo si está (sin barra de tareas)
    rect = info.get("Work", info.get("Monitor"))
    if not rect:
        return {"ok": False, "error": "No se pudo obtener rect del monitor."}

    L, T, R, B = rect
    W, H = R - L, B - T
    mode = (mode or "max").lower()

    if mode == "max":
        x, y, w, h = L, T, W, H
    elif mode == "left":
        x, y, w, h = L, T, W // 2, H
    elif mode == "right":
        x, y, w, h = L + W // 2, T, W // 2, H
    elif mode == "center":
        w, h = int(W * 0.7), int(H * 0.7)
        x, y = L + (W - w) // 2, T + (H - h) // 2
    elif mode == "grid" and grid:
        try:
            cols, rows, gx, gy = grid
        except Exception:
            return {"ok": False, "error": f"Parámetros grid inválidos: {grid}"}
        if cols <= 0 or rows <= 0 or not (0 <= gx < cols) or not (0 <= gy < rows):
            return {"ok": False, "error": f"Parámetros grid inválidos: {grid}"}
        cell_w, cell_h = W // cols, H // rows
        x, y, w, h = L + gx * cell_w, T + gy * cell_h, cell_w, cell_h
    else:
        return {"ok": False, "error": "Modo no reconocido. Usa: max|left|right|center|grid"}

    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP, x, y, w, h,
            win32con.SWP_SHOWWINDOW
        )
        return {
            "ok": True,
            "placed": {
                "monitor": monitor_index,
                "mode": mode,
                "rect": {"x": x, "y": y, "w": w, "h": h},
                "grid": grid,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------- CLI ----------
if __name__ == "__main__":
    if len(sys.argv) < 5:
        jprint({
            "ok": False,
            "error": "Uso: python winapps.py mueve \"<titulo_regex>\" <monitor> <modo> [COLS,ROWS,X,Y] [indice]"
        })

    command = sys.argv[1].lower()
    if command != "mueve":
        jprint({"ok": False, "error": "Comando no reconocido. Usa: mueve"})

    titulo_regex = sys.argv[2]

    # monitor
    try:
        monitor = int(sys.argv[3])
    except ValueError:
        jprint({"ok": False, "error": f"Monitor inválido: {sys.argv[3]}"})

    mode = sys.argv[4].lower()

    # Parse opcionales: grid y/o índice
    grid = None
    idx_arg = None
    if mode == "grid":
        if len(sys.argv) < 6:
            jprint({"ok": False, "error": "Modo grid requiere COLS,ROWS,X,Y"})
        coords = sys.argv[5]
        try:
            cols, rows, gx, gy = map(int, coords.split(","))
            grid = (cols, rows, gx, gy)
        except Exception:
            jprint({"ok": False, "error": "Formato grid inválido. Usa COLS,ROWS,X,Y (ej: 2,2,1,0)"})
        # índice opcional en posición 6
        if len(sys.argv) >= 7:
            idx_arg = sys.argv[6]
    else:
        # índice opcional en posición 5
        if len(sys.argv) >= 6:
            idx_arg = sys.argv[5]

    # Índice (qué ventana mover si hay varias)
    index = 0
    if idx_arg is not None:
        try:
            index = int(idx_arg)
        except ValueError:
            jprint({"ok": False, "error": f"Índice inválido: {idx_arg}"})

    # Buscar ventanas: primero por título; si no hay, por proceso inferido del texto
    wins = _find_windows(titulo_regex=titulo_regex)
    if not wins:
        wins = _find_windows(proc_hint=re.sub(r"[^a-z0-9]+", "", titulo_regex.lower()))

    if not wins:
        jprint({"ok": False, "error": f"No se encontraron ventanas que coincidan con: {titulo_regex}"})

    if index < 0 or index >= len(wins):
        jprint({"ok": False, "error": f"Índice fuera de rango: {index}. Coincidencias: {len(wins)}"})

    hwnd, title, pname = wins[index]

    # Mover
    res = move_app(hwnd, monitor-1, mode=mode, grid=grid)
    if res.get("ok"):
        placed = res.setdefault("placed", {})
        placed["title"] = title
        placed["hwnd"] = hwnd
        placed["index"] = index
        placed["proc"] = pname
        jprint(res)
    else:
        jprint(res)