import sys, json, time, subprocess, os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException


def load_creds_from_file():
    # ruta ../State/data.txt relativa al script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    state_path = os.path.normpath(os.path.join(base_dir, "..", "State", "data.txt"))

    if not os.path.exists(state_path):
        return {"ok": False, "error": f"No existe {state_path}"}

    creds = {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()

        cid  = creds.get("SPOTIFY_CLIENT_ID")
        csec = creds.get("SPOTIFY_CLIENT_SECRET")
        ruri = creds.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

        if not cid or not csec:
            return {"ok": False, "error": "Faltan CLIENT_ID o CLIENT_SECRET en data.txt"}

        return {"ok": True, "CLIENT_ID": cid, "CLIENT_SECRET": csec, "REDIRECT_URI": ruri}
    except Exception as e:
        return {"ok": False, "error": str(e)}


_creds = load_creds_from_file()
if not _creds.get("ok"):
    print(json.dumps({"ok": False, "error": _creds.get("error")}, ensure_ascii=False))
    sys.exit(1)

# ====== DATA ======
CLIENT_ID     = _creds["CLIENT_ID"]
CLIENT_SECRET = _creds["CLIENT_SECRET"]
REDIRECT_URI  = _creds["REDIRECT_URI"]
SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing"

# ====== Helpers JSON / shell ======
def jprint(payload: dict):
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 1

def open_spotify_app():
    # Abre la app de Spotify en Windows (no bloquea)
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "spotify:"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    time.sleep(1.5)

# ====== Auth ======
sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )
)

# ====== Core ======
def list_devices():
    try:
        devices = sp.devices().get("devices", [])
        data = [
            {
                "id": d.get("id"),
                "name": d.get("name"),
                "type": d.get("type"),
                "is_active": d.get("is_active"),
                "volume_percent": d.get("volume_percent")
            }
            for d in devices
        ]
        return {"ok": True, "devices": data}
    except SpotifyException as e:
        return {"ok": False, "error": f"Spotify API error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def pick_device_id(prefer: str | None = None):
    """
    Elige un device_id. prefer puede ser:
      - "computer" / "smartphone" (por tipo)
      - cualquier nombre parcial (case-insensitive)
      - None -> activo si existe, si no el primero
    """
    devices = sp.devices().get("devices", [])
    if not devices:
        return None

    # 1) si hay activo
    active = next((d for d in devices if d.get("is_active")), None)
    # 2) prefer por tipo
    if prefer in ("computer", "smartphone"):
        d = next((d for d in devices if d.get("type", "").lower() == prefer), None)
        if d:
            return d.get("id")
    # 3) prefer por nombre parcial
    if prefer and prefer not in ("computer", "smartphone"):
        d = next((d for d in devices if prefer.lower() in (d.get("name") or "").lower()), None)
        if d:
            return d.get("id")
    # 4) activo o primero
    if active:
        return active.get("id")
    return devices[0].get("id")

def ensure_active_device(prefer: str | None = None):
    """
    Garantiza un device activo: intenta seleccionar uno y transferir reproducción.
    Devuelve {"ok":True, "device_id":..., "device_name":...} o {"ok":False,...}
    """
    try:
        devices = sp.devices().get("devices", [])
        if not devices:
            open_spotify_app()
            devices = sp.devices().get("devices", [])
            if not devices:
                return {"ok": False, "error": "No hay dispositivos de Spotify disponibles (abre la app de Spotify y reproduce algo un momento)."}

        target_id = pick_device_id(prefer)
        if not target_id:
            return {"ok": False, "error": f"No se encontró un dispositivo adecuado (prefer='{prefer}')."}

        # si no está activo, transfiere playback
        info = next((d for d in devices if d.get("id") == target_id), {})
        if not info.get("is_active"):
            sp.transfer_playback(device_id=target_id, force_play=False)
            time.sleep(0.5)

        # devuelve info final
        # refresca estado
        devices2 = sp.devices().get("devices", [])
        cur = next((d for d in devices2 if d.get("id") == target_id), info)
        return {
            "ok": True,
            "device_id": target_id,
            "device_name": cur.get("name"),
            "device_type": cur.get("type"),
            "is_active": cur.get("is_active")
        }
    except SpotifyException as e:
        return {"ok": False, "error": f"Spotify API error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def play_song(query: str, prefer_device: str | None = None):
    try:
        dev = ensure_active_device(prefer_device)
        if not dev.get("ok"):
            return dev
        device_id = dev["device_id"]

        res = sp.search(q=query, type="track", limit=1)
        tracks = res.get("tracks", {}).get("items", [])
        if not tracks:
            return {"ok": False, "error": f"No se encontró la canción: '{query}'"}

        uri = tracks[0]["uri"]
        sp.start_playback(device_id=device_id, uris=[uri])
        return {"ok": True, "message": f"Reproduciendo: {tracks[0]['name']} · {tracks[0]['artists'][0]['name']}", "track_uri": uri, "device_id": device_id}
    except SpotifyException as e:
        return {"ok": False, "error": f"Spotify API error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def pause_song(prefer_device: str | None = None):
    try:
        dev = ensure_active_device(prefer_device)
        if not dev.get("ok"):
            return dev
        sp.pause_playback(device_id=dev["device_id"])
        return {"ok": True, "message": "Pausado", "device_id": dev["device_id"]}
    except SpotifyException as e:
        return {"ok": False, "error": f"Spotify API error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def next_song(prefer_device: str | None = None):
    try:
        dev = ensure_active_device(prefer_device)
        if not dev.get("ok"):
            return dev
        sp.next_track(device_id=dev["device_id"])
        return {"ok": True, "message": "Siguiente", "device_id": dev["device_id"]}
    except SpotifyException as e:
        return {"ok": False, "error": f"Spotify API error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def change_device(prefer: str):
    # prefer puede ser "computer", "smartphone" o parte del nombre del dispositivo
    try:
        dev = ensure_active_device(prefer)
        if not dev.get("ok"):
            return dev
        # Si ya está activo, simplemente lo reporta
        return {"ok": True, "message": f"Dispositivo activo: {dev['device_name']} ({dev['device_type']})", "device_id": dev["device_id"]}
    except SpotifyException as e:
        return {"ok": False, "error": f"Spotify API error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ====== CLI ======
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(jprint({"ok": False, "error": "Uso: python spotify_cli.py [devices | device <computer|smartphone|nombre> | play <canción> [prefer] | pause [prefer] | next [prefer]]"}))

    cmd = sys.argv[1].lower()

    if cmd == "devices":
        sys.exit(jprint(list_devices()))

    elif cmd == "device":
        if len(sys.argv) < 3:
            sys.exit(jprint({"ok": False, "error": "Uso: device <computer|smartphone|nombre>"}))
        prefer = sys.argv[2]
        sys.exit(jprint(change_device(prefer)))

    elif cmd == "play":
        if len(sys.argv) < 3:
            sys.exit(jprint({"ok": False, "error": "Uso: play <canción> [prefer]"}))
        song = sys.argv[2]
        prefer = sys.argv[3].lower() if len(sys.argv) >= 4 else None
        sys.exit(jprint(play_song(song, prefer)))

    elif cmd == "pause":
        prefer = sys.argv[2].lower() if len(sys.argv) >= 3 else None
        sys.exit(jprint(pause_song(prefer)))

    elif cmd == "next":
        prefer = sys.argv[2].lower() if len(sys.argv) >= 3 else None
        sys.exit(jprint(next_song(prefer)))

    else:
        sys.exit(jprint({"ok": False, "error": "Comando no reconocido. Usa: devices | device | play | pause | next"}))
