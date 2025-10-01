from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
import sys, time, subprocess, socket, os, json, re
from urllib.parse import urlparse


DEBUG_PORT = 9222
USER_DATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\ChromiumDebugProfile")
BROWSER_BIN  = r"C:\Users\Josem\AppData\Local\ms-playwright\chromium-1181\chrome-win\chrome.exe"

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

def _is_port_open(port:int)->bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0

def ensure_browser_with_cdp():
    """Arranca (si hace falta) el navegador con CDP y devuelve JSON ok/error."""
    if _is_port_open(DEBUG_PORT):
        return {"ok": True, "message": "CDP ya estaba disponible"}
    if not os.path.exists(BROWSER_BIN):
        return {
            "ok": False,
            "error": f"No existe BROWSER_BIN: {BROWSER_BIN}. Edita la ruta a chromium/chrome."
        }
    args = [
        BROWSER_BIN,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    subprocess.Popen(
        args,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):  # ~10s
        if _is_port_open(DEBUG_PORT):
            return {"ok": True, "message": "CDP listo"}
        time.sleep(0.1)
    return {"ok": False, "error": "El navegador no abrió el puerto de depuración a tiempo."}

def connect_playwright():
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return p, browser, ctx

def disconnect_only(p):
    try:
        p.stop()
    except Exception:
        pass

def last_navigated_page(ctx):
    # de más nueva a más vieja
    for p in reversed([pg for pg in ctx.pages if not pg.is_closed()]):
        u = (p.url or "").lower()
        t = (p.title() or "").lower()
        if u and u != "about:blank" and not u.startswith("chrome://") and "nueva pestaña" not in t:
            return p
    # si todas son blank/newtab, devuelve la última igualmente
    return ctx.pages[-1]

def search(ctx, keywords: str):
    page = ctx.new_page()
    ctx.current_page = page
    page.goto("https://www.google.com", wait_until="domcontentloaded")
    # Consentimiento (si aparece)
    try:
        page.locator("button:has-text('Acepto'), button:has-text('Accept all'), button:has-text('Acepto todo')").first.click(timeout=1500)
    except Exception:
        pass
    box = page.locator('textarea[name="q"]')
    box.fill(keywords)
    page.keyboard.press("Enter")
    try:
        page.wait_for_selector("a h3", timeout=10000)
    except PlaywrightTimeoutError:
        return {"ok": False, "error": "No aparecieron resultados."}
    count = page.locator("a h3:visible").count()
    return {"ok": True, "message": f"Buscado: {keywords}", "results_visible": count}

def open_url(ctx, url: str):
    if not url.startswith("http"):  # añade https:// solo si falta
        url = "https://" + url
    page = ctx.new_page()
    ctx.current_page = page
    try:
        page.goto(url, wait_until="domcontentloaded")
    except PlaywrightError as e:
        return {"ok": False, "error": f"No se pudo abrir la URL: {e}"}
    return {"ok": True, "message": f"Abrí {url}", "url": page.url, "title": page.title()}

def select(ctx, option: str):
    if not getattr(ctx, "pages", None):
        return {"ok": False, "error": "No hay pestañas abiertas."}

    page = last_navigated_page(ctx)  # última pestaña creada (asumiendo que ctx.pages[0] es la activa)
    page.bring_to_front()

    # 1) Asegura que hay resultados con h3 (no solo visibles)
    try:
        page.wait_for_selector("a:has(h3)", timeout=10000)
    except PlaywrightTimeoutError:
        return {"ok": False, "error": "No hay resultados (a:has(h3))."}

    # 2) Valida opción
    try:
        idx = int(option) - 1  # 1-based -> 0-based
    except ValueError:
        return {"ok": False, "error": "Opción inválida (no numérica)."}
    if idx < 0:
        return {"ok": False, "error": "El índice debe ser >= 1."}

    # 3) Localiza TODOS los enlaces con h3 (sin :visible para permitir scroll)
    links_all = page.locator("a:has(h3)")
    count_all = links_all.count()
    if count_all == 0:
        return {"ok": False, "error": "No se encontraron enlaces con título (a>h3)."}

    # 4) Si el índice no está disponible aún, intenta cargar más con scroll
    if idx >= count_all:
        seen = count_all
        # Intenta varias veces (ajusta repeticiones/tiempos según tu UI)
        for _ in range(6):
            # Desplázate al final y da tiempo a que cargue nuevo contenido
            page.keyboard.press("End")
            page.wait_for_timeout(400)
            new_count = links_all.count()
            if new_count > seen:
                seen = new_count
                if idx < seen:
                    break

        count_all = links_all.count()
        if idx >= count_all:
            return {"ok": False, "error": f"Índice fuera de rango: {idx+1} (hay {count_all})."}

    # 5) Obtén el enlace objetivo y llévalo a la vista
    link = links_all.nth(idx)
    try:
        link.scroll_into_view_if_needed()
        # Asegura que se vuelva visible antes del click
        link.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        # A veces es visible ya o hay overlays; seguimos con el click y fallback
        pass

    # 6) Click con manejo de navegación, popup o href
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            link.click()
        return {"ok": True, "message": f"Abrí el resultado {idx+1}", "url": page.url, "title": page.title()}
    except PlaywrightTimeoutError:
        # Puede que se haya abierto una pestaña nueva (target=_blank)
        try:
            with page.expect_popup(timeout=5000) as popup_info:
                link.click()
            new_page = popup_info.value
            new_page.wait_for_load_state("domcontentloaded", timeout=15000)
            # Opcional: mantén la nueva pestaña como activa en tu ctx
            try:
                ctx.pages.insert(0, new_page)
            except Exception:
                pass
            new_page.bring_to_front()
            return {"ok": True, "message": f"Abrí el resultado {idx+1} en pestaña nueva", "url": new_page.url, "title": new_page.title()}
        except Exception:
            # Fallback final por href directo
            try:
                href = link.get_attribute("href")
            except Exception:
                href = None
            if href:
                page.goto(href, wait_until="domcontentloaded", timeout=15000)
                return {"ok": True, "message": f"Abrí el resultado {idx+1} (href)", "url": page.url, "title": page.title()}
            return {"ok": False, "error": f"No se pudo abrir el resultado {idx+1} (click, popup ni href)."}
        

def cierra(ctx):
    try:
        for page in ctx.pages:
            page.close()
        return {"ok": True, "message": "Cerradas todas las pestañas de este contexto."}
    except Exception as e:
        return {"ok": False, "error": f"No se pudieron cerrar las pestañas: {e}"}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Uso: python script.py [busca <keywords> | abre <URL> | cierra | selecciona <n>]"}, ensure_ascii=False))
        sys.exit(1)

    # 1) Asegura CDP
    ready = ensure_browser_with_cdp()
    if not ready.get("ok"):
        print(json.dumps(ready, ensure_ascii=False))
        sys.exit(1)

    # 2) Conecta Playwright
    p, browser, ctx = connect_playwright()

    cmd = sys.argv[1].lower()
    try:
        if cmd == "busca":
            keywords = " ".join(sys.argv[2:])
            result = search(ctx, keywords)
            print(json.dumps(result, ensure_ascii=False))

        elif cmd == "abre":
            url = " ".join(sys.argv[2:])
            result = open_url(ctx, url)
            print(json.dumps(result, ensure_ascii=False))

        elif cmd == "selecciona":
            option = " ".join(sys.argv[2:])
            result = select(ctx, option)
            print(json.dumps(result, ensure_ascii=False))

        elif cmd == "cierra":
            result = cierra(ctx)
            # No cierro el Chrome externo; solo desconecto Playwright
            print(json.dumps(result, ensure_ascii=False))

        else:
            print(json.dumps({"ok": False, "error": "Comando no reconocido. Usa: busca, abre, cierra o selecciona."}, ensure_ascii=False))

    finally:
        # Importante: mantener el navegador vivo
        disconnect_only(p)