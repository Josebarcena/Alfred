# Alfred — LLM Assistant (CLI)

Alfred is a modular **LLM-powered assistant** designed to run from the command line.  
The project is structured to keep the core logic, model/LLM integration, and input/output layers cleanly separated, making it easy to extend with new tools, providers, or interfaces.

---

## Features

- **CLI-first workflow** via `Alfred_CLI.py`
- **Modular architecture** (Core / LLM / IO separation)
- Easy to extend with:
  - new LLM providers or backends
  - new I/O channels (terminal, files, etc.)
  - new assistant behaviors and orchestration logic

---

## Repository Structure

```text
.
├── Core/                 # Core assistant logic (orchestration, routing, prompts, utilities)
├── IO/                   # Input/Output layer (CLI interaction, formatting, persistence, etc.)
├── LLM/                  # LLM integration (providers, wrappers, calls, configs)
└── Alfred_CLI.py         # Command-line entrypoint
```

## Requirements

- Python 3.10+ (recommended)
- An API key for OLLAMA (if applicable)

##  Quick Start
Run Alfred from the project root:
- python Alfred_CLI.py
