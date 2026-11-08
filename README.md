# Lexis Suite — Ecossistema de Aquisicao de Idiomas & Vocabulario Ativo

Plataforma web modular para triagem acelerada de vocabulario em ingles (MWLD 01k-10k), absorcao de estruturas nativas (Phrasal Verbs, Collocations, Idioms), treino auditivo (Listening Studio: Ditado Interativo com Video e Escuta as Cegas), curadoria cognitiva com TypeSafe Jev e injecao direta no Anki Desktop via AnkiConnect.

---

## Arquitetura de Modulos

1. **Vocabulario & Chunks (`vocab_review_app.html` + `vocab_review_server.py`):**
   - Base indexada: 66.332 acepcoes MWLD + 13.531 estruturas/chunks + 14.212 sentencas Mairo Vergara.
   - Modo Foco 1-por-1 e Modo Grade com deteccao preventiva de falsos cognatos e curadoria automatica de frases $i+1$ via TypeSafe Jev (`typesafe-sdk`).
2. **Listening Studio:**
   - Ditado Ativo com Video: suporte a YouTube (`/api/youtube-transcript` com fusao sintatica de micro-legendas) e arquivos locais (`.mp4`/`.webm` + `.srt`/`.vtt`), Word Slots em tempo real, dicas ortograficas (Levenshtein) e controle de velocidade.
   - Escuta as Cegas (Blind Listening): reproducao auditiva com revelacao em dois estagios (transcricao EN -> traducao PT).
3. **Anki Hub & Sincronizacao Bidirecional:**
   - Fila qualificada de Gaps com salvaguarda $i+1$ e injecao via AnkiConnect (`http://127.0.0.1:8765`).
   - Sincronizacao bidirecional com Google Cloud Run (`/api/sync-cloud` e `/api/import-knowledge-map`).

---

## Execucao Local (Ambiente Isolado `.venv`)

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt pytest
.\.venv\Scripts\python vocab_review_server.py
```

```bash
# Linux / macOS
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt pytest
./.venv/bin/python vocab_review_server.py
```

- **Interface Local:** `http://127.0.0.1:5050`
- **Variaveis de Ambiente (`.env`):**
  - `TYPESAFE_API_KEY`: Chave da API TypeSafe para julgamentos do modelo Jev.
  - `LEXIS_CLOUD_URL`: URL da instancia Google Cloud Run para sync bidirecional.

---

## Testes Automatizados

```powershell
.\.venv\Scripts\pytest tests/
```

---

## Deploy em Container (Google Cloud Run)

O repositorio contem `Dockerfile` e `.dockerignore` prontos para build limpo (excluindo `.env`, `.venv`, `.git`, caches e artefatos de documentacao/testes).
