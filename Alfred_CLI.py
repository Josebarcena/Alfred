# agent_cli.py
from typing import Callable, Iterable, Optional
import unicodedata
import re
import sys
from LLM.Aliaser import load_alias_db, ensure_rule_ids, alias_adjust
from Core.builder_json import build_payload_from_text
from IO.Bridge import run_payload
# Palabras/frases que provocan la salida del bucle
GOODBYE: set[str] = {
    "exit", "quit", "salir", "adios", "adiós",
    "bye", "chao", "chau", "hasta luego"
}
PROMPT_INPUT = "> "
PROMPT_OUTPUT = "👴 > "
ALIAS_DB = load_alias_db()
ensure_rule_ids(ALIAS_DB)

LAST_ALIAS_RULE_ID: str | None = None
LAST_ALIAS_CANON: str | None = None


def _normalize(text: str) -> str:
    """Minúsculas + sin acentos (NFKD) para comparaciones robustas."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()

def _should_exit(user_input: str, goodbye_words: Iterable[str]) -> bool:
    """
    Devuelve True si el input contiene alguna palabra/frase de GOODBYE
    como palabra completa (no substrings tipo 'exito' vs 'exit').
    """
    s = _normalize(user_input)
    for word in goodbye_words:
        w = re.escape(_normalize(word))
        # Coincidencia de palabra/frase completa con límites de palabra
        # Para frases con espacios, \b sigue funcionando en separación por no-alfanum.
        if re.search(rf"\b{w}\b", s):
            return True
    return False


def make_output(input: str) -> str:
    global PROMPT_OUTPUT
    if input.lower() == "inicio":
        print(PROMPT_OUTPUT + " Hola señor. ¿En qué puedo ayudarle?")
        return None
    elif input.lower() == "salir":
        print(PROMPT_OUTPUT + " Hasta luego señor.")
        return None
    elif input.lower() == "vacio":
        print(PROMPT_OUTPUT + " desea algo mas señor?")
        return None
    elif input.startswith("❌"):
        print(f"\n{input}\n")
        return None
    else:
        return process_line(input)

def process_line(line: str) -> str:
    global PROMPT_OUTPUT, ALIAS_DB, LAST_ALIAS_RULE_ID, LAST_ALIAS_CANON

    s = line.strip()
    if not s:
        return None

    # Comandos de feedback
    if s.startswith("/bien"):
        if LAST_ALIAS_RULE_ID:
            ok, canon, w = alias_adjust(LAST_ALIAS_RULE_ID, 0.2, ALIAS_DB, mode="inc")
            if ok:
                print(f"{PROMPT_OUTPUT} listo señor! Peso ↑ para {canon}. Nuevo peso: {w:.2f}")
            else:
                print(f"{PROMPT_OUTPUT} No encontre la ultima regla señor.")
        else:
            print(f"{PROMPT_OUTPUT} ⚠️ Señor no hay alias previo para evaluar positivamente.")
        return

    elif s.startswith("/mal"):
        if LAST_ALIAS_RULE_ID:
            ok, canon, w = alias_adjust(LAST_ALIAS_RULE_ID, 0.3, ALIAS_DB, mode="dec")
            if ok:
                print(f"{PROMPT_OUTPUT} listo señor! Peso ↓ para {canon}. Nuevo peso: {w:.2f}")
            else:
                print(f"{PROMPT_OUTPUT} ⚠️ No encontre la ultima regla señor.")
        else:
            print(f"{PROMPT_OUTPUT} Señor no hay alias previo para evaluar negativamente")
        return
    
    try:
        payload, avisos, last_rule_id = build_payload_from_text(s, ALIAS_DB)
    except Exception as e:
        print(f"{PROMPT_OUTPUT} ❌❌ {e}")
        return

    if avisos:
        print(f"{PROMPT_OUTPUT} ⚠️ " + " | ".join(avisos))

    # Ejecutar directamente con dispatcher wrapper
    print(payload)
    out = run_payload(payload)
    # Resumen corto
    if isinstance(out.get("results"), list):
        ok = out["ok"]
        print(f"{PROMPT_OUTPUT} {'✅' if ok else '❌'} {len(out['results'])} orden(es) procesada(s).")
    else:
        print(f"{PROMPT_OUTPUT} {'✅ Listo' if out.get('ok') else '❌ No puedo hacer eso'}")

    # Guarda la última regla para /bien /mal
    if last_rule_id:
        LAST_ALIAS_RULE_ID = last_rule_id

def prompt_loop():
    global PROMPT_INPUT
    print("Alfred CLI iniciado. Escriba 'exit' o 'quit' para salir.")
    goodbye_words: list[str] = GOODBYE
    on_command: str = None
    make_output("inicio")
    loop = True
    try:
        while loop:
            try:
                line = input(PROMPT_INPUT)
            except EOFError:   # Ctrl+D / fin de input
                make_output("salir")
                break

            if line is None:
                make_output("vacio")

            line = line.strip()
            if not line:
                make_output("vacio")

            if _should_exit(line, goodbye_words):
                make_output("salir")
                loop = False

            elif on_command is not None:
                on_command = line
            else:
                make_output(line)
    except KeyboardInterrupt:  # Ctrl+C
        make_output("salir")
    except Exception as e:
        make_output(f"❌ Error inesperado: {e}")
        # Opcional: relanzar o registrar
        # raise


#MAIN FUNCTION
if __name__ == "__main__":
    prompt_loop()