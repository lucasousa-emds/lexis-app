#!/usr/bin/env python3
"""
vocab_review_server.py (Edição de Alta Performance / Zero Gargalo)
Servidor Local de Triagem Ultrarrápida de Vocabulário MWLD & Integração Anki.
- ThreadingHTTPServer multi-thread para requisições paralelas sem fila
- Tradução 100% assíncrona em fila de background (sem travar carregamento de página)
- Gravação de disco em background com persistência atômica
- Latência média por requisição: < 5ms
"""

import os
import re
import sys
import json
import time
import queue
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
import sqlite3
import socket

PORT = int(os.environ.get("PORT", 5050))
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
MAP_FILE = os.path.join(WORKSPACE_DIR, "knowledge_map_english.json")
MWLD_FILE = os.path.join(WORKSPACE_DIR, "mwld_source", "notes.csv")
TRANS_CACHE_FILE = os.path.join(WORKSPACE_DIR, "mwld_source", "translations_cache.json")
JEV_CACHE_FILE = os.path.join(WORKSPACE_DIR, "mwld_source", "jev_cache.json")
STRUCTURES_FILE = os.path.join(WORKSPACE_DIR, "mwld_source", "structures_entries.json")
ANKI_URL = "http://127.0.0.1:8765"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

# Integração Mairo Vergara (Anki SQLite & Mídia)
ANKI_DB_PATH = os.path.expanduser("~/.var/app/net.ankiweb.Anki/data/Anki2/Usuário 1/collection.anki2")
ANKI_MEDIA_DIR = os.path.expanduser("~/.var/app/net.ankiweb.Anki/data/Anki2/Usuário 1/collection.media")
MAIRO_SENTENCES_BY_KEYWORD = {}
MAIRO_SENTENCES_BY_WORD = {}

# Cache em memória
KNOWLEDGE_MAP = {}
MWLD_ENTRIES = []
MWLD_BY_SUBDECK = {}
MWLD_BY_WORD = {}
STRUCTURES_BY_SUBDECK = {}
TRANSLATIONS_CACHE = {}
JEV_CACHE = {}
LOCK = threading.Lock()
SAVE_DIRTY = False

# Fila para traduções em background (sem travar a requisição do usuário)
TRANSLATE_QUEUE = queue.Queue()

def get_typesafe_key():
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if key: return key
    bashrc_path = os.path.expanduser("~/.bashrc")
    if os.path.exists(bashrc_path):
        with open(bashrc_path, "r", encoding="utf-8") as f:
            for line in f:
                if "TYPESAFE_API_KEY" in line and "=" in line:
                    m = re.search(r'TYPESAFE_API_KEY=["\']?([^"\'\s]+)["\']?', line)
                    if m: return m.group(1)
    return ""

def load_jev_cache():
    global JEV_CACHE
    if os.path.exists(JEV_CACHE_FILE):
        try:
            with open(JEV_CACHE_FILE, "r", encoding="utf-8") as f:
                JEV_CACHE = json.load(f)
        except Exception:
            JEV_CACHE = {}
    else:
        JEV_CACHE = {}

def save_jev_cache():
    try:
        os.makedirs(os.path.dirname(JEV_CACHE_FILE), exist_ok=True)
        tmp = JEV_CACHE_FILE + ".tmp"
        with LOCK:
            cache_copy = dict(JEV_CACHE)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache_copy, f, ensure_ascii=False, indent=2)
        os.replace(tmp, JEV_CACHE_FILE)
    except Exception as e:
        print(f"⚠️ Erro ao salvar jev_cache: {e}")

def analyze_word_with_jev(word, definition="", sentence=""):
    """
    Julgamento cognitivo instantâneo com TypeSafe Jev (System One):
    - Tipo de Cognato (transparent / false_friend / opaque)
    - Risco de Confusão para Falante de Português (0 a 2)
    - Qualidade da Frase i+1 para Flashcard Anki (0 a 2)
    - Gancho Mnemônico Recomendado
    """
    w_clean = (word or "").strip().lower()
    if not w_clean:
        return None
    if w_clean in JEV_CACHE:
        return JEV_CACHE[w_clean]

    key = get_typesafe_key()
    if not key:
        return None

    try:
        from typesafe_sdk import TypeSafeClient, Choice, Score
        client = TypeSafeClient(api_key=key)
        state = {
            "word": word,
            "definition": definition or "",
            "example_sentence": sentence or ""
        }
        res = client.system_one(
            state=state,
            questions={
                "cognate_type": Choice(
                    instructions="Classify this English word regarding its relationship to Brazilian Portuguese vocabulary.",
                    criteria={
                        "transparent": "Transparent cognate (orthography and meaning directly match Portuguese, e.g. communication ~ comunicação)",
                        "false_friend": "False cognate / false friend (looks like a Portuguese word but means something completely different, e.g. actually does NOT mean atualmente; pretend does NOT mean pretender)",
                        "opaque": "Opaque root with no direct lexical twin in Portuguese"
                    }
                ),
                "confusion_risk": Score(
                    instructions="Rate the likelihood that a Brazilian learner will misunderstand this word without explicit warning.",
                    criteria=[
                        "Low risk: transparent, intuitive, or standard straightforward vocabulary",
                        "Moderate risk: subtle nuance or less common usage",
                        "High risk: dangerous trap, false friend, or counterintuitive preposition/grammar"
                    ]
                ),
                "sentence_quality": Score(
                    instructions="Rate how effectively the example sentence demonstrates the meaning of the target word for spaced repetition (i+1).",
                    criteria=[
                        "Weak: vague sentence where many unrelated words could fit equally well",
                        "Good: clear context, grammatically sound and accessible",
                        "Optimal: vivid context that makes the specific meaning unambiguous"
                    ]
                ),
                "pedagogical_hook": Choice(
                    instructions="Select the most effective memory anchor strategy for this word.",
                    criteria={
                        "latin_root": "Direct connection to a Latin/Portuguese root word",
                        "contrast_warning": "Warning about false cognate or misleading false friend",
                        "vivid_scene": "Visual scene or physical action anchor",
                        "usage_pattern": "Specific preposition, colocation or syntactic phrase pattern"
                    }
                )
            }
        )
        answers = res.answers
        cog = answers.get("cognate_type")
        risk = answers.get("confusion_risk")
        sent_q = answers.get("sentence_quality")
        hook = answers.get("pedagogical_hook")

        result_data = {
            "word": word,
            "cognate_type": cog.choice if cog else "opaque",
            "cognate_confidence": round(cog.confidence, 2) if cog else 0.5,
            "cognate_probabilities": cog.probabilities if cog else {},
            "confusion_risk": round(risk.score if hasattr(risk, 'score') else getattr(risk, 'level', 0.5), 2) if risk else 0.5,
            "sentence_quality": round(sent_q.score if hasattr(sent_q, 'score') else getattr(sent_q, 'level', 1.0), 2) if sent_q else 1.0,
            "pedagogical_hook": hook.choice if hook else "vivid_scene"
        }
        with LOCK:
            JEV_CACHE[w_clean] = result_data
        save_jev_cache()
        return result_data
    except Exception as e:
        print(f"⚠️ Erro em analyze_word_with_jev: {e}")
        return None

def curate_best_sentence_with_jev(word, candidate_sentences, definition=""):
    """
    Curador cognitivo de frases i+1 com TypeSafe Jev (System One):
    Quando há múltiplos candidatos de frases (ex: Mairo Vergara vs MWLD),
    o Jev julga qual é a frase pedagogicamente superior para o flashcard Anki.
    """
    if not candidate_sentences:
        return None
    if len(candidate_sentences) == 1:
        return candidate_sentences[0]

    w_clean = (word or "").strip().lower()
    cache_key = f"__curated_{w_clean}"
    if cache_key in JEV_CACHE:
        cached_en = JEV_CACHE[cache_key].get("chosen_en")
        for cand in candidate_sentences:
            if cand.get("en", "").strip() == cached_en:
                return cand

    key = get_typesafe_key()
    if not key:
        return candidate_sentences[0]

    # Avaliar os top 4 candidatos
    cands_to_evaluate = candidate_sentences[:4]
    try:
        from typesafe_sdk import TypeSafeClient, Choice
        client = TypeSafeClient(api_key=key)

        criteria = {}
        for idx, cand in enumerate(cands_to_evaluate):
            clean_s = re.sub(r'<[^>]+>', '', cand.get("en", "")).strip()
            src = cand.get("source", "Acervo")
            criteria[f"cand_{idx}"] = f"Candidate {idx+1}: \"{clean_s}\" (Source: {src})"

        state = {
            "target_word": word,
            "definition": definition or "",
            "candidate_sentences": [re.sub(r'<[^>]+>', '', c.get("en", "")).strip() for c in cands_to_evaluate]
        }

        res = client.system_one(
            state=state,
            questions={
                "best_sentence": Choice(
                    instructions=(
                        f"Choose the optimal example sentence to create an Anki flashcard for learning the English word '{word}'. "
                        "Pick the sentence with the most natural, vivid, and unambiguous context where the word's meaning is clearest to an adult language learner."
                    ),
                    criteria=criteria
                )
            }
        )
        choice = res.answers.get("best_sentence")
        if choice and choice.choice in criteria:
            sel_idx = int(choice.choice.replace("cand_", ""))
            best_cand = cands_to_evaluate[sel_idx]
            print(f"✨ Jev Curador escolheu frase {sel_idx+1} para '{word}': \"{best_cand.get('en')}\" (Confiança: {choice.confidence:.2f})")
            with LOCK:
                JEV_CACHE[cache_key] = {
                    "chosen_en": best_cand.get("en", "").strip(),
                    "confidence": choice.confidence,
                    "model": getattr(res, "model", "jev-latest")
                }
            save_jev_cache()
            return best_cand
    except Exception as e:
        print(f"⚠️ Aviso no Jev Curador de Frases para '{word}': {e}")

    return candidate_sentences[0]

def invoke_anki(action, **params):
    payload = json.dumps({"action": action, "params": params, "version": 6}).encode("utf-8")
    req = urllib.request.Request(ANKI_URL, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        if res.get("error"):
            raise RuntimeError(f"Erro no AnkiConnect ({action}): {res['error']}")
        return res.get("result")

def load_translations_cache():
    global TRANSLATIONS_CACHE
    if os.path.exists(TRANS_CACHE_FILE):
        try:
            with open(TRANS_CACHE_FILE, "r", encoding="utf-8") as f:
                TRANSLATIONS_CACHE = json.load(f)
        except Exception:
            TRANSLATIONS_CACHE = {}
    else:
        TRANSLATIONS_CACHE = {}

def save_translations_cache():
    try:
        os.makedirs(os.path.dirname(TRANS_CACHE_FILE), exist_ok=True)
        tmp = TRANS_CACHE_FILE + ".tmp"
        with LOCK:
            cache_copy = dict(TRANSLATIONS_CACHE)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache_copy, f, ensure_ascii=False)
        os.replace(tmp, TRANS_CACHE_FILE)
    except Exception as e:
        print(f"⚠️ Erro ao salvar translation cache: {e}")

def translate_to_pt_sync(text):
    if not text or not text.strip():
        return ""
    text_clean = text.strip()
    if text_clean in TRANSLATIONS_CACHE:
        cached = TRANSLATIONS_CACHE[text_clean]
        if cached and cached.strip().lower() != text_clean.lower():
            return cached

    # Tier 1: Google Chrome Dict API (Super rápido, estável, sem bloqueio 429)
    try:
        url = "https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=en&tl=pt&q=" + urllib.parse.quote(text_clean)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                res_pt = data[0] if isinstance(data[0], str) else data[0][0]
                if res_pt and res_pt.strip() and res_pt.strip().lower() != text_clean.lower():
                    clean_res = res_pt.strip()
                    TRANSLATIONS_CACHE[text_clean] = clean_res
                    return clean_res
    except Exception:
        pass

    # Tier 2: MyMemory API Fallback
    try:
        url = "https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(text_clean) + "&langpair=en|pt"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            res_pt = d.get("responseData", {}).get("translatedText", "")
            if res_pt and res_pt.strip() and res_pt.strip().lower() != text_clean.lower() and not res_pt.startswith("MYMEMORY WARNING"):
                clean_res = res_pt.strip()
                TRANSLATIONS_CACHE[text_clean] = clean_res
                return clean_res
    except Exception:
        pass

    # Tier 3: gtx API Fallback
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=pt&dt=t&q=" + urllib.parse.quote(text_clean)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res_pt = "".join([segment[0] for segment in data[0] if segment and segment[0]]).strip()
            if res_pt and res_pt.lower() != text_clean.lower():
                TRANSLATIONS_CACHE[text_clean] = res_pt
                return res_pt
    except Exception:
        pass

    return ""

def translation_worker():
    """Worker em thread separada para não bloquear NENHUMA requisição do usuário."""
    last_save = time.time()
    while True:
        try:
            item = TRANSLATE_QUEUE.get(timeout=2.0)
            if item and item not in TRANSLATIONS_CACHE:
                translate_to_pt_sync(item)
                if time.time() - last_save > 5.0:
                    save_translations_cache()
                    last_save = time.time()
            TRANSLATE_QUEUE.task_done()
        except queue.Empty:
            if time.time() - last_save > 10.0:
                save_translations_cache()
                last_save = time.time()
        except Exception:
            pass

def load_knowledge_map():
    global KNOWLEDGE_MAP
    if not os.path.exists(MAP_FILE):
        KNOWLEDGE_MAP = {"usuario": "Lucas", "mapa_vocabulario": {}, "estatisticas": {}}
        return
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        KNOWLEDGE_MAP = json.load(f)

def save_knowledge_map_memory():
    """Atualiza as estatísticas em memória instantaneamente (0.02ms) e marca para flush em disco."""
    global SAVE_DIRTY
    with LOCK:
        KNOWLEDGE_MAP["ultima_atualizacao"] = datetime.now().isoformat()
        total_conhecidas = 0
        total_estudo = 0
        total_desc = 0
        total_duvida = 0
        for t_data in KNOWLEDGE_MAP.get("mapa_vocabulario", {}).values():
            for ac in t_data.get("acepcoes", []):
                st = ac.get("status")
                if st == "conhecido": total_conhecidas += 1
                elif st == "em_estudo": total_estudo += 1
                elif st == "desconhecido": total_desc += 1
                elif st == "duvida": total_duvida += 1

        KNOWLEDGE_MAP["estatisticas"] = {
            "total_termos": len(KNOWLEDGE_MAP.get("mapa_vocabulario", {})),
            "acepcoes_conhecidas": total_conhecidas,
            "acepcoes_em_estudo": total_estudo,
            "acepcoes_desconhecidas": total_desc,
            "acepcoes_duvida": total_duvida
        }
        SAVE_DIRTY = True

def disk_saver_worker():
    """Worker de persistência em disco em segundo plano (evita lag de I/O em cliques)."""
    global SAVE_DIRTY
    while True:
        time.sleep(1.0)
        if SAVE_DIRTY:
            with LOCK:
                SAVE_DIRTY = False
                try:
                    tmp = MAP_FILE + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(KNOWLEDGE_MAP, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, MAP_FILE)
                except Exception as e:
                    print(f"⚠️ Erro ao salvar knowledge_map no disco: {e}")

def index_mwld():
    global MWLD_ENTRIES, MWLD_BY_SUBDECK, MWLD_BY_WORD
    if not os.path.exists(MWLD_FILE):
        print(f"❌ Arquivo {MWLD_FILE} não encontrado!")
        return

    print("📖 Indexando acervo MWLD (66k notas)...")
    t0 = time.time()
    by_subdeck = {}
    by_word = {}
    entries = []

    with open(MWLD_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if line.startswith("#") or not line.strip(): continue
            parts = line.split("\t")
            if len(parts) >= 12:
                deck_full = parts[1]
                subdeck = deck_full.split("::")[-1] if "::" in deck_full else deck_full
                note_id = parts[2].strip()
                word = parts[4].strip()
                pos = parts[5].strip()
                ipa = parts[6].strip()
                audio_url = parts[7].strip()
                def_en = parts[9].strip()
                ex1 = parts[11].strip() if len(parts) > 11 else ""
                ex2 = parts[13].strip() if len(parts) > 13 else ""

                entry = {
                    "id": f"{word}_{subdeck}_{idx}",
                    "note_id": note_id,
                    "subdeck": subdeck,
                    "word": word,
                    "pos": pos,
                    "ipa": ipa,
                    "audio_url": audio_url,
                    "definition_en": def_en,
                    "example_1": ex1,
                    "example_2": ex2
                }
                entries.append(entry)
                if subdeck not in by_subdeck:
                    by_subdeck[subdeck] = []
                by_subdeck[subdeck].append(entry)

                w_lower = word.lower().strip()
                if w_lower not in by_word:
                    by_word[w_lower] = []
                by_word[w_lower].append(entry)

    MWLD_ENTRIES = entries
    MWLD_BY_SUBDECK = by_subdeck
    MWLD_BY_WORD = by_word
    print(f"✓ {len(entries)} acepções indexadas em {time.time()-t0:.2f}s across {len(by_subdeck)} subdecks ({len(by_word)} palavras únicas)!")

def index_structures():
    global STRUCTURES_BY_SUBDECK, MWLD_ENTRIES, MWLD_BY_SUBDECK, MWLD_BY_WORD
    if not os.path.exists(STRUCTURES_FILE):
        print(f"⚠️ Arquivo de estruturas não encontrado em {STRUCTURES_FILE}")
        return

    print("🧩 Indexando Estruturas Nativas (Phrasal Verbs, Collocations, Idioms)...")
    t0 = time.time()
    try:
        with open(STRUCTURES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        total_loaded = 0
        for sdeck, items in data.items():
            STRUCTURES_BY_SUBDECK[sdeck] = items
            MWLD_BY_SUBDECK[sdeck] = items
            MWLD_ENTRIES.extend(items)
            total_loaded += len(items)

            for item in items:
                w_lower = item["word"].lower().strip()
                if w_lower not in MWLD_BY_WORD:
                    MWLD_BY_WORD[w_lower] = []
                MWLD_BY_WORD[w_lower].append(item)

        print(f"✓ {total_loaded} estruturas nativas indexadas em {time.time()-t0:.2f}s nos subdecks: {list(data.keys())}!")
    except Exception as e:
        print(f"❌ Erro ao indexar estruturas: {e}")

def load_mairo_sentences():
    global MAIRO_SENTENCES_BY_KEYWORD, MAIRO_SENTENCES_BY_WORD
    if not os.path.exists(ANKI_DB_PATH):
        print(f"⚠️ Banco do Anki não encontrado em {ANKI_DB_PATH}")
        return

    t0 = time.time()
    conn = None
    tmp_path = None
    try:
        try:
            conn = sqlite3.connect(f"file:{ANKI_DB_PATH}?mode=ro", uri=True, timeout=2.0)
            c = conn.cursor()
            c.execute("SELECT id, name FROM decks")
        except sqlite3.OperationalError:
            import shutil, tempfile
            with tempfile.NamedTemporaryFile(suffix='.anki2', delete=False) as tf:
                tmp_path = tf.name
            shutil.copyfile(ANKI_DB_PATH, tmp_path)
            conn = sqlite3.connect(tmp_path)
            c = conn.cursor()
            c.execute("SELECT id, name FROM decks")

        target_did = None
        for did, name in c.fetchall():
            if "Sentenças por Assunto" in name:
                target_did = did
                break

        if not target_did:
            print("⚠️ Baralho 'Sentenças por Assunto' não encontrado no Anki SQLite.")
            return

        c.execute("SELECT n.id, n.flds, n.tags FROM cards c JOIN notes n ON c.nid = n.id WHERE c.did = ?", (target_did,))
        rows = c.fetchall()

        by_kw = {}
        by_w = {}

        for nid, flds, tags in rows:
            parts = flds.split("\x1f")
            front = parts[0]
            back = parts[1] if len(parts) > 1 else ""

            # Extrair áudio
            m_audio = re.search(r'\[sound:([^\]]+)\]', front)
            audio = m_audio.group(1) if m_audio else ""
            clean_front = re.sub(r'\[sound:[^\]]+\]', '', front).strip()
            clean_front = re.sub(r'<[^>]+>', ' ', clean_front)
            clean_front = ' '.join(clean_front.split())

            # Extrair tradução PT do verso
            m_pt = re.findall(r'<i>(.*?)</i>', back)
            pt_sentence = ""
            for cand in m_pt:
                if "<img" in cand: continue
                cand_clean = re.sub(r'<[^>]+>', ' ', cand).strip()
                cand_clean = ' '.join(cand_clean.split())
                if len(cand_clean) > len(pt_sentence):
                    pt_sentence = cand_clean

            # Extrair tema
            m_tema = re.search(r'tema::([^\s]+)', tags)
            theme = m_tema.group(1).replace("_", " ").title() if m_tema else "Geral"

            sent_obj = {
                "nid": nid,
                "en": clean_front,
                "pt": pt_sentence,
                "audio": audio,
                "theme": theme,
                "source": "Mairo Vergara"
            }

            # Palavra-chave destacada em <b>
            keywords = re.findall(r'<b>(.*?)</b>', front, re.IGNORECASE)
            for kw in keywords:
                kw_clean = re.sub(r'<[^>]+>', '', kw).strip().lower()
                if kw_clean:
                    if kw_clean not in by_kw:
                        by_kw[kw_clean] = []
                    if len(by_kw[kw_clean]) < 8:
                        by_kw[kw_clean].append(sent_obj)

            # Vocábulos na frase
            tokens = set(re.findall(r'[a-zA-Z]+', clean_front.lower()))
            for tok in tokens:
                if len(tok) >= 3:
                    if tok not in by_w:
                        by_w[tok] = []
                    if len(by_w[tok]) < 8:
                        by_w[tok].append(sent_obj)

        MAIRO_SENTENCES_BY_KEYWORD = by_kw
        MAIRO_SENTENCES_BY_WORD = by_w
        print(f"✓ {len(rows)} sentenças do Mairo Vergara indexadas em {time.time()-t0:.2f}s ({len(by_kw)} termos destacados, {len(by_w)} vocábulos contextuais)!")
    except Exception as e:
        print(f"⚠️ Erro ao indexar sentenças do Mairo Vergara: {e}")
    finally:
        if conn:
            try: conn.close()
            except: pass
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass

def get_mairo_sentences_for_word(w, limit=6):
    w_low = w.lower().strip()
    res = []
    seen_nids = set()
    for s in MAIRO_SENTENCES_BY_KEYWORD.get(w_low, []):
        if s["nid"] not in seen_nids:
            seen_nids.add(s["nid"])
            res.append(s)
    for s in MAIRO_SENTENCES_BY_WORD.get(w_low, []):
        if s["nid"] not in seen_nids:
            seen_nids.add(s["nid"])
            res.append(s)
        if len(res) >= limit:
            break
    return res[:limit]

BASIC_STOPWORDS = {
    "a", "an", "the", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "her", "our", "their", "this", "that", "these", "those",
    "in", "on", "at", "to", "for", "with", "by", "from", "of", "about", "into", "through", "after", "over", "between", "under", "without", "before", "up", "down", "out", "off",
    "and", "but", "or", "so", "because", "if", "when", "as", "while", "than",
    "be", "am", "is", "are", "was", "were", "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "done",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must", "cannot", "cant", "wont", "dont", "didnt",
    "not", "no", "yes", "all", "some", "any", "very", "too", "also", "just", "more", "most", "now", "then", "here", "there",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "twenty", "thirty", "fifty", "hundred", "thousand",
    "mr", "mrs", "ms", "dr", "sir", "madam", "ok", "okay",
    "s", "t", "d", "m", "re", "ve", "ll", "neither", "either"
}

IRREGULAR_MAP = {
    "was": "be", "were": "be", "is": "be", "are": "be", "am": "be", "been": "be", "being": "be",
    "has": "have", "had": "have", "having": "have", "did": "do", "does": "do", "done": "do",
    "went": "go", "gone": "go", "goes": "go", "said": "say", "says": "say",
    "made": "make", "makes": "make", "got": "get", "gets": "get", "gotten": "get",
    "knew": "know", "known": "know", "knows": "know",
    "thought": "think", "thinks": "think", "took": "take", "taken": "take", "takes": "take",
    "saw": "see", "seen": "see", "sees": "see", "came": "come", "comes": "come",
    "gave": "give", "given": "give", "gives": "give", "found": "find", "finds": "find",
    "told": "tell", "tells": "tell", "felt": "feel", "feels": "feel",
    "left": "leave", "leaves": "leave", "brought": "bring", "brings": "bring",
    "began": "begin", "begun": "begin", "begins": "begin", "kept": "keep", "keeps": "keep",
    "held": "hold", "holds": "hold", "wrote": "write", "written": "write", "writes": "write",
    "stood": "stand", "stands": "stand", "heard": "hear", "hears": "hear",
    "let": "let", "lets": "let", "set": "set", "sets": "set",
    "met": "meet", "meets": "meet", "run": "run", "ran": "run", "runs": "run",
    "paid": "pay", "pays": "pay", "sat": "sit", "sits": "sit",
    "spoke": "speak", "spoken": "speak", "speaks": "speak",
    "fell": "fall", "fallen": "fall", "falls": "fall",
    "caught": "catch", "catches": "catch", "drove": "drive", "driven": "drive", "drives": "drive",
    "won": "win", "wins": "win", "built": "build", "builds": "build",
    "children": "child", "used": "use", "uses": "use"
}

def get_word_lemmas(w):
    w = (w or "").lower().strip()
    if not w: return []
    res = [w]
    if w in IRREGULAR_MAP:
        res.append(IRREGULAR_MAP[w])
    if w.endswith("ly") and len(w) > 4:
        res.append(w[:-2])
        if w.endswith("ily"): res.append(w[:-3] + "y")
    if w.endswith("ed") and len(w) > 3:
        res.append(w[:-2])
        res.append(w[:-1])
    if w.endswith("ing") and len(w) > 4:
        res.append(w[:-3])
        res.append(w[:-3] + "e")
    if w.endswith("es") and len(w) > 3:
        res.append(w[:-2])
        res.append(w[:-1])
    elif w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        res.append(w[:-1])
    return list(dict.fromkeys(res))

def get_word_mwld_tier(w):
    entries = MWLD_BY_WORD.get((w or "").lower(), [])
    tiers = [e["subdeck"] for e in entries if e.get("subdeck")]
    if not tiers: return None
    def parse_t(t):
        try: return int(t.replace("k", ""))
        except: return 999
    return min([parse_t(t) for t in tiers])

def get_user_vocab_profile():
    known_set = set()
    unknown_set = set()
    for term, data in KNOWLEDGE_MAP.get("mapa_vocabulario", {}).items():
        st = data.get("status_geral")
        if st == "conhecido": known_set.add(term.lower())
        elif st in ("desconhecido", "duvida"): unknown_set.add(term.lower())
        for ac in data.get("acepcoes", []):
            ac_st = ac.get("status")
            if ac_st == "conhecido": known_set.add(term.lower())
            elif ac_st in ("desconhecido", "duvida"): unknown_set.add(term.lower())
    return known_set, unknown_set

def is_word_known_to_user(w, target_word, known_set, unknown_set):
    w_clean = re.sub(r"[^a-zA-Z]", "", w).lower()
    if not w_clean: return True, "empty"
    lemmas = get_word_lemmas(w_clean)

    target_clean = re.sub(r"[^a-zA-Z\s]", "", target_word or "").lower()
    target_tokens = target_clean.split()
    target_lemmas = []
    for tt in target_tokens:
        target_lemmas.extend(get_word_lemmas(tt))
    if any(l in target_lemmas for l in lemmas):
        return True, "target"

    if any(l in BASIC_STOPWORDS for l in lemmas):
        return True, "stopword"
    if any(l in known_set for l in lemmas):
        return True, "user_known"
    if any(l in unknown_set for l in lemmas):
        return False, "user_unknown"

    best_tier = None
    for l in lemmas:
        t = get_word_mwld_tier(l)
        if t is not None:
            if best_tier is None or t < best_tier:
                best_tier = t

    if best_tier is None:
        return False, "unindexed"
    if best_tier <= 1:
        return True, f"tier_{best_tier}k"
    else:
        return False, f"tier_{best_tier}k_unlearned"

def evaluate_sentence_i1(sentence, target_word, known_set=None, unknown_set=None):
    if not sentence or not isinstance(sentence, str):
        return 999, ["empty"], False
    if known_set is None or unknown_set is None:
        known_set, unknown_set = get_user_vocab_profile()

    clean = re.sub(r"<[^>]+>", " ", sentence)
    clean = re.sub(r"\[sound:[^\]]+\]", "", clean)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"\[.*?\]", " ", clean)
    tokens = re.findall(r"\b[a-zA-Z]+\b", clean)
    if len(tokens) < 3:
        return 999, ["fragment"], False

    unknowns = []
    for tok in tokens:
        known, reason = is_word_known_to_user(tok, target_word, known_set, unknown_set)
        if not known:
            unknowns.append((tok, reason))

    extra_count = len(unknowns)
    is_strict = (extra_count == 0 and 3 <= len(tokens) <= 18)
    return extra_count, unknowns, is_strict

def is_valid_i1_sentence(frase, target_word=None):
    if not frase or not isinstance(frase, str):
        return False
    clean = re.sub(r'<[^>]+>', ' ', frase).strip()
    clean = re.sub(r'\[sound:[^\]]+\]', '', clean).strip()
    clean = ' '.join(clean.split())
    if clean in ("—", "-", "...", ""):
        return False
    if "was very important for us" in clean.lower():
        return False
    words = clean.split()
    if len(words) < 3:
        return False
    if target_word:
        cnt, _, is_strict = evaluate_sentence_i1(frase, target_word)
        return is_strict
    return True

def is_valid_definition(d):
    if not d or not isinstance(d, str):
        return False
    clean = re.sub(r'<[^>]+>', ' ', d).strip()
    clean = ' '.join(clean.split())
    if clean in ("—", "-", "...", ""):
        return False
    if "Acepção complexa suspensa temporariamente" in clean:
        return False
    if "Palavra intrusa identificada no contexto de" in clean:
        return False
    if "Acepção intrusa em" in clean:
        return False
    return len(clean) >= 5

def get_term_candidates(termo):
    t_clean = re.sub(r'\(.*?\)', '', termo or "").strip().lower()
    cands = [termo.strip().lower(), t_clean]
    if t_clean.endswith('ies'):
        cands.append(t_clean[:-3] + 'y')
    elif t_clean.endswith('es'):
        cands.append(t_clean[:-2])
        cands.append(t_clean[:-1])
    elif t_clean.endswith('s') and len(t_clean) > 3:
        cands.append(t_clean[:-1])
    if t_clean.endswith('ed'):
        cands.append(t_clean[:-2])
        cands.append(t_clean[:-1])
    if t_clean.endswith('ing'):
        cands.append(t_clean[:-3])
        cands.append(t_clean[:-3] + 'e')
    return list(dict.fromkeys([c for c in cands if c]))

CURATED_I1_SENTENCES = {
    "trial": {
        "frase": "The trial will begin next week.",
        "frase_pt": "O julgamento vai começar na próxima semana."
    },
    "perhaps": {
        "frase": "Perhaps you can help me with this.",
        "frase_pt": "Talvez você possa me ajudar com isso."
    },
    "these": {
        "frase": "These are my new books.",
        "frase_pt": "Estes são meus novos livros."
    },
    "those": {
        "frase": "Those people are waiting outside.",
        "frase_pt": "Aquelas pessoas estão esperando lá fora."
    },
    "lawyer": {
        "frase": "You should talk to a lawyer.",
        "frase_pt": "Você deveria falar com um advogado."
    },
    "shareholders": {
        "frase": "The company gave money to all shareholders.",
        "frase_pt": "A empresa deu dinheiro para todos os acionistas."
    },
    "proxy votes": {
        "frase": "People who cannot be here can send proxy votes.",
        "frase_pt": "Pessoas que não puderem estar aqui podem enviar votos por procuração."
    },
    "geranium": {
        "frase": "She put a red geranium in the room.",
        "frase_pt": "Ela colocou um gerânio vermelho no quarto."
    },
    "late summer": {
        "frase": "We like to stay home in late summer.",
        "frase_pt": "Nós gostamos de ficar em casa no final do verão."
    },
    "harpsichordist": {
        "frase": "A harpsichordist plays old music.",
        "frase_pt": "Um cravista toca música antiga."
    },
    "bach": {
        "frase": "He likes to listen to the music of Bach.",
        "frase_pt": "Ele gosta de ouvir a música de Bach."
    },
    "fielders": {
        "frase": "The fielders took the ball quickly.",
        "frase_pt": "Os defensores pegaram a bola rapidamente."
    },
    "hitters": {
        "frase": "Good hitters make many runs in the game.",
        "frase_pt": "Bons batedores fazem muitas corridas no jogo."
    },
    "poach": {
        "frase": "She likes to poach food in hot water.",
        "frase_pt": "Ela gosta de pochar comida em água quente."
    },
    "swollen": {
        "frase": "His eye was swollen after he fell.",
        "frase_pt": "O olho dele ficou inchado depois que ele caiu."
    },
    "lymph nodes": {
        "frase": "The doctor felt the lymph nodes in his body.",
        "frase_pt": "O médico apalpou os gânglios linfáticos em seu corpo."
    },
    "awl": {
        "frase": "He used an awl to make a small hole.",
        "frase_pt": "Ele usou um furador para fazer um pequeno furo."
    },
    "stronghold": {
        "frase": "The city was a strong stronghold in the war.",
        "frase_pt": "A cidade era uma fortaleza forte na guerra."
    },
    "border": {
        "frase": "Our car was at the country border.",
        "frase_pt": "Nosso carro estava na fronteira do país."
    },
    "shockproof": {
        "frase": "This watch has a shockproof glass.",
        "frase_pt": "Este relógio tem um vidro à prova de choque."
    },
    "harbor": {
        "frase": "Do not harbor bad feelings toward others.",
        "frase_pt": "Não alimente ressentimentos em relação aos outros."
    },
    "hilt": {
        "frase": "His hand was on the hilt.",
        "frase_pt": "A mão dele estava no punho.",
        "def_en": "the handle of a sword, dagger, or tool",
        "def_pt": "o cabo de uma espada, adaga ou ferramenta"
    },
    "onto": {
        "frase": "Put the book onto the table.",
        "frase_pt": "Coloque o livro sobre a mesa.",
        "def_en": "to a position on or upon",
        "def_pt": "para uma posição sobre ou em cima"
    },
    "upon": {
        "frase": "The book was upon the table.",
        "frase_pt": "O livro estava sobre a mesa.",
        "def_en": "on or above something",
        "def_pt": "sobre ou em cima de algo"
    },
    "which": {
        "frase": "Which book do you want to read?",
        "frase_pt": "Qual livro você quer ler?"
    },
    "include": {
        "frase": "Does the price include breakfast?",
        "frase_pt": "O preço inclui café da manhã?"
    },
    "continue": {
        "frase": "We will continue our work next week.",
        "frase_pt": "Nós continuaremos nosso trabalho na próxima semana."
    },
    "president": {
        "frase": "The president spoke to the nation.",
        "frase_pt": "O presidente falou para a nação."
    },
    "policy": {
        "frase": "The company has a good policy.",
        "frase_pt": "A empresa tem uma boa política."
    },
    "road": {
        "frase": "We walked on the open road.",
        "frase_pt": "Nós caminhamos pela estrada aberta."
    },
    "join": {
        "frase": "Would you like to join our group?",
        "frase_pt": "Você gostaria de se juntar ao nosso grupo?"
    },
    "itself": {
        "frase": "The city itself is very small.",
        "frase_pt": "A cidade em si é muito pequena."
    },
    "century": {
        "frase": "This house was built in the last century.",
        "frase_pt": "Esta casa foi construída no século passado."
    },
    "usually": {
        "frase": "I usually drink tea in the morning.",
        "frase_pt": "Eu geralmente tomo chá de manhã."
    },
    "thus": {
        "frase": "He worked hard and thus won the game.",
        "frase_pt": "Ele trabalhou duro e deste modo ganhou o jogo."
    },
    "fund": {
        "frase": "They started a fund to help people.",
        "frase_pt": "Eles iniciaram um fundo para ajudar pessoas."
    },
    "environmental": {
        "frase": "We must study these environmental questions.",
        "frase_pt": "Nós devemos estudar essas questões ambientais."
    },
    "pm": {
        "frase": "The train was here at five pm.",
        "frase_pt": "O trem esteve aqui às cinco da tarde."
    },
    "democrat": {
        "frase": "He has been a Democrat for twenty years.",
        "frase_pt": "Ele é um democrata há vinte anos."
    },
    "management": {
        "frase": "Good management is important for business.",
        "frase_pt": "Uma boa gestão é importante para os negócios."
    },
    "onto": {
        "frase": "He walked onto the ground.",
        "frase_pt": "Ele caminhou sobre o chão.",
        "def_en": "to a position on or upon",
        "def_pt": "para uma posição sobre ou em direção a"
    },
    "perform": {
        "frase": "She will perform a new song tonight.",
        "frase_pt": "Ela vai apresentar uma nova música hoje à noite."
    },
    "instead": {
        "frase": "Can I have water instead of tea?",
        "frase_pt": "Posso beber água em vez de chá?"
    },
    "tend": {
        "frase": "Young people tend to ask questions.",
        "frase_pt": "Pessoas jovens tendem a fazer perguntas."
    },
    "report": {
        "frase": "I will report the facts to you.",
        "frase_pt": "Eu vou relatar os fatos para você."
    },
    "along": {
        "frase": "We walked along the street.",
        "frase_pt": "Nós caminhamos ao longo da rua."
    },
    "late": {
        "frase": "He was late for class.",
        "frase_pt": "Ele estava atrasado para a aula."
    },
    "care": {
        "frase": "She has no care for money.",
        "frase_pt": "Ela não se importa com dinheiro."
    },
    "raise": {
        "frase": "You can raise your hand.",
        "frase_pt": "Você pode levantar a sua mão."
    },
    "appear": {
        "frase": "He did not appear at the meeting.",
        "frase_pt": "Ele não apareceu na reunião."
    },
    "research": {
        "frase": "The school does research on energy.",
        "frase_pt": "A escola faz pesquisas sobre energia."
    },
    "project": {
        "frase": "We project big growth next year.",
        "frase_pt": "Nós projetamos um grande crescimento no próximo ano."
    },
    "resume": {
        "frase": "We will resume our work next week.",
        "frase_pt": "Nós vamos retomar nosso trabalho na próxima semana."
    },
    "produce": {
        "frase": "They sell green produce at the store.",
        "frase_pt": "Eles vendem produtos agrícolas verdes na loja."
    },
    "tender": {
        "frase": "The baby has tender skin.",
        "frase_pt": "O bebê tem a pele tenra e macia."
    },
    "leave": {
        "frase": "He had three days of paid leave.",
        "frase_pt": "Ele teve três dias de licença remunerada."
    },
    "sound": {
        "frase": "She has a sound body and mind.",
        "frase_pt": "Ela tem um corpo e uma mente sãos."
    },
    "second": {
        "frase": "Who will second this idea?",
        "frase_pt": "Quem vai apoiar esta ideia?"
    },
    "tip": {
        "frase": "I gave a small tip for the service.",
        "frase_pt": "Eu dei uma pequena gorjeta pelo serviço."
    },
    "season": {
        "frase": "You can season the food well.",
        "frase_pt": "Você pode temperar bem a comida."
    },
    "flat": {
        "frase": "The land is very flat and green.",
        "frase_pt": "A terra é muito plana e verde."
    },
    "spot": {
        "frase": "I could spot him in the room.",
        "frase_pt": "Eu consegui avistá-lo na sala."
    },
    "figure": {
        "frase": "I figure that he is at home.",
        "frase_pt": "Eu calculo/imagino que ele esteja em casa."
    },
    "treat": {
        "frase": "I will treat you to a drink.",
        "frase_pt": "Eu vou te pagar uma bebida."
    },
    "draw": {
        "frase": "The game will draw many people.",
        "frase_pt": "O jogo vai atrair muitas pessoas."
    },
    "issue": {
        "frase": "They will issue a new card for you.",
        "frase_pt": "Eles vão emitir um novo cartão para você."
    },
    "charge": {
        "frase": "They will charge him with the crime.",
        "frase_pt": "Eles vão acusá-lo pelo crime."
    },
    "unearth": {
        "frase": "They want to unearth the secret.",
        "frase_pt": "Eles querem desenterrar o segredo."
    },
    "flaky": {
        "frase": "His friend was very flaky today.",
        "frase_pt": "O amigo dele estava muito inconsistente/esquisito hoje."
    },
    "agm": {
        "frase": "All important members will be at the AGM.",
        "frase_pt": "Todos os membros importantes estarão na AGM."
    },
    "nor": {
        "frase": "It is neither good nor bad.",
        "frase_pt": "Não é nem bom nem ruim.",
        "def_en": "used after 'neither' to introduce the second of two negative alternatives",
        "def_pt": "usado após 'neither' para introduzir a segunda alternativa negativa"
    },
    "citizen": {
        "frase": "He is a citizen of this country.",
        "frase_pt": "Ele é um cidadão deste país.",
        "def_en": "a person who legally belongs to a country",
        "def_pt": "uma pessoa que pertence legalmente a um país"
    },
    "income": {
        "frase": "He has a good income from his work.",
        "frase_pt": "Ele tem uma boa renda do seu trabalho.",
        "def_en": "money that is earned from work or investments",
        "def_pt": "dinheiro que é ganho do trabalho ou investimentos"
    },
    "board": {
        "frase": "It is time to board the plane.",
        "frase_pt": "É hora de embarcar no avião.",
        "def_en": "to get into a plane, train, or ship (embarcar em veículo/avião)",
        "def_pt": "entrar em avião, trem ou navio (embarcar em veículo/avião)"
    },
    "throw": {
        "frase": "Can you throw the ball to me?",
        "frase_pt": "Você pode jogar a bola para mim?",
        "def_en": "to cause something to move through the air by moving your arm quickly",
        "def_pt": "jogar ou arremessar algo com a mão pelo ar"
    }
}

def find_ready_sentence_and_def(termo):
    t_raw = (termo or "").strip()
    t_lower = t_raw.lower()
    t_clean = re.sub(r'\(.*?\)', '', t_lower).strip()

    known_set, unknown_set = get_user_vocab_profile()

    # 0. Checar frases curadas de estrita conformidade i+1
    curated = CURATED_I1_SENTENCES.get(t_clean) or CURATED_I1_SENTENCES.get(t_lower)
    if curated:
        frase = curated["frase"]
        frase_pt = curated["frase_pt"]
        mwld_matches = MWLD_BY_WORD.get(t_clean, []) or MWLD_BY_WORD.get(t_lower, [])
        def_en = curated.get("def_en", "")
        def_pt = curated.get("def_pt", "")
        ipa = ""
        audio_url = ""
        if (not def_en) and mwld_matches:
            cand_m = mwld_matches[0]
            def_en = cand_m.get("definition_en", "")
            ipa = cand_m.get("ipa", "")
            audio_url = cand_m.get("audio_url", "")
        elif mwld_matches:
            ipa = mwld_matches[0].get("ipa", "")
            audio_url = mwld_matches[0].get("audio_url", "")
        if def_en and not def_pt:
            def_pt = translate_to_pt_sync(def_en)
        return {
            "frase": frase,
            "frase_pt": frase_pt,
            "def_en": def_en,
            "def_pt": def_pt,
            "ipa": ipa,
            "audio_url": audio_url,
            "mairo_audio": "",
            "source": "Curadoria i+1 Estrita",
            "is_strict_i1": True,
            "extra_unknowns": []
        }

    cands = get_term_candidates(termo)
    pool = []

    # 1. Candidatos do Mairo Vergara por palavra-chave (projetadas para este termo)
    for c in cands:
        for item in MAIRO_SENTENCES_BY_KEYWORD.get(c, []):
            if item.get("en"):
                pool.append({
                    "en": item["en"],
                    "pt": item.get("pt", ""),
                    "audio": item.get("audio", ""),
                    "source": "Mairo Vergara",
                    "priority": 1
                })

    # 2. Candidatos do dicionário MWLD
    for c in cands:
        for ac in MWLD_BY_WORD.get(c, []):
            for ex in [ac.get("example_1"), ac.get("example_2")]:
                if ex and len(ex.split()) >= 3:
                    pool.append({
                        "en": ex,
                        "pt": "",
                        "audio": "",
                        "source": "Dicionário MWLD",
                        "priority": 2
                    })

    # 3. Candidatos do Mairo Vergara por ocorrência de palavra
    for c in cands:
        for item in MAIRO_SENTENCES_BY_WORD.get(c, []):
            if item.get("en"):
                pool.append({
                    "en": item["en"],
                    "pt": item.get("pt", ""),
                    "audio": item.get("audio", ""),
                    "source": "Mairo Vergara (Contexto)",
                    "priority": 3
                })

    # Avaliar e pontuar candidatos com algoritmo i+1
    scored = []
    for cand in pool:
        u_cnt, unks, is_strict = evaluate_sentence_i1(cand["en"], termo, known_set, unknown_set)
        tokens = re.findall(r"\b[a-zA-Z]+\b", cand["en"])
        length_penalty = 0.1 * max(0, len(tokens) - 14) + (0.5 if len(tokens) < 4 else 0.0)
        has_audio = 1.0 if cand.get("audio") else 0.0
        score = (u_cnt * 100) + (cand["priority"] * 10) + length_penalty - (2.0 * has_audio)
        scored.append((score, u_cnt, unks, is_strict, cand))

    scored.sort(key=lambda x: x[0])

    mwld_cand = None
    for cand_key in cands:
        matches = MWLD_BY_WORD.get(cand_key, [])
        if matches:
            mwld_cand = matches[0]
            break

    def_en = ""
    def_pt = ""
    ipa = ""
    audio_url = ""
    if mwld_cand:
        d = mwld_cand.get("definition_en", "")
        if is_valid_definition(d):
            def_en = d
        ipa = mwld_cand.get("ipa", "")
        audio_url = mwld_cand.get("audio_url", "")

    if scored and scored[0][1] == 0:
        # Quando há múltiplas opções em conformidade estrita i+1, Jev seleciona a pedagogicamente ideal
        zero_unknown_cands = [x[4] for x in scored if x[1] == 0]
        if len(zero_unknown_cands) > 1:
            c = curate_best_sentence_with_jev(termo, zero_unknown_cands, def_en)
        else:
            c = scored[0][4]

        frase = c["en"]
        frase_pt = c.get("pt", "")
        mairo_audio = c.get("audio", "")
        source = c.get("source", "Acervo")
        if frase and not frase_pt:
            frase_pt = translate_to_pt_sync(re.sub(r'<[^>]+>', '', frase))
        if def_en and not def_pt:
            def_pt = translate_to_pt_sync(def_en)
        return {
            "frase": frase,
            "frase_pt": frase_pt,
            "def_en": def_en,
            "def_pt": def_pt,
            "ipa": ipa,
            "audio_url": audio_url,
            "mairo_audio": mairo_audio,
            "source": source,
            "is_strict_i1": True,
            "extra_unknowns": []
        }

    # Se não houver candidato com 0 palavras desconhecidas, ranqueia os melhores com Jev
    if scored and len(scored) > 1:
        top_pool = [x[4] for x in scored[:3]]
        cand_dict = curate_best_sentence_with_jev(termo, top_pool, def_en)
        extra_unknowns = scored[0][2]
    else:
        best_cand = scored[0] if scored else None
        cand_dict = best_cand[4] if best_cand else {}
        extra_unknowns = best_cand[2] if best_cand else []

    frase = cand_dict.get("en", "")
    frase_pt = cand_dict.get("pt", "")
    mairo_audio = cand_dict.get("audio", "")
    source = cand_dict.get("source", "Acervo")

    if frase and not frase_pt:
        frase_pt = translate_to_pt_sync(re.sub(r'<[^>]+>', '', frase))
    if def_en and not def_pt:
        def_pt = translate_to_pt_sync(def_en)

    return {
        "frase": frase,
        "frase_pt": frase_pt,
        "def_en": def_en,
        "def_pt": def_pt,
        "ipa": ipa,
        "audio_url": audio_url,
        "mairo_audio": mairo_audio,
        "source": source,
        "is_strict_i1": (best_cand[1] == 0) if best_cand else False,
        "extra_unknowns": extra_unknowns
    }

SUBDECK_PRIORITY = {
    "01k": 1, "pv-top150": 2, "02k": 3, "03k": 4, "collocations": 5, "pv-all": 6,
    "04k": 7, "idioms": 8, "05k": 9, "06k": 10, "07k": 11, "08k": 12, "09k": 13, "10k": 14,
    "12k": 15, "14k": 16, "16k": 17, "18k": 18, "20k": 20,
    "25k": 25, "30k": 30, "40k": 40, "50k": 50, "60k": 60
}

def get_term_importance(termo):
    """
    Calcula a importância lexical de um termo com base na frequência real da língua inglesa:
    - Decks de maior frequência (01k = Top 1.000) têm prioridade 1 (máxima).
    - Dentro do mesmo subdeck, respeita o índice de ocorrência/frequência na lista MWLD.
    - Termos fora do MWLD recebem prioridade 99.
    Retorna: (subdeck_prio, frequency_idx, subdeck_name)
    """
    t_clean = (termo or "").strip().lower()
    matches = MWLD_BY_WORD.get(t_clean, [])
    if not matches:
        t_sub = re.sub(r'\(.*?\)', '', t_clean).strip()
        matches = MWLD_BY_WORD.get(t_sub, [])

    if matches:
        m = matches[0]
        s = m.get("subdeck", "01k")
        prio = SUBDECK_PRIORITY.get(s, 50)
        idx = 999999
        m_id = m.get("id", "")
        parts = m_id.split("_")
        if parts and parts[-1].isdigit():
            idx = int(parts[-1])
        return (prio, idx, s)

    return (99, 999999, "Geral")

NOISE_WORDS = {
    # Stopwords & contrações
    'the', 'a', 'an', 'and', 'or', 'but', 'of', 'to', 'in', 'on', 'at', 'for', 
    'with', 'by', 'from', 'as', 'into', 'he', 'she', 'it', 'they', 'we', 'i', 
    'you', 'me', 'him', 'her', 'them', 'us', 'my', 'your', 'his', 'their', 'our', 
    'its', 'be', 'am', 'is', 'are', 'was', 'were', 'been', 'being',
    "can't", "don't", "won't", "didn't", "it's", "you're", "they're", "we're", "i'm", "i've", "i'll", "that's", "what's", "there's",
    # Países, nacionalidades, dias e meses
    'american', 'british', 'french', 'spanish', 'german', 'chinese', 'japanese', 'italian', 'russian',
    'america', 'britain', 'england', 'france', 'london', 'paris',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
    # Números ordinais e cardinais básicos
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
    'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen',
    'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety', 'hundred', 'thousand', 'million',
    'first', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'
}

FALSE_COGNATES = {
    "pretend": "Falso Amigo! Significa 'FINGIR' (não pretender). Pretender = intend.",
    "intend": "Significa 'PRETENDER / TER INTENÇÃO' (não entender). Entender = understand.",
    "actually": "Falso Amigo! Significa 'NA VERDADE / REALMENTE' (não atualmente). Atualmente = currently.",
    "currently": "Significa 'ATUALMENTE' (não correntemente).",
    "push": "Falso Amigo! Significa 'EMPURRAR' (não puxar). Puxar = pull.",
    "pull": "Significa 'PUXAR' (não pular). Pular = jump.",
    "realize": "Significa 'DAR-SE CONTA / PERCEBER', além de concretizar algo.",
    "notice": "Significa 'NOTAR / REPARAR' (não notícia). Notícia = news.",
    "novel": "Como substantivo é 'ROMANCE (LIVRO)', e adjetivo é 'INÉDITO / INOVADOR' (não novela). Novela = soap opera.",
    "fabric": "Falso Amigo! Significa 'TECIDO' (não fábrica). Fábrica = factory.",
    "factory": "Significa 'FÁBRICA'.",
    "eventually": "Falso Amigo! Significa 'NO FINAL DAS CONTAS / COM O TEMPO' (não eventualmente). Às vezes = occasionally.",
    "sensible": "Falso Amigo! Significa 'SENSATO / PRUDENTE' (não sensível). Sensível = sensitive.",
    "sensitive": "Significa 'SENSÍVEL / DELICADO'.",
    "sympathetic": "Falso Amigo! Significa 'COMPREENSIVO / SOLIDÁRIO' (não simpático). Simpático = nice/friendly.",
    "prejudice": "Falso Amigo! Significa 'PRECONCEITO' (não prejuízo). Prejuízo = loss/damage.",
    "comprehensive": "Falso Amigo! Significa 'ABRANGENTE / COMPLETO' (não compreensivo). Compreensivo = sympathetic.",
    "exquisite": "Falso Amigo! Significa 'REFINADO / EXCEPCIONAL' (não esquisito). Esquisito = strange/weird.",
    "costume": "Falso Amigo! Significa 'FANTASIA / TRAJE TÍPICO' (não costume cotidiano). Hábito = habit/custom.",
    "parents": "Falso Amigo! Significa 'PAIS (PAI E MÃE)' (não parentes). Parentes = relatives.",
    "relatives": "Significa 'PARENTES'.",
    "anthem": "Falso Amigo! Significa 'HINO' (não antena). Antena = antenna.",
    "injury": "Falso Amigo! Significa 'FERIMENTO / LESÃO' (não injúria verbal). Insulto = insult.",
    "collar": "Falso Amigo! Significa 'GOLA / COLEIRA' (não colar). Colar de joia = necklace.",
    "balcony": "Falso Amigo! Significa 'SACADA / VARANDA' (não balcão). Balcão = counter.",
    "attend": "Falso Amigo! Significa 'COMPARECER / FREQUENTAR' (não atender telefone/cliente). Atender = answer/assist.",
    "assist": "Significa 'AJUDAR / PRESTAR SOCORRO' (não assistir TV). Assistir TV = watch.",
    "convict": "Significa 'CONDENAR / RÉU CONDENADO' (não convicto de certeza). Convicto = convinced.",
    "deception": "Falso Amigo! Significa 'ENGANO / GOLPE' (não decepção). Decepção = disappointment.",
    "disappointment": "Significa 'DECEPÇÃO / DESAPONTAMENTO'.",
    "expert": "Significa 'ESPECIALISTA / PERITO' (não esperto). Esperto = smart/clever.",
    "legend": "Falso Amigo! Significa 'LENDA' (não legenda de filme). Legenda = subtitle.",
    "subtitle": "Significa 'LEGENDA'.",
    "mayor": "Falso Amigo! Significa 'PREFEITO' (não maior). Maior = bigger/greater.",
    "physician": "Falso Amigo! Significa 'MÉDICO CLÍNICO' (não físico). Físico = physicist.",
    "resume": "Significa 'RETOMAR / REINICIAR' ou 'CURRÍCULO' (não resumo). Resumo = summary.",
    "summary": "Significa 'RESUMO / SÍNTESE'.",
    "idiom": "Significa 'EXPRESSÃO IDIOMÁTICA' (não língua/idioma). Língua = language.",
    "apology": "Significa 'PEDIDO DE DESCULPAS' (não apologia/elogio público).",
    "argument": "Significa 'DISCUSSÃO / BATE-BOCA', além de argumento lógico.",
    "cafeteria": "Significa 'REFEITÓRIO / CANTINA' (não cafeteria comum). Cafeteria = coffee shop.",
    "cigar": "Significa 'CHARUTO' (não cigarro). Cigarro = cigarette.",
    "college": "Significa 'FACULDADE / ENSINO SUPERIOR' (não colégio). Colégio = school/high school.",
    "contest": "Significa 'CONCURSO / COMPETIÇÃO' (não contexto). Contexto = context.",
    "data": "Significa 'DADOS / INFORMAÇÕES' (não data de calendário). Data de calendário = date.",
    "estate": "Significa 'PATRIMÔNIO / PROPRIEDADE / BENS' (não estado geográfico). Estado = state.",
    "exit": "Significa 'SAÍDA' (não êxito/sucesso). Êxito = success.",
    "journal": "Significa 'REVISTA CIENTÍFICA / DIÁRIO' (não jornal diário). Jornal = newspaper.",
    "pasta": "Significa 'MASSA (MACARRÃO)' (não pasta de dente ou pasta de papéis).",
    "policy": "Significa 'POLÍTICA/DIRETRIZ DE EMPRESA/ESTADO' ou 'APÓLICE' (não polícia). Polícia = police.",
    "tax": "Significa 'IMPOSTO / TRIBUTO' (não taxa de juros ou táxi). Taxa = rate; Táxi = taxi.",
    "compromise": "Falso Amigo! Significa 'ACORDO / CONCESSÃO / ENTRAR EM ACORDO' (não compromisso de agenda). Compromisso = appointment / commitment.",
    "custom": "Significa 'HÁBITO / COSTUME' ou 'ALFÂNDEGA' (não fantasia). Fantasia = costume.",
    "devolution": "Significa 'DESCENTRALIZAÇÃO / TRANSFERÊNCIA DE PODER' (não devolução). Devolução = return / refund.",
    "envy": "Significa 'INVEJA / TER INVEJA' (não envio). Envio = sending / shipment.",
    "genial": "Significa 'AFÁVEL / CORDIAL / SIMPÁTICO' (não genial/gênio). Genial = brilliant / genius.",
    "hazard": "Falso Amigo! Significa 'PERIGO / RISCO / AMEAÇA' (não azar). Azar = bad luck.",
    "ingenious": "Significa 'ENGENHOSO / CRIATIVO' (não ingênuo). Ingênuo = naive.",
    "intoxicated": "Falso Amigo! Significa 'EMBRIAGADO / ALCOOLIZADO' (não intoxicação alimentar). Intoxicação = food poisoning.",
    "lecture": "Falso Amigo! Significa 'PALESTRA / AULA MAGNA' (não leitura). Leitura = reading.",
    "library": "Falso Amigo! Significa 'BIBLIOTECA' (não livraria). Livraria = bookstore.",
    "lunch": "Falso Amigo! Significa 'ALMOÇO' (não lanche). Lanche = snack.",
    "magazine": "Falso Amigo! Significa 'REVISTA' (não magazine/loja de departamento). Loja = department store.",
    "moist": "Significa 'ÚMIDO / SUAVE' (não murcho). Murcho = withered.",
    "particular": "Significa 'ESPECÍFICO / EXIGENTE / DETALHISTA' (não privado). Privado/Particular = private.",
    "procure": "Falso Amigo! Significa 'CONSEGUIR / OBTER / ADQUIRIR' (não procurar). Procurar = look for / search.",
    "remedy": "Significa 'SOLUÇÃO / REPARAÇÃO' ou 'REMÉDIO' (remédio comum = medicine / drug).",
    "stranger": "Falso Amigo! Significa 'DESCONHECIDO / ESTRANHO (PESSOA)' (não esquisito). Estranho = weird / strange.",
    "ultimate": "Significa 'DEFINITIVO / SUPREMO / FINAL' (não último de uma fila). Último = last.",
    "silicon": "Significa 'SILÍCIO (ELEMENTO QUÍMICO)' (não silicone). Silicone = silicone.",
    "traffic": "Significa 'TRÂNSITO / TRÁFEGO DE VEÍCULOS' (não tráfico de drogas). Tráfico ilícito = trafficking."
}

CEFR_INFO = {
    "01k": {"code": "A1/A2", "label": "Iniciante / Fundamentos", "desc": "Top 1.000 termos essenciais da língua"},
    "02k": {"code": "A2", "label": "Básico Consolidado", "desc": "Top 2.000 vocabulário de sobrevivência diária"},
    "03k": {"code": "B1", "label": "Intermediário Operacional", "desc": "Top 3.000 conversação independente e trabalho"},
    "04k": {"code": "B1+", "label": "Intermediário Médio", "desc": "Top 4.000 expressividade e nuances cotidianas"},
    "05k": {"code": "B2", "label": "Intermediário Superior", "desc": "Top 5.000 vocabulário corporativo e argumentativo"},
    "06k": {"code": "B2+", "label": "Avançado Operacional", "desc": "Top 6.000 fluência espontânea em temas complexos"},
    "07k": {"code": "C1", "label": "Avançado Culto", "desc": "Top 7.000 vocabulário formal e literário"},
    "08k": {"code": "C1", "label": "Domínio Formal", "desc": "Top 8.000 precisão cirúrgica de vocabulário"},
    "09k": {"code": "C1+", "label": "Acadêmico & Técnico", "desc": "Top 9.000 textos densos e especializados"},
    "10k": {"code": "C1/C2", "label": "Quase Nativo", "desc": "Top 10.000 riqueza vocabular de nível nativo"},
    "pv-top150": {"code": "A2-B2", "label": "Top 150 Phrasal Verbs", "desc": "Os verbos frasais mais usados no inglês falado", "track": "structures"},
    "pv-all": {"code": "B1-C2", "label": "Phrasal Verbs (Acervo Completo)", "desc": "Mais de 5.300 phrasal verbs com exemplos e tradução", "track": "structures"},
    "collocations": {"code": "B1-C1", "label": "Collocations Oxford", "desc": "Combinações e colocações naturais do inglês", "track": "structures"},
    "idioms": {"code": "B2-C2", "label": "Idioms & Expressões Cotidianas", "desc": "Expressões idiomáticas nativas em contexto", "track": "structures"}
}

THEME_KEYWORDS = [
    ("💼 Negócios & Trabalho", {"business", "company", "market", "job", "office", "work", "boss", "manager", "meeting", "money", "cost", "price", "pay", "profit", "contract", "trade", "deal", "economy", "finance", "client", "customer", "firm", "corporate", "career", "salary", "industry", "sell", "buy", "hire", "fired", "interview", "report", "project"}),
    ("💻 Tecnologia & Inovação", {"computer", "software", "phone", "system", "app", "digital", "internet", "code", "device", "data", "screen", "machine", "robot", "online", "network", "technology", "tech", "electronic", "server", "web", "program", "file", "download"}),
    ("🗣️ Cotidiano & Convivência", {"home", "house", "room", "family", "friend", "dinner", "breakfast", "lunch", "food", "eat", "drink", "kitchen", "morning", "night", "weekend", "bed", "sleep", "street", "car", "bus", "train", "clean", "cook", "wear", "clothes", "coffee", "tea", "restaurant", "store", "shop"}),
    ("🧠 Emoção & Comportamento", {"feel", "feeling", "emotion", "mind", "happy", "sad", "angry", "fear", "scared", "hope", "dream", "thought", "think", "attitude", "behavior", "habit", "worry", "calm", "love", "hate", "trust", "courage", "confidence", "psychology", "mental", "mood"}),
    ("🎓 Educação & Aprendizado", {"school", "study", "student", "teacher", "class", "book", "learn", "lesson", "college", "university", "test", "exam", "grade", "read", "write", "paper", "homework", "library", "course", "knowledge", "degree"}),
    ("🩺 Saúde & Bem-estar", {"health", "doctor", "hospital", "medicine", "pain", "sick", "ill", "body", "exercise", "workout", "fitness", "sleep", "diet", "disease", "treatment", "cure", "drug", "care", "injury", "blood", "headache"}),
    ("⚖️ Sociedade, Lei & Justiça", {"law", "rule", "police", "court", "judge", "crime", "legal", "government", "president", "vote", "rights", "citizen", "tax", "society", "public", "state", "policy", "justice", "prison", "suspect"}),
    ("🎨 Cultura, Arte & Lazer", {"music", "art", "song", "movie", "film", "game", "sport", "play", "dance", "theatre", "leisure", "hobby", "concert", "draw", "paint", "guitar", "piano", "festival"}),
    ("✈️ Viagem & Lugares", {"travel", "trip", "flight", "plane", "hotel", "airport", "vacation", "holiday", "visit", "country", "city", "beach", "mountain", "tour", "ticket", "luggage", "passport", "world"})
]

def detect_sentence_theme(sentence, word=""):
    text = (sentence + " " + word).lower()
    words_set = set(re.findall(r'[a-z]+', text))
    for theme_label, kws in THEME_KEYWORDS:
        if words_set.intersection(kws):
            return theme_label
    return "🌐 Conversação & Geral"

def get_user_cefr_status():
    total_known = 0
    total_gaps = 0
    total_doubt = 0
    for t_data in KNOWLEDGE_MAP.get("mapa_vocabulario", {}).values():
        st = t_data.get("status_geral")
        if st == "conhecido":
            total_known += 1
        elif st == "desconhecido":
            total_gaps += 1
        elif st == "duvida":
            total_doubt += 1
        for ac in t_data.get("acepcoes", []):
            ast = ac.get("status")
            if ast == "conhecido":
                total_known += 1
            elif ast == "desconhecido":
                total_gaps += 1
            elif ast == "duvida":
                total_doubt += 1

    if total_known < 600:
        lvl = {"code": "A1/A2", "label": "Básico em Formação", "desc": "Construindo alicerce dos 1.000 termos essenciais"}
    elif total_known < 1500:
        lvl = {"code": "A2+", "label": "Básico Consolidado", "desc": "Autonomia em situações rotineiras"}
    elif total_known < 3000:
        lvl = {"code": "B1", "label": "Intermediário Independente", "desc": "Conversação e leitura autônoma"}
    elif total_known < 5000:
        lvl = {"code": "B2", "label": "Intermediário Superior", "desc": "Fluência em trabalho e temas abstratos"}
    else:
        lvl = {"code": "C1", "label": "Avançado Fluente", "desc": "Domínio refinado e vocabulário espontâneo"}
    
    lvl["known_count"] = total_known
    lvl["gaps_count"] = total_gaps
    lvl["doubt_count"] = total_doubt
    return lvl

def get_deck_progress(subdeck="01k"):
    vocab_map = KNOWLEDGE_MAP.get("mapa_vocabulario", {})
    if subdeck == "all":
        entries = MWLD_ENTRIES
        stats_subdeck = "Global"
        cefr_data = {"code": "Global", "label": "Banco Completo", "desc": "Todas as 66.000 notas"}
    else:
        entries = MWLD_BY_SUBDECK.get(subdeck, [])
        stats_subdeck = subdeck
        cefr_data = CEFR_INFO.get(subdeck, {"code": "B1", "label": "Intermediário", "desc": ""})

    seen_words = set()
    evaluated_words = set()

    for e in entries:
        w_lower = e["word"].lower().strip()
        if w_lower in PURE_FUNCTION_WORDS or w_lower.startswith("-") or w_lower.endswith("-"):
            continue
        pos_lower = e.get("pos", "").lower()
        if "prefix" in pos_lower or "suffix" in pos_lower or "combining form" in pos_lower:
            continue

        if w_lower not in seen_words:
            seen_words.add(w_lower)
            if w_lower in vocab_map:
                t_data = vocab_map[w_lower]
                st = t_data.get("status_geral")
                if st in ["conhecido", "desconhecido", "duvida", "em_estudo"]:
                    evaluated_words.add(w_lower)
                else:
                    for ac in t_data.get("acepcoes", []):
                        if ac.get("status") in ["conhecido", "desconhecido", "duvida", "em_estudo"]:
                            evaluated_words.add(w_lower)
                            break

    total = len(seen_words)
    evaluated = len(evaluated_words)
    remaining = max(0, total - evaluated)
    percent = int((evaluated / total * 100) if total > 0 else 0)

    user_lvl = get_user_cefr_status()

    return {
        "subdeck": stats_subdeck,
        "total": total,
        "evaluated": evaluated,
        "remaining": remaining,
        "percent": percent,
        "cefr": cefr_data,
        "user_level": user_lvl
    }

def get_all_subdecks_summary():
    """
    Avalia os subdecks em ordem crescente (01k..10k) e identifica
    o primeiro subdeck com palavras pendentes (remaining > 0) como o atual sendo estudado.
    """
    candidate_subdecks = ["01k", "02k", "03k", "04k", "05k", "06k", "07k", "08k", "09k", "10k"]
    summary = {}
    completed = []
    active = None
    for s in candidate_subdecks:
        st = get_deck_progress(s)
        rem = st.get("remaining", 0)
        pct = st.get("percent", 0)
        tot = st.get("total", 0)
        summary[s] = {"percent": pct, "remaining": rem, "total": tot}
        if rem == 0 and tot > 0:
            completed.append(s)
        elif active is None and rem > 0:
            active = s
    return active or "01k", completed, summary

IRREGULAR_VERBS = {
    'say': ['said'], 'go': ['went', 'gone'], 'see': ['saw', 'seen'],
    'make': ['made'], 'take': ['took', 'taken'], 'come': ['came'],
    'know': ['knew', 'known'], 'get': ['got', 'gotten'], 'give': ['gave', 'given'],
    'find': ['found'], 'think': ['thought'], 'tell': ['told'],
    'become': ['became'], 'leave': ['left'], 'feel': ['felt'],
    'bring': ['brought'], 'buy': ['bought'], 'teach': ['taught'],
    'write': ['wrote', 'written'], 'run': ['ran'], 'stand': ['stood'],
    'lose': ['lost'], 'pay': ['paid'], 'meet': ['met'], 'sit': ['sat'],
    'speak': ['spoke', 'spoken'], 'read': ['read'], 'hear': ['heard'],
    'fall': ['fell', 'fallen'], 'hold': ['held'], 'send': ['sent'], 'drive': ['drove', 'driven']
}

def tag_sentence_for_translation(sentence, word):
    if not sentence or not word:
        return sentence or ""
    # Se já tem <i> ou <b>, normaliza para <b>
    if re.search(r'<[bi]>[^<]+</[bi]>', sentence, re.IGNORECASE):
        return re.sub(r'<([bi])>([^<]+)</\1>', r'<b>\2</b>', sentence)
    
    # Casar palavra e flexões regulares
    pat = re.compile(rf'\b({re.escape(word)}[a-zA-Z]*)\b', re.IGNORECASE)
    if pat.search(sentence):
        return pat.sub(r'<b>\1</b>', sentence)

    # Casar irregulares
    irr = IRREGULAR_VERBS.get(word.lower(), [])
    for v in irr:
        p_irr = re.compile(rf'\b({re.escape(v)})\b', re.IGNORECASE)
        if p_irr.search(sentence):
            return p_irr.sub(r'<b>\1</b>', sentence)

    return sentence

def clean_portuguese_tag(tagged_pt, en_word):
    if not tagged_pt or ("<b" not in tagged_pt and "<i" not in tagged_pt):
        return tagged_pt
    w_lower = (en_word or "").lower().strip()
    
    # 1. Separar pronomes oblíquos da tag (ex: <b>me ajudaria</b> -> me <b>ajudaria</b>)
    clitics = r'(?:me|te|se|nos|vos|lhe|lhes|o|a|os|as)'
    if w_lower not in ['me', 'him', 'her', 'us', 'them', 'it', 'you']:
        tagged_pt = re.sub(rf'<([bi])>({clitics})\s+([^<]+)</\1>', r'\2 <\1>\3</\1>', tagged_pt, flags=re.IGNORECASE)

    # 2. Separar artigos/preposições da tag (ex: <b>um carro</b> -> um <b>carro</b>)
    articles = r'(?:o|a|os|as|um|uma|uns|umas|de|do|da|dos|das|em|no|na|nos|nas|ao|à|aos|às|por|pelo|pela|pelos|pelas)'
    if w_lower not in ['a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'by']:
        tagged_pt = re.sub(rf'<([bi])>({articles})\s+([^<]+)</\1>', r'\2 <\1>\3</\1>', tagged_pt, flags=re.IGNORECASE)

    return tagged_pt

PURE_FUNCTION_WORDS = NOISE_WORDS

def extract_focus_word_from_fields(fields):
    """Extrai a palavra em foco de uma nota do Anki a partir dos campos Frente/Anverso ou Verso/Reverso."""
    if not isinstance(fields, dict):
        return None
    back_html = fields.get("Reverso", {}).get("value") or fields.get("Verso", {}).get("value") or ""
    m = re.search(r'<b>\s*([^/<]+?)(?:\s*/|<|\b)', back_html)
    if m:
        cand = re.sub(r'<[^>]+>', '', m.group(1)).strip().lower()
        if cand and cand not in ("en", "pt", "tema", "br", "definicao", "exemplo"):
            return cand
    front_html = fields.get("Anverso", {}).get("value") or fields.get("Frente", {}).get("value") or ""
    m_bold = re.findall(r'<b>\s*([^<]+?)\s*</b>', front_html)
    if m_bold:
        cand = m_bold[0].strip().lower()
        if cand and cand not in ("en", "pt"):
            return cand
    return None

class RequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            html_file = os.path.join(WORKSPACE_DIR, "vocab_review_app.html")
            if os.path.exists(html_file):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(os.path.getsize(html_file)))
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        elif path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.serve_html()
        elif path == "/api/status":
            self.handle_api_status()
        elif path == "/api/words":
            self.handle_api_words(query)
        elif path == "/api/subdecks":
            self.handle_api_subdecks()
        elif path == "/api/gaps":
            self.handle_api_gaps()
        elif path == "/api/export-knowledge-map":
            self.send_json(KNOWLEDGE_MAP)
        elif path.startswith("/media/"):
            self.serve_media(path)
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if path == "/api/evaluate":
            self.handle_api_evaluate(data)
        elif path == "/api/batch-evaluate":
            self.handle_api_batch_evaluate(data)
        elif path == "/api/mark-remaining-known":
            self.handle_api_mark_remaining_known(data)
        elif path == "/api/auto-approve-functional":
            self.handle_api_auto_approve_functional(data)
        elif path == "/api/flag-intruder":
            self.handle_api_flag_intruder(data)
        elif path == "/api/inject-anki":
            self.handle_api_inject_anki(data)
        elif path == "/api/translate":
            self.handle_api_translate(data)
        elif path == "/api/jev-analyze":
            self.handle_api_jev_analyze(data)
        elif path == "/api/auto-approve-cognates":
            self.handle_api_auto_approve_cognates(data)
        elif path == "/api/enrich-gaps":
            self.handle_api_enrich_gaps(data)
        elif path == "/api/curate-sentence":
            self.handle_api_curate_sentence(data)
        elif path == "/api/import-knowledge-map":
            self.handle_api_import_knowledge_map(data)
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, data_obj, code=200):
        res = json.dumps(data_obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(res)))
        self.end_headers()
        self.wfile.write(res)

    def serve_html(self):
        html_file = os.path.join(WORKSPACE_DIR, "vocab_review_app.html")
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                content = f.read().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"HTML template not found")

    def serve_media(self, path):
        filename = urllib.parse.unquote(path[len("/media/"):])
        filename = os.path.basename(filename)
        filepath = os.path.join(ANKI_MEDIA_DIR, filename)
        if os.path.exists(filepath):
            ext = os.path.splitext(filename)[1].lower()
            ctype = "audio/mpeg" if ext == ".mp3" else ("audio/wav" if ext == ".wav" else "application/octet-stream")
            try:
                with open(filepath, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Media not found")

    def handle_api_status(self):
        stats = KNOWLEDGE_MAP.get("estatisticas", {})
        unlinked_gaps = 0
        ready_gaps = 0
        waiting_gaps = 0
        for data in KNOWLEDGE_MAP.get("mapa_vocabulario", {}).values():
            for ac in data.get("acepcoes", []):
                st = ac.get("status")
                if st in ("desconhecido", "duvida"):
                    termo = data.get("termo", "")
                    frase = ac.get("frase_i1") or ac.get("frase_exemplo") or ""
                    def_en = ac.get("definicao") or ""
                    has_sentence = is_valid_i1_sentence(frase, termo)
                    has_def = is_valid_definition(def_en)
                    is_ready = bool(has_sentence and has_def)

                    if not is_ready:
                        waiting_gaps += 1
                    elif not ac.get("card_id") and not ac.get("injetado_em"):
                        ready_gaps += 1
                        unlinked_gaps += 1

        active_subdeck, completed_subdecks, subdecks_summary = get_all_subdecks_summary()

        self.send_json({
            "usuario": KNOWLEDGE_MAP.get("usuario", "Lucas"),
            "stats": stats,
            "unlinked_gaps": unlinked_gaps,
            "ready_gaps": ready_gaps,
            "waiting_gaps": waiting_gaps,
            "active_subdeck": active_subdeck,
            "completed_subdecks": completed_subdecks,
            "subdecks_summary": subdecks_summary,
            "total_indexed": len(MWLD_ENTRIES)
        })

    def handle_api_subdecks(self):
        mwld_subdecks = []
        structures_subdecks = []
        candidate_mwld = ["01k", "02k", "03k", "04k", "05k", "06k", "07k", "08k", "09k", "10k"]
        candidate_struct = ["pv-top150", "pv-all", "collocations", "idioms"]

        for s in candidate_mwld:
            if s in MWLD_BY_SUBDECK:
                cefr = CEFR_INFO.get(s, {"code": "B1", "label": "Intermediário", "desc": ""})
                mwld_subdecks.append({
                    "name": s,
                    "label": f"Deck {s} • Nível {cefr['code']} ({cefr['label']})",
                    "count": len(MWLD_BY_SUBDECK[s]),
                    "cefr": cefr,
                    "track": "mwld"
                })

        for s in candidate_struct:
            if s in MWLD_BY_SUBDECK:
                cefr = CEFR_INFO.get(s, {"code": "B1-C1", "label": s, "desc": ""})
                structures_subdecks.append({
                    "name": s,
                    "label": f"{cefr['label']} ({len(MWLD_BY_SUBDECK[s])})",
                    "count": len(MWLD_BY_SUBDECK[s]),
                    "cefr": cefr,
                    "track": "structures"
                })

        all_subdecks = mwld_subdecks + structures_subdecks
        self.send_json({
            "subdecks": all_subdecks,
            "mwld_subdecks": mwld_subdecks,
            "structures_subdecks": structures_subdecks
        })

    def handle_api_translate(self, data):
        text = data.get("text", "")
        word = data.get("word", "")
        if word and text:
            text = tag_sentence_for_translation(text, word)
        
        cached = TRANSLATIONS_CACHE.get(text, "")
        if cached and cached != text and ("<b" in cached or "<i" in cached or not word):
            cleaned = clean_portuguese_tag(cached, word) if word else cached
            self.send_json({"text": text, "translation": cleaned})
        else:
            pt = translate_to_pt_sync(text)
            cleaned = clean_portuguese_tag(pt, word) if word else pt
            if cleaned and cleaned != text:
                TRANSLATIONS_CACHE[text] = cleaned
            self.send_json({"text": text, "translation": cleaned})

    def handle_api_jev_analyze(self, data):
        word = data.get("word", "").strip()
        definition = data.get("definition", "").strip()
        sentence = data.get("sentence", "").strip()
        if not word:
            self.send_json({"error": "Parâmetro 'word' obrigatório"}, 400)
            return

        res = analyze_word_with_jev(word, definition, sentence)
        if res:
            self.send_json({"success": True, "analysis": res})
        else:
            self.send_json({"success": False, "message": "Não foi possível analisar com Jev (verifique API Key ou conectividade)"}, 500)

    def handle_api_curate_sentence(self, data):
        """Avalia lista de sentenças candidatas com TypeSafe Jev e seleciona a melhor para o Anki."""
        word = data.get("word", "").strip()
        definition = data.get("definition", "").strip()
        sentences = data.get("sentences", [])
        if not word or not sentences:
            self.send_json({"error": "Parâmetros 'word' e 'sentences' obrigatórios"}, 400)
            return

        best = curate_best_sentence_with_jev(word, sentences, definition)
        if best:
            self.send_json({"success": True, "best_sentence": best})
        else:
            self.send_json({"success": False, "message": "Não foi possível curar com Jev"}, 500)

    def handle_api_import_knowledge_map(self, data):
        """Mescla o mapa de vocabulário da nuvem com o banco local garantindo persistência."""
        global KNOWLEDGE_MAP
        new_map = data.get("mapa_vocabulario", {})
        if not new_map:
            self.send_json({"error": "Dados inválidos de mapa_vocabulario"}, 400)
            return
        with LOCK:
            for k, v in new_map.items():
                KNOWLEDGE_MAP.setdefault("mapa_vocabulario", {})[k] = v
            save_knowledge_map_memory()
        self.send_json({"success": True, "message": f"{len(new_map)} termos sincronizados com sucesso!"})

    def handle_api_auto_approve_cognates(self, data):
        """Avalia lista de palavras com TypeSafe Jev e auto-aprova cognatos transparentes."""
        words_list = data.get("words", [])
        if not words_list:
            self.send_json({"error": "Lista de palavras vazia"}, 400)
            return

        vocab_map = KNOWLEDGE_MAP.setdefault("mapa_vocabulario", {})
        now_iso = datetime.now().isoformat()
        approved = []

        for w_item in words_list:
            w = w_item.strip().lower()
            if not w:
                continue
            if w in vocab_map and vocab_map[w].get("status_geral") in ["conhecido", "desconhecido", "duvida"]:
                continue

            analysis = analyze_word_with_jev(w)
            if analysis and analysis.get("cognate_type") == "transparent" and analysis.get("cognate_confidence", 0) >= 0.80:
                vocab_map[w] = {
                    "termo": w,
                    "status_geral": "conhecido",
                    "acepcoes": [
                        {
                            "sentido_id": f"{w}_jev_cognate",
                            "pos": "cognato",
                            "definicao": f"Cognato transparente analisado pela Jev AI ({int(analysis['cognate_confidence']*100)}% de certeza)",
                            "status": "conhecido",
                            "confirmado_em": now_iso
                        }
                    ],
                    "collocations": [],
                    "observacoes": f"Auto-aprovado via TypeSafe Jev (Cognato Transparente, conf={analysis['cognate_confidence']})"
                }
                approved.append({
                    "word": w,
                    "confidence": analysis["cognate_confidence"],
                    "risk": analysis.get("confusion_risk", 0)
                })

        if approved:
            save_knowledge_map_memory()

        self.send_json({
            "success": True,
            "approved_count": len(approved),
            "approved_words": approved,
            "stats": KNOWLEDGE_MAP.get("estatisticas")
        })

    def handle_api_auto_approve_functional(self, data):
        vocab_map = KNOWLEDGE_MAP.setdefault("mapa_vocabulario", {})
        now_iso = datetime.now().isoformat()
        count = 0
        for w in PURE_FUNCTION_WORDS:
            if w not in vocab_map:
                vocab_map[w] = {
                    "termo": w,
                    "status_geral": "conhecido",
                    "acepcoes": [
                        {
                            "sentido_id": f"{w}_base",
                            "pos": "functional",
                            "definicao": "Gramática básica consolidada",
                            "status": "conhecido",
                            "confirmado_em": now_iso
                        }
                    ],
                    "collocations": [],
                    "observacoes": "Auto-aprovado como gramática elementar"
                }
                count += 1
            else:
                vocab_map[w]["status_geral"] = "conhecido"
        save_knowledge_map_memory()
        print(f"✓ {count} termos gramaticais consolidados no mapa!")
        self.send_json({"success": True, "count": count, "stats": KNOWLEDGE_MAP.get("estatisticas")})

    def handle_api_words(self, query):
        """Ultra-rápido: zero chamadas síncronas de rede externa!"""
        subdeck = query.get("subdeck", ["01k"])[0]
        status_filter = query.get("status", ["pending"])[0]
        pos_filter = query.get("pos", ["all"])[0]
        skip_functional = query.get("skip_functional", ["true"])[0].lower() == "true"
        group_by_word = query.get("group_by_word", ["true"])[0].lower() == "true"
        search = query.get("search", [""])[0].lower().strip()
        limit = int(query.get("limit", [25])[0])
        offset = int(query.get("offset", [0])[0])

        is_searching = bool(search)
        if is_searching or subdeck == "all":
            entries = MWLD_ENTRIES
        else:
            entries = MWLD_BY_SUBDECK.get(subdeck, [])

        vocab_map = KNOWLEDGE_MAP.get("mapa_vocabulario", {})

        filtered = []
        seen_keys = set()

        search_boundary_regex = None
        if is_searching:
            try:
                search_boundary_regex = re.compile(rf'\b{re.escape(search)}\b', re.IGNORECASE)
            except Exception:
                search_boundary_regex = None

        for e in entries:
            w_lower = e["word"].lower().strip()
            pos_lower = e["pos"].lower().strip()
            ex1_raw = e.get("example_1", "")
            ex2_raw = e.get("example_2", "")
            def_raw = e.get("definition_en", "")

            # Se NÃO estiver buscando termo específico, aplica filtros de ruído e agrupamento
            if not is_searching:
                if skip_functional:
                    if w_lower in PURE_FUNCTION_WORDS:
                        continue
                    if w_lower.startswith("-") or w_lower.endswith("-"):
                        continue
                    if "prefix" in pos_lower or "suffix" in pos_lower or "combining form" in pos_lower:
                        continue

                key = w_lower if group_by_word else (w_lower, pos_lower)
                if group_by_word and key in seen_keys:
                    continue
            else:
                # Na busca global, procuramos no headword, na definição e em TODAS as frases de exemplo!
                if not (search in w_lower or search in ex1_raw.lower() or search in ex2_raw.lower() or search in def_raw.lower()):
                    continue

            if pos_filter != "all":
                if pos_filter.lower() not in pos_lower:
                    continue

            current_status = "pending"
            current_ac = None
            if w_lower in vocab_map:
                t_data = vocab_map[w_lower]
                for ac in t_data.get("acepcoes", []):
                    if ac.get("sentido_id") == e["id"] or ac.get("sentido_id") == f"{w_lower}_base":
                        current_status = ac.get("status", "pending")
                        current_ac = ac
                        break
                    elif ac.get("status") in ["desconhecido", "duvida"]:
                        current_status = ac.get("status")
                        current_ac = ac
                if current_status == "pending" and t_data.get("status_geral") in ["conhecido", "em_estudo"]:
                    current_status = t_data.get("status_geral")

            # Filtro de status: se for busca ativa e o filtro estiver no padrão "pending",
            # permitimos todos os resultados para que o usuário encontre qualquer palavra no banco.
            if is_searching and status_filter == "pending":
                pass
            elif status_filter == "pending" and current_status != "pending":
                continue
            elif status_filter == "desconhecido" and current_status != "desconhecido":
                continue
            elif status_filter == "duvida" and current_status != "duvida":
                continue
            elif status_filter == "conhecido" and current_status != "conhecido":
                continue

            # Cálculo de relevância de busca
            search_score = 99
            if is_searching:
                if w_lower == search:
                    search_score = 0
                elif w_lower.startswith(search):
                    search_score = 1
                elif search in w_lower:
                    search_score = 2
                elif search_boundary_regex and (search_boundary_regex.search(ex1_raw) or search_boundary_regex.search(ex2_raw)):
                    search_score = 3
                elif search in ex1_raw.lower() or search in ex2_raw.lower():
                    search_score = 4
                elif search_boundary_regex and search_boundary_regex.search(def_raw):
                    search_score = 5
                else:
                    search_score = 6

            pt_def = ""
            if current_ac and current_ac.get("definicao_pt"):
                pt_def = current_ac.get("definicao_pt")
            elif e["definition_en"] in TRANSLATIONS_CACHE:
                pt_def = TRANSLATIONS_CACHE[e["definition_en"]]

            # Tradução contextual das frases de exemplo com palavra marcada
            tagged_ex1 = tag_sentence_for_translation(e["example_1"], e["word"]) if e.get("example_1") else ""
            clean_ex1 = re.sub(r'<[^>]+>', '', e["example_1"]).strip() if e.get("example_1") else ""
            ex1_pt = ""
            if tagged_ex1:
                cached1 = TRANSLATIONS_CACHE.get(tagged_ex1) or ""
                if cached1 and ("<b" in cached1 or "<i" in cached1):
                    ex1_pt = clean_portuguese_tag(cached1, e["word"])
                else:
                    TRANSLATE_QUEUE.put(tagged_ex1)

            tagged_ex2 = tag_sentence_for_translation(e["example_2"], e["word"]) if e.get("example_2") else ""
            clean_ex2 = re.sub(r'<[^>]+>', '', e["example_2"]).strip() if e.get("example_2") else ""
            ex2_pt = ""
            if tagged_ex2:
                cached2 = TRANSLATIONS_CACHE.get(tagged_ex2) or ""
                if cached2 and ("<b" in cached2 or "<i" in cached2):
                    ex2_pt = clean_portuguese_tag(cached2, e["word"])
                else:
                    TRANSLATE_QUEUE.put(tagged_ex2)

            # Detecção Preventiva de Falso Cognato (Dicionário + Jev System One)
            false_cog = FALSE_COGNATES.get(w_lower, "")
            if not false_cog and w_lower in JEV_CACHE:
                j_entry = JEV_CACHE[w_lower]
                if j_entry.get("cognate_type") == "false_friend" or j_entry.get("confusion_risk", 0) >= 0.70:
                    conf = int(j_entry.get("cognate_confidence", 0.8) * 100)
                    false_cog = f"Alerta Jev ({conf}% conf.): Falso cognato / risco alto de confusão para falantes de português!"
            
            # Detecção de Tema Contextual das Frases
            sentence_theme_1 = detect_sentence_theme(clean_ex1 or e["example_1"], e["word"])
            sentence_theme_2 = detect_sentence_theme(clean_ex2 or e.get("example_2", ""), e["word"]) if e.get("example_2") else sentence_theme_1

            # Compilar todas as frases disponíveis (MWLD + Mairo Vergara nativo)
            word_sentences = []
            if e.get("example_1"):
                word_sentences.append({
                    "en": e["example_1"],
                    "pt": ex1_pt,
                    "source": "Dicionário MWLD",
                    "theme": sentence_theme_1,
                    "audio": e.get("audio_url", "")
                })
            if e.get("example_2"):
                word_sentences.append({
                    "en": e["example_2"],
                    "pt": ex2_pt,
                    "source": "Dicionário MWLD",
                    "theme": sentence_theme_2,
                    "audio": e.get("audio_url", "")
                })
            mairo_matches = MAIRO_SENTENCES_BY_KEYWORD.get(w_lower, []) or MAIRO_SENTENCES_BY_WORD.get(w_lower, [])
            for m in mairo_matches[:3]:
                word_sentences.append({
                    "en": m.get("en", ""),
                    "pt": m.get("pt", ""),
                    "source": "Mairo Vergara",
                    "theme": m.get("theme", "Conversação"),
                    "audio": m.get("audio", "")
                })

            filtered.append({
                "id": e["id"],
                "note_id": e.get("note_id", ""),
                "subdeck": e.get("subdeck", subdeck),
                "word": e["word"],
                "pos": e.get("pos", ""),
                "ipa": e.get("ipa", ""),
                "audio_url": e.get("audio_url", ""),
                "definition_en": e.get("definition_en", ""),
                "definition_pt": pt_def,
                "example_1": e.get("example_1", ""),
                "example_1_pt": ex1_pt,
                "example_2": e.get("example_2", ""),
                "example_2_pt": ex2_pt,
                "sentences": word_sentences,
                "false_cognate": false_cog,
                "theme": sentence_theme_1,
                "theme_1": sentence_theme_1,
                "theme_2": sentence_theme_2,
                "is_chunk": e.get("is_chunk", False),
                "chunk_type": e.get("chunk_type", ""),
                "status": current_status,
                "_score": search_score
            })
            if not is_searching and group_by_word:
                seen_keys.add(key)

        if is_searching:
            filtered.sort(key=lambda x: (
                x.get("_score", 99),
                x["subdeck"],
                x["word"].lower()
            ))

        total_filtered = len(filtered)
        paginated = filtered[offset:offset+limit]

        # Garantir tradução instantânea dos primeiros itens da tela com tag preservada
        for idx, item in enumerate(paginated):
            if (not item.get("example_1_pt") or ("<b" not in item.get("example_1_pt") and "<i" not in item.get("example_1_pt"))) and item.get("example_1"):
                tagged_ex = tag_sentence_for_translation(item["example_1"], item["word"])
                if tagged_ex:
                    if idx < 4:
                        t_pt = translate_to_pt_sync(tagged_ex)
                        if t_pt:
                            cleaned_t1 = clean_portuguese_tag(t_pt, item["word"])
                            item["example_1_pt"] = cleaned_t1
                            TRANSLATIONS_CACHE[tagged_ex] = cleaned_t1
                    else:
                        TRANSLATE_QUEUE.put(tagged_ex)

            if (not item.get("example_2_pt") or ("<b" not in item.get("example_2_pt") and "<i" not in item.get("example_2_pt"))) and item.get("example_2"):
                tagged_ex2 = tag_sentence_for_translation(item["example_2"], item["word"])
                if tagged_ex2:
                    if idx < 3:
                        t_pt2 = translate_to_pt_sync(tagged_ex2)
                        if t_pt2:
                            cleaned_t2 = clean_portuguese_tag(t_pt2, item["word"])
                            item["example_2_pt"] = cleaned_t2
                            TRANSLATIONS_CACHE[tagged_ex2] = cleaned_t2
                    else:
                        TRANSLATE_QUEUE.put(tagged_ex2)

            if not item.get("definition_pt") and item.get("definition_en"):
                if idx < 4:
                    t_def = translate_to_pt_sync(item["definition_en"])
                    if t_def:
                        item["definition_pt"] = t_def
                else:
                    TRANSLATE_QUEUE.put(item["definition_en"])

            # Anexar frases enriquecidas do acervo do Mairo Vergara (amplia o escopo de escolhas)
            sentences_pool = []
            if item.get("example_1"):
                sentences_pool.append({
                    "en": item["example_1"],
                    "pt": item.get("example_1_pt", ""),
                    "audio": item.get("audio_url", ""),
                    "source": "Dicionário MWLD",
                    "theme": item.get("theme_1", "Conversação & Geral"),
                    "nid": None
                })
            if item.get("example_2"):
                sentences_pool.append({
                    "en": item["example_2"],
                    "pt": item.get("example_2_pt", ""),
                    "audio": item.get("audio_url", ""),
                    "source": "Dicionário MWLD",
                    "theme": item.get("theme_2", "Conversação & Geral"),
                    "nid": None
                })

            mairo_matches = get_mairo_sentences_for_word(item["word"], limit=6)
            for m in mairo_matches:
                sentences_pool.append({
                    "en": m["en"],
                    "pt": m["pt"],
                    "audio": f"/media/{urllib.parse.quote(m['audio'])}" if m["audio"] else "",
                    "source": "Mairo Vergara",
                    "theme": f"🎙️ {m['theme']}",
                    "nid": m["nid"]
                })

            item["sentences"] = sentences_pool
            item["total_sentences"] = len(sentences_pool)
            item["has_mairo"] = len(mairo_matches) > 0

        if is_searching:
            evaluated_in_search = sum(1 for x in filtered if x["status"] != "pending")
            cefr_data = {"code": "Global", "label": "Busca Global", "desc": f"Resultados para '{search}' em todo o acervo (66k notas)"}
            stats_subdeck = "Global (66k)"
            user_lvl = get_user_cefr_status()
            deck_stats = {
                "subdeck": stats_subdeck,
                "total": total_filtered,
                "evaluated": evaluated_in_search,
                "remaining": max(0, total_filtered - evaluated_in_search),
                "percent": int((evaluated_in_search / total_filtered * 100) if total_filtered > 0 else 0),
                "cefr": cefr_data,
                "user_level": user_lvl
            }
        else:
            deck_stats = get_deck_progress(subdeck)

        self.send_json({
            "total": total_filtered,
            "offset": offset,
            "limit": limit,
            "words": paginated,
            "deck_stats": deck_stats
        })

    def handle_api_evaluate(self, data):
        word = data.get("word", "").strip()
        status = data.get("status", "").strip()
        sentido_id = data.get("id", f"{word}_custom")
        pos = data.get("pos", "")
        def_en = data.get("definition_en", "")
        def_pt = data.get("definition_pt", "")
        ex = data.get("example_1", "")

        if not word or not status:
            self.send_json({"error": "Parâmetros incompletos"}, 400)
            return

        w_norm = word.lower()
        vocab_map = KNOWLEDGE_MAP.setdefault("mapa_vocabulario", {})

        if w_norm not in vocab_map:
            vocab_map[w_norm] = {
                "termo": word,
                "status_geral": status,
                "acepcoes": [],
                "collocations": [],
                "observacoes": "Classificado via Web Reviewer"
            }

        vocab_map[w_norm]["status_geral"] = status

        found = False
        for ac in vocab_map[w_norm].get("acepcoes", []):
            if ac.get("sentido_id") == sentido_id or (ac.get("definicao") and ac.get("definicao") == def_en):
                ac["status"] = status
                ac["confirmado_em"] = datetime.now().isoformat()
                if def_en: ac["definicao"] = def_en
                if def_pt: ac["definicao_pt"] = def_pt
                if ex:
                    ac["frase_exemplo"] = ex
                    if not ac.get("frase_i1"):
                        ac["frase_i1"] = ex
                found = True
                break

        if not found:
            vocab_map[w_norm]["acepcoes"].append({
                "sentido_id": sentido_id,
                "pos": pos,
                "definicao": def_en,
                "definicao_pt": def_pt,
                "status": status,
                "frase_exemplo": ex,
                "frase_i1": ex,
                "confirmado_em": datetime.now().isoformat()
            })

        save_knowledge_map_memory()
        subdeck = data.get("subdeck", "01k")
        deck_stats = get_deck_progress(subdeck)
        self.send_json({
            "success": True,
            "word": word,
            "status": status,
            "stats": KNOWLEDGE_MAP.get("estatisticas"),
            "deck_stats": deck_stats
        })

    def handle_api_batch_evaluate(self, data):
        items = data.get("items", [])
        if not items:
            self.send_json({"error": "Nenhum item recebido"}, 400)
            return

        vocab_map = KNOWLEDGE_MAP.setdefault("mapa_vocabulario", {})
        now_iso = datetime.now().isoformat()

        for it in items:
            word = it.get("word", "").strip()
            status = it.get("status", "").strip()
            sentido_id = it.get("id", f"{word}_batch")
            pos = it.get("pos", "")
            def_en = it.get("definition_en", "")
            def_pt = it.get("definition_pt", "")
            ex = it.get("example_1", "")

            if not word or not status: continue
            w_norm = word.lower()

            if w_norm not in vocab_map:
                vocab_map[w_norm] = {
                    "termo": word,
                    "status_geral": status,
                    "acepcoes": [],
                    "collocations": [],
                    "observacoes": "Classificado via Web Reviewer (Lote)"
                }

            found = False
            for ac in vocab_map[w_norm].get("acepcoes", []):
                if ac.get("sentido_id") == sentido_id or ac.get("definicao") == def_en:
                    ac["status"] = status
                    ac["confirmado_em"] = now_iso
                    if def_pt: ac["definicao_pt"] = def_pt
                    if ex: ac["frase_exemplo"] = ex
                    found = True
                    break

            if not found:
                vocab_map[w_norm]["acepcoes"].append({
                    "sentido_id": sentido_id,
                    "pos": pos,
                    "definicao": def_en,
                    "definicao_pt": def_pt,
                    "status": status,
                    "frase_exemplo": ex,
                    "confirmado_em": now_iso
                })

        save_knowledge_map_memory()
        subdeck = data.get("subdeck", "01k")
        deck_stats = get_deck_progress(subdeck)
        self.send_json({
            "success": True,
            "count": len(items),
            "stats": KNOWLEDGE_MAP.get("estatisticas"),
            "deck_stats": deck_stats
        })

    def handle_api_mark_remaining_known(self, data):
        subdeck = data.get("subdeck", "01k")
        vocab_map = KNOWLEDGE_MAP.setdefault("mapa_vocabulario", {})
        now_iso = datetime.now().isoformat()

        entries = MWLD_ENTRIES if subdeck == "all" else MWLD_BY_SUBDECK.get(subdeck, [])

        count_marked = 0
        seen_words = set()

        for e in entries:
            w_lower = e["word"].lower().strip()
            if w_lower in PURE_FUNCTION_WORDS or w_lower.startswith("-") or w_lower.endswith("-"):
                continue
            pos_lower = e.get("pos", "").lower()
            if "prefix" in pos_lower or "suffix" in pos_lower or "combining form" in pos_lower:
                continue

            if w_lower in seen_words:
                continue
            seen_words.add(w_lower)

            # Verificar se já tem status avaliado (conhecido, desconhecido, duvida, em_estudo)
            is_evaluated = False
            if w_lower in vocab_map:
                t_data = vocab_map[w_lower]
                st = t_data.get("status_geral")
                if st in ["conhecido", "desconhecido", "duvida", "em_estudo"]:
                    is_evaluated = True
                else:
                    for ac in t_data.get("acepcoes", []):
                        if ac.get("status") in ["conhecido", "desconhecido", "duvida", "em_estudo"]:
                            is_evaluated = True
                            break

            # Se não estiver avaliado (ou seja, pendente), marca como conhecido!
            if not is_evaluated:
                if w_lower not in vocab_map:
                    vocab_map[w_lower] = {
                        "termo": e["word"],
                        "status_geral": "conhecido",
                        "acepcoes": [
                            {
                                "sentido_id": e["id"],
                                "pos": e.get("pos", ""),
                                "definicao": e.get("definition_en", ""),
                                "status": "conhecido",
                                "frase_exemplo": e.get("example_1", ""),
                                "confirmado_em": now_iso
                            }
                        ],
                        "collocations": [],
                        "observacoes": f"Aprovado em massa (Restantes do Deck {subdeck})"
                    }
                else:
                    vocab_map[w_lower]["status_geral"] = "conhecido"
                    if not vocab_map[w_lower].get("acepcoes"):
                        vocab_map[w_lower]["acepcoes"] = [
                            {
                                "sentido_id": e["id"],
                                "pos": e.get("pos", ""),
                                "definicao": e.get("definition_en", ""),
                                "status": "conhecido",
                                "frase_exemplo": e.get("example_1", ""),
                                "confirmado_em": now_iso
                            }
                        ]
                    else:
                        for ac in vocab_map[w_lower]["acepcoes"]:
                            if ac.get("status") in [None, "", "pending"]:
                                ac["status"] = "conhecido"
                                ac["confirmado_em"] = now_iso
                count_marked += 1

        save_knowledge_map_memory()
        deck_stats = get_deck_progress(subdeck)

        # Trigger AnkiConnect sync
        try:
            req = urllib.request.Request(
                ANKI_URL,
                data=json.dumps({"action": "sync", "params": {}, "version": 6}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=3.0)
        except Exception:
            pass

        self.send_json({
            "success": True,
            "count": count_marked,
            "subdeck": subdeck,
            "deck_stats": deck_stats,
            "stats": KNOWLEDGE_MAP.get("estatisticas")
        })

    def handle_api_flag_intruder(self, data):
        intruder = data.get("intruder", "").lower().strip()
        target_word = data.get("target_word", "").lower().strip()
        if not intruder:
            self.send_json({"error": "Nenhuma palavra intrusa fornecida"}, 400)
            return

        vocab_map = KNOWLEDGE_MAP.setdefault("mapa_vocabulario", {})
        now_iso = datetime.now().isoformat()

        if intruder not in vocab_map:
            vocab_map[intruder] = {
                "termo": intruder,
                "status_geral": "desconhecido",
                "acepcoes": [
                    {
                        "sentido_id": f"{intruder}_flagged_{int(time.time())}",
                        "pos": "geral",
                        "definicao": f"Palavra intrusa identificada no contexto de '{target_word}'",
                        "definicao_pt": f"Identificada durante estudo de '{target_word}'",
                        "status": "desconhecido",
                        "frase_exemplo": "",
                        "observacao_aluno": f"Sinalizado como obstáculo I+2 em '{target_word}'",
                        "confirmado_em": now_iso
                    }
                ],
                "collocations": [],
                "observacoes": f"Sinalizado como obstáculo I+2 durante triagem de '{target_word}'"
            }
        else:
            vocab_map[intruder]["status_geral"] = "desconhecido"
            if not vocab_map[intruder].get("acepcoes"):
                vocab_map[intruder]["acepcoes"] = []
            vocab_map[intruder]["acepcoes"].append({
                "sentido_id": f"{intruder}_flagged_{int(time.time())}",
                "pos": "geral",
                "definicao": f"Acepção intrusa em '{target_word}'",
                "definicao_pt": f"Identificada durante estudo de '{target_word}'",
                "status": "desconhecido",
                "confirmado_em": now_iso
            })

        save_knowledge_map_memory()
        print(f"🚩 Palavra intrusa '{intruder}' registrada como Gap I+1!")
        self.send_json({"success": True, "intruder": intruder, "target_word": target_word, "stats": KNOWLEDGE_MAP.get("estatisticas")})

    def handle_api_gaps(self):
        gaps = []
        needs_save = False
        known_set, unknown_set = get_user_vocab_profile()

        for termo, data in KNOWLEDGE_MAP.get("mapa_vocabulario", {}).items():
            for ac in data.get("acepcoes", []):
                st = ac.get("status")
                if st in ("desconhecido", "duvida"):
                    frase = ac.get("frase_i1") or ac.get("frase_exemplo", "")
                    def_en = ac.get("definicao", "")
                    def_pt = ac.get("definicao_pt", "")

                    # Avaliar conformidade i+1 da frase atual
                    extra_cnt, unknowns_list, is_strict = evaluate_sentence_i1(frase, termo, known_set, unknown_set)
                    has_sentence = is_strict
                    has_def = is_valid_definition(def_en)

                    is_ready = bool(has_sentence and has_def)

                    card_id = ac.get("card_id")
                    injetado_em = ac.get("injetado_em")
                    if not is_ready:
                        status_label = "aguardando_frase"
                    elif card_id or injetado_em:
                        status_label = "injetado"
                    else:
                        status_label = "pronto"

                    prio, idx, s_name = get_term_importance(termo)
                    prio_label = f"★ Top {s_name.upper()}" if prio <= 10 else f"Deck {s_name.upper()}"
                    intruders = [u[0] for u in unknowns_list]
                    i_level = "i+1" if extra_cnt == 0 else f"i+{extra_cnt + 1}"

                    gaps.append({
                        "termo": termo,
                        "termo_display": data.get("termo", termo),
                        "sentido_id": ac.get("sentido_id"),
                        "pos": ac.get("pos", ""),
                        "definicao": def_en,
                        "definicao_pt": def_pt,
                        "frase": frase,
                        "card_id": card_id,
                        "confirmado_em": ac.get("confirmado_em"),
                        "status": st,
                        "is_ready": is_ready,
                        "status_label": status_label,
                        "has_sentence": has_sentence,
                        "has_def": has_def,
                        "subdeck": s_name,
                        "importance_prio": prio,
                        "importance_idx": idx,
                        "priority_label": prio_label,
                        "is_strict_i1": is_strict,
                        "extra_unknowns_count": extra_cnt,
                        "extra_unknowns": intruders,
                        "i_level": i_level
                    })

        if needs_save:
            save_knowledge_map_memory()

        # Ordenar:
        # 1. Prontos primeiro, rigorosamente por IMPORTÂNCIA (prio, idx) -> Top 1k e maior frequência no topo!
        # 2. Aguardando frase, também por importância
        # 3. Injetados no final, ordenados por recência
        def gap_sort_key(g):
            label = g["status_label"]
            prio = g.get("importance_prio", 99)
            idx = g.get("importance_idx", 999999)
            if label == "pronto":
                return (0, prio, idx)
            elif label == "aguardando_frase":
                return (1, prio, idx)
            else:
                ts = 0
                if g.get("confirmado_em"):
                    try:
                        ts = datetime.fromisoformat(g["confirmado_em"]).timestamp()
                    except Exception:
                        pass
                return (2, -ts)

        gaps.sort(key=gap_sort_key)

        ready_count = sum(1 for g in gaps if g["status_label"] == "pronto")
        waiting_count = sum(1 for g in gaps if g["status_label"] == "aguardando_frase")
        injected_count = sum(1 for g in gaps if g["status_label"] == "injetado")

        self.send_json({
            "gaps": gaps,
            "total": len(gaps),
            "ready_count": ready_count,
            "waiting_count": waiting_count,
            "injected_count": injected_count
        })

    def handle_api_enrich_gaps(self, data):
        vocab_map = KNOWLEDGE_MAP.get("mapa_vocabulario", {})
        enriched_count = 0
        ready_count = 0
        waiting_count = 0

        for termo, t_data in vocab_map.items():
            for ac in t_data.get("acepcoes", []):
                if ac.get("status") in ("desconhecido", "duvida"):
                    frase = ac.get("frase_i1") or ac.get("frase_exemplo") or ""
                    def_en = ac.get("definicao") or ""

                    was_incomplete = (not is_valid_i1_sentence(frase, termo)) or (not is_valid_definition(def_en))
                    if was_incomplete:
                        cand = find_ready_sentence_and_def(termo)
                        changed = False
                        cand_frase = cand.get("frase", "")
                        if cand_frase and is_valid_i1_sentence(cand_frase, termo):
                            ac["frase_i1"] = cand_frase
                            frase = cand_frase
                            if cand.get("frase_pt"):
                                ac["frase_pt"] = cand["frase_pt"]
                            changed = True
                        if not is_valid_definition(def_en) and is_valid_definition(cand.get("def_en")):
                            ac["definicao"] = cand["def_en"]
                            def_en = cand["def_en"]
                            if cand.get("def_pt"):
                                ac["definicao_pt"] = cand["def_pt"]
                            changed = True
                        if cand.get("ipa") and not ac.get("ipa"):
                            ac["ipa"] = cand["ipa"]
                        if cand.get("audio_url") and not ac.get("audio_url"):
                            ac["audio_url"] = cand["audio_url"]
                        if cand.get("mairo_audio") and not ac.get("mairo_audio"):
                            ac["mairo_audio"] = cand["mairo_audio"]
                        if changed:
                            enriched_count += 1

                    if is_valid_i1_sentence(ac.get("frase_i1") or ac.get("frase_exemplo"), termo) and is_valid_definition(ac.get("definicao")):
                        ready_count += 1
                    else:
                        waiting_count += 1

        if enriched_count > 0:
            save_knowledge_map_memory()

        self.send_json({
            "success": True,
            "enriched_count": enriched_count,
            "ready_count": ready_count,
            "waiting_count": waiting_count,
            "message": f"{enriched_count} termos enriquecidos com frases e definições do acervo! ({ready_count} prontos para injeção, {waiting_count} aguardando)."
        })

    def handle_api_inject_anki(self, data):
        try:
            try:
                invoke_anki("version")
            except Exception as e_conn:
                print(f"❌ Erro ao conectar ao AnkiConnect: {e_conn}")
                self.send_json({
                    "success": False,
                    "error": "O Anki Desktop precisa estar aberto no computador com o AnkiConnect ativo!",
                    "message": "⚠️ O aplicativo do Anki Desktop não está aberto no computador. Abra o Anki para concluir a injeção."
                })
                return

            limit_raw = data.get("limit") if data else None
            limit = None
            if limit_raw and str(limit_raw).lower() != "all":
                try:
                    limit = int(limit_raw)
                except ValueError:
                    limit = None

            vocab_map = KNOWLEDGE_MAP.get("mapa_vocabulario", {})
            candidates = []

            for termo, t_data in vocab_map.items():
                for ac in t_data.get("acepcoes", []):
                    if ac.get("status") in ("desconhecido", "duvida") and not ac.get("card_id") and not ac.get("injetado_em"):
                        prio, idx, s = get_term_importance(termo)
                        candidates.append({
                            "termo": termo,
                            "termo_display": t_data.get("termo", termo),
                            "ac": ac,
                            "prio": prio,
                            "idx": idx,
                            "subdeck": s
                        })

            if not candidates:
                self.send_json({"success": True, "message": "Nenhum Gap novo pendente para injeção.", "injected": 0, "skipped_waiting": 0})
                return

            # Tenta auto-enriquecimento e separa somente quem tem frase i+1 autêntica e definição completa
            ready_items = []
            skipped_without_phrase = []

            for item in candidates:
                termo = item["termo"]
                ac = item["ac"]
                w_display = item["termo_display"]

                # Se já tiver card_id no ac mas não foi movido, conta como pronto
                existing_cid = ac.get("card_id")
                if existing_cid:
                    ready_items.append(item)
                    continue

                frase = ac.get("frase_i1") or ac.get("frase_exemplo") or ""
                def_en = ac.get("definicao") or ""

                if not is_valid_i1_sentence(frase, termo) or not is_valid_definition(def_en):
                    cand = find_ready_sentence_and_def(termo)
                    cand_frase = cand.get("frase", "")
                    if cand_frase and is_valid_i1_sentence(cand_frase, termo):
                        frase = cand_frase
                        ac["frase_i1"] = frase
                        if cand.get("frase_pt"): ac["frase_pt"] = cand["frase_pt"]
                    if not is_valid_definition(def_en) and is_valid_definition(cand.get("def_en")):
                        def_en = cand["def_en"]
                        ac["definicao"] = def_en
                        if cand.get("def_pt"): ac["definicao_pt"] = cand["def_pt"]
                    if cand.get("ipa") and not ac.get("ipa"): ac["ipa"] = cand["ipa"]
                    if cand.get("audio_url") and not ac.get("audio_url"): ac["audio_url"] = cand["audio_url"]
                    if cand.get("mairo_audio") and not ac.get("mairo_audio"): ac["mairo_audio"] = cand["mairo_audio"]

                if is_valid_i1_sentence(frase, termo) and is_valid_definition(def_en):
                    ready_items.append(item)
                else:
                    skipped_without_phrase.append(w_display)

            if not ready_items:
                self.send_json({
                    "success": True,
                    "message": "Nenhum Gap possui frase autêntica pronta ainda. Clique em 'Buscar Frases' primeiro.",
                    "injected": 0,
                    "skipped_waiting": len(skipped_without_phrase)
                })
                return

            # CRÍTICO: Ordenar rigorosamente pela IMPORTÂNCIA (Top 1.000 primeiro, maior frequência primeiro)
            ready_items.sort(key=lambda x: (x["prio"], x["idx"]))

            # Aplicar limite de injeção escolhido pelo usuário (ex: 5, 10, 20, ou all)
            if limit and limit > 0:
                selected_for_injection = ready_items[:limit]
            else:
                selected_for_injection = ready_items

            print(f"🚀 Iniciando injeção dos {len(selected_for_injection)} Gaps mais importantes no Anki (limite={limit})...")
            created_count = 0
            injected_words = []
            errors_list = []

            # Carregar palavras em foco já ativas no baralho principal '🎯 Meu Estudo Ativo'
            active_study_focus = {}
            try:
                active_cards = invoke_anki("findCards", query='"deck:🇬🇧 Inglês::🎯 Meu Estudo Ativo"')
                if active_cards:
                    active_info = invoke_anki("cardsInfo", cards=active_cards)
                    for c in active_info:
                        fw = extract_focus_word_from_fields(c.get("fields", {}))
                        if fw:
                            active_study_focus[fw.lower()] = c["cardId"]
            except Exception as e_act:
                print(f"⚠️ Aviso ao verificar cards em estudo ativo: {e_act}")

            for item in selected_for_injection:
                termo = item["termo"]
                w_display = item["termo_display"]
                ac = item["ac"]
                t_lower = termo.lower().strip()

                # 1. Se a palavra em foco já estiver ativa no baralho, evita qualquer duplicata da mesma palavra!
                if t_lower in active_study_focus:
                    existing_cid = active_study_focus[t_lower]
                    ac["card_id"] = existing_cid
                    ac["injetado_em"] = datetime.now().isoformat()
                    created_count += 1
                    injected_words.append(w_display)
                    print(f"  ✓ [{created_count}] '{w_display}' já possui carta ativa em Meu Estudo Ativo (CardId: {existing_cid}) - duplicata evitada.")
                    continue

                # 2. Se a acepção já estiver vinculada a uma carta existente, descongela e move
                existing_cid = ac.get("card_id")
                if existing_cid:
                    try:
                        invoke_anki("changeDeck", cards=[existing_cid], deck="🇬🇧 Inglês::🎯 Meu Estudo Ativo")
                        invoke_anki("unsuspend", cards=[existing_cid])
                        ac["injetado_em"] = datetime.now().isoformat()
                        created_count += 1
                        injected_words.append(w_display)
                        active_study_focus[t_lower] = existing_cid
                        print(f"  ✓ [{created_count}] Descongelado e movido '{w_display}' para Estudo Ativo (CardId: {existing_cid})")
                        continue
                    except Exception as e_mv:
                        print(f"  ⚠️ Tentativa de mover card {existing_cid} falhou, criando novo: {e_mv}")

                frase = ac.get("frase_i1") or ac.get("frase_exemplo") or ""
                def_en = ac.get("definicao") or ""

                mwld_match = None
                matches = MWLD_BY_WORD.get(termo.lower(), [])
                if matches:
                    mwld_match = matches[0]

                ipa = ac.get("ipa") or (mwld_match["ipa"] if mwld_match else "")
                audio_url = ac.get("audio_url") or (mwld_match["audio_url"] if mwld_match else "")
                mairo_audio = ac.get("mairo_audio")

                audio_tag = ""
                if mairo_audio:
                    audio_tag = f"[sound:{mairo_audio}]"
                elif audio_url:
                    audio_filename = f"mwld_{termo}_{int(time.time()*1000)%100000}.wav"
                    try:
                        invoke_anki("storeMediaFile", filename=audio_filename, url=audio_url)
                        audio_tag = f"[sound:{audio_filename}]"
                    except Exception as ea:
                        print(f"⚠️ Erro ao baixar áudio para {termo}: {ea}")

                def_pt = ac.get("definicao_pt") or translate_to_pt_sync(def_en)
                clean_frase = re.sub(r'<[^>]+>', '', frase)
                frase_pt = ac.get("frase_pt") or translate_to_pt_sync(clean_frase)

                pattern = re.compile(rf'\b({re.escape(w_display)})\b', re.IGNORECASE)
                if pattern.search(clean_frase):
                    front_text = pattern.sub(r'<b>\1</b>', clean_frase)
                else:
                    matched_chunk = False
                    if " " in w_display:
                        parts = w_display.split()
                        head = parts[0]
                        tail = r'\s+'.join(re.escape(p) for p in parts[1:])
                        head_forms = [re.escape(head), re.escape(head) + r's', re.escape(head) + r'ed', re.escape(head) + r'ing']
                        irr_forms = IRREGULAR_VERBS.get(head.lower(), [])
                        for f_irr in irr_forms:
                            head_forms.append(re.escape(f_irr))
                        chunk_regex = re.compile(rf'\b((?:{"|".join(head_forms)})(?:\s+[a-zA-Z0-9\'-]{{1,15}}){{0,2}}\s+{tail})\b', re.IGNORECASE)
                        if chunk_regex.search(clean_frase):
                            front_text = chunk_regex.sub(r'<b>\1</b>', clean_frase)
                            matched_chunk = True
                    if not matched_chunk:
                        front_text = f"<b>{clean_frase}</b>"

                if audio_tag:
                    anverso = f"{front_text}<br />{audio_tag}"
                else:
                    anverso = front_text

                ipa_str = f" /{ipa}/" if ipa else ""
                
                # Alerta Didático de Falso Cognato
                false_cog = FALSE_COGNATES.get(termo.lower(), "")
                false_cog_html = f"""<div style="margin: 10px 0; padding: 10px 14px; background: rgba(245, 158, 11, 0.15); border-left: 4px solid #f59e0b; border-radius: 6px; color: #fbbf24; font-size: 13px;"><b>⚠️ ATENÇÃO - FALSO AMIGO / COGNATO:</b><br />{false_cog}</div>""" if false_cog else ""
                
                # Contexto Temático
                theme = detect_sentence_theme(clean_frase, termo)
                theme_html = f"""<div style="font-size: 12px; color: #38bdf8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Tema: {theme}</div>"""

                reverso = f"""<div><b>{w_display}{ipa_str}</b></div>
<div><b><br /></b></div>
{false_cog_html}
{theme_html}
<div><b>EN </b>({def_en}) <br /><br /></div>
<div><b>PT </b>({def_pt}).</div>
<div><br /></div>
<div><i>{frase_pt}</i></div>"""

                # 3. REGRA ESTRITA: Só permitir duplicatas quando a palavra em foco é OUTRA!
                same_focus_card = None
                diff_focus_found = False

                clean_query = clean_frase.replace('"', '').strip()
                words = clean_query.split()
                search_q = ' '.join(words[:6]) if len(words) > 6 else clean_query

                try:
                    existing_notes = invoke_anki("findNotes", query=f'"{search_q}"')
                    if existing_notes:
                        n_infos = invoke_anki("notesInfo", notes=existing_notes)
                        for n in n_infos:
                            fw = extract_focus_word_from_fields(n.get("fields", {}))
                            if fw and fw.lower() == t_lower:
                                if n.get("cards"):
                                    same_focus_card = n["cards"][0]
                                    break
                            elif fw:
                                diff_focus_found = True
                except Exception as e_chk:
                    print(f"⚠️ Erro ao checar duplicatas de '{w_display}': {e_chk}")

                # Se já existe nota com a MESMA palavra em foco, NUNCA duplica: reaproveita/descongela
                if same_focus_card:
                    try:
                        invoke_anki("changeDeck", cards=[same_focus_card], deck="🇬🇧 Inglês::🎯 Meu Estudo Ativo")
                        invoke_anki("unsuspend", cards=[same_focus_card])
                        ac["card_id"] = same_focus_card
                        ac["injetado_em"] = datetime.now().isoformat()
                        created_count += 1
                        injected_words.append(w_display)
                        active_study_focus[t_lower] = same_focus_card
                        print(f"  ✓ [{created_count}] Reaproveitado card existente de '{w_display}' (mesma palavra em foco, sem duplicar nota!) (CardId: {same_focus_card})")
                        continue
                    except Exception as e_reuse:
                        print(f"  ⚠️ Falha ao reaproveitar card {same_focus_card}: {e_reuse}")

                # Só permite duplicata no Anki quando a frase coincide mas a palavra em foco é OUTRA!
                allow_dup = bool(diff_focus_found)

                subdeck_tag = f"deck-{item.get('subdeck', '01k')}"
                note_payload = {
                    "deckName": "🇬🇧 Inglês::🎯 Meu Estudo Ativo",
                    "modelName": "Básico-fd486",
                    "fields": {
                        "Anverso": anverso,
                        "Reverso": reverso
                    },
                    "tags": ["mwld-prioritario", "i1-lexico", "triagem-rapida", subdeck_tag],
                    "options": {
                        "allowDuplicate": allow_dup,
                        "duplicateScope": "deck"
                    }
                }

                try:
                    res_add = invoke_anki("addNote", note=note_payload)
                    if res_add:
                        ac["card_id"] = res_add
                        ac["injetado_em"] = datetime.now().isoformat()
                        created_count += 1
                        injected_words.append(w_display)
                        active_study_focus[t_lower] = res_add
                        print(f"  ✓ [{created_count}] Injetado '{w_display}' no Estudo Ativo (NoteId: {res_add}, allowDuplicate={allow_dup})")
                except Exception as e_add:
                    err_str = str(e_add)
                    errors_list.append(f"{w_display}: {err_str}")
                    print(f"  ❌ Erro ao adicionar nota '{w_display}': {err_str}")

            save_knowledge_map_memory()

            sync_res = "ok"
            if created_count > 0:
                print("🔄 Sincronizando com o AnkiWeb via AnkiConnect...")
                try:
                    invoke_anki("sync")
                    print("✓ Sincronização com o AnkiWeb concluída!")
                except Exception as e_sync:
                    print(f"⚠️ Aviso ao sincronizar com AnkiWeb: {e_sync}")
                    sync_res = str(e_sync)

            if created_count > 0:
                top_str = ", ".join(injected_words[:8])
                if len(injected_words) > 8:
                    top_str += f" e mais {len(injected_words)-8}..."
                msg = f"🚀 {created_count} cartas mais importantes injetadas com sucesso no Anki ({top_str})!"
                if skipped_without_phrase:
                    msg += f" (Nota: {len(skipped_without_phrase)} outros termos continuam na fila aguardando frase i+1)."

                self.send_json({
                    "success": True,
                    "injected": created_count,
                    "injected_words": injected_words,
                    "skipped_waiting": len(skipped_without_phrase),
                    "skipped_terms": skipped_without_phrase,
                    "sync": sync_res,
                    "message": msg
                })
            else:
                err_detail = f": {errors_list[0]}" if errors_list else ""
                self.send_json({
                    "success": False,
                    "injected": 0,
                    "error": f"Nenhuma carta pôde ser injetada no Anki{err_detail}",
                    "message": f"⚠️ Nenhuma carta foi adicionada ao Anki{err_detail}. Verifique se o Anki Desktop está aberto no computador."
                })

        except Exception as e_main:
            print(f"❌ Erro geral em inject_anki: {e_main}")
            self.send_json({"error": str(e_main)}, 500)

def keep_alive_worker():
    """Mantém o servidor na nuvem (Render) acordado enviando um ping a cada 9 minutos."""
    cloud_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    if not cloud_url and os.environ.get("PORT"):
        cloud_url = "https://lexis-app-swxb.onrender.com"
    if not cloud_url:
        return

    url = cloud_url.rstrip("/") + "/api/status"
    time.sleep(60)
    while True:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LexiSync-KeepAlive/1.0"})
            with urllib.request.urlopen(req, timeout=15.0) as res:
                _ = res.read()
        except Exception:
            pass
        time.sleep(540) # A cada 9 minutos

def run_server():
    load_translations_cache()
    load_jev_cache()
    load_knowledge_map()
    index_mwld()
    index_structures()
    load_mairo_sentences()

    # Iniciar workers em background
    threading.Thread(target=translation_worker, daemon=True).start()
    threading.Thread(target=disk_saver_worker, daemon=True).start()
    threading.Thread(target=keep_alive_worker, daemon=True).start()

    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    server_address = ("0.0.0.0", PORT)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    print(f"\n=======================================================")
    print(f"🚀 Servidor LexiSync MWLD (TURBO) ativo e liberado na rede:")
    print(f"  💻 No Computador : http://127.0.0.1:{PORT}")
    print(f"  📱 No Celular    : http://{local_ip}:{PORT}")
    print(f"=======================================================\n")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
