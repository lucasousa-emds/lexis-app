#!/usr/bin/env python3
"""
media_miner.py — Motor de Mineração Lexical & Cobertura 95% para Mídias Reais
Suporta .epub (com capítulos), .srt, .vtt, .txt e texto colado usando apenas stdlib Python.
Cruza a obra com MWLD, Phrasal Verbs, Idioms, Collocations e knowledge_map_english.json.
"""

import base64
import io
import json
import os
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser


IRREGULAR_LEMMAS = {
    "was": "be", "were": "be", "been": "be", "am": "be", "is": "be", "are": "be",
    "had": "have", "has": "have", "having": "have",
    "did": "do", "does": "do", "done": "do", "doing": "do",
    "went": "go", "gone": "go", "goes": "go", "going": "go",
    "said": "say", "says": "say", "saying": "say",
    "made": "make", "makes": "make", "making": "make",
    "took": "take", "taken": "take", "takes": "take", "taking": "take",
    "came": "come", "comes": "come", "coming": "come",
    "saw": "see", "seen": "see", "sees": "see", "seeing": "see",
    "knew": "know", "known": "know", "knows": "know", "knowing": "know",
    "got": "get", "gotten": "get", "gets": "get", "getting": "get",
    "gave": "give", "given": "give", "gives": "give", "giving": "give",
    "found": "find", "finds": "find", "finding": "find",
    "thought": "think", "thinks": "think", "thinking": "think",
    "told": "tell", "tells": "tell", "telling": "tell",
    "became": "become", "becomes": "become", "becoming": "become",
    "left": "leave", "leaves": "leave", "leaving": "leave",
    "felt": "feel", "feels": "feel", "feeling": "feel",
    "brought": "bring", "brings": "bring", "bringing": "bring",
    "began": "begin", "begun": "begin", "begins": "begin", "beginning": "begin",
    "kept": "keep", "keeps": "keep", "keeping": "keep",
    "held": "hold", "holds": "hold", "holding": "hold",
    "wrote": "write", "written": "write", "writes": "write", "writing": "write",
    "stood": "stand", "stands": "stand", "standing": "stand",
    "heard": "hear", "hears": "hear", "hearing": "hear",
    "meant": "mean", "means": "mean", "meaning": "mean",
    "met": "meet", "meets": "meet", "meeting": "meet",
    "ran": "run", "runs": "run", "running": "run",
    "paid": "pay", "pays": "pay", "paying": "pay",
    "sat": "sit", "sits": "sit", "sitting": "sit",
    "spoke": "speak", "spoken": "speak", "speaks": "speak", "speaking": "speak",
    "lay": "lie", "lain": "lie", "lying": "lie",
    "led": "lead", "leads": "lead", "leading": "lead",
    "grew": "grow", "grown": "grow", "grows": "grow", "growing": "grow",
    "lost": "lose", "loses": "lose", "losing": "lose",
    "fell": "fall", "fallen": "fall", "falls": "fall", "falling": "fall",
    "sent": "send", "sends": "send", "sending": "send",
    "built": "build", "builds": "build", "building": "build",
    "understood": "understand", "understands": "understand",
    "drew": "draw", "drawn": "draw", "draws": "draw", "drawing": "draw",
    "broke": "break", "broken": "break", "breaks": "break", "breaking": "break",
    "spent": "spend", "spends": "spend", "spending": "spend",
    "rose": "rise", "risen": "rise", "rises": "rise", "rising": "rise",
    "drove": "drive", "driven": "drive", "drives": "drive", "driving": "drive",
    "bought": "buy", "buys": "buy", "buying": "buy",
    "wore": "wear", "worn": "wear", "wears": "wear", "wearing": "wear",
    "chose": "choose", "chosen": "choose", "chooses": "choose", "choosing": "choose",
    "caught": "catch", "catches": "catch", "catching": "catch",
    "taught": "teach", "teaches": "teach", "teaching": "teach",
    "fought": "fight", "fights": "fight", "fighting": "fight",
    "flew": "fly", "flown": "fly", "flies": "fly", "flying": "fly",
    "threw": "throw", "thrown": "throw", "throws": "throw", "throwing": "throw",
    "shook": "shake", "shaken": "shake", "shakes": "shake", "shaking": "shake",
    "woke": "wake", "woken": "wake", "wakes": "wake", "waking": "wake",
    "slept": "sleep", "sleeps": "sleep", "sleeping": "sleep",
    "swept": "sweep", "crept": "creep", "wept": "weep", "leapt": "leap",
    "struck": "strike", "strikes": "strike", "striking": "strike",
    "stuck": "stick", "sticks": "stick", "sticking": "stick",
    "hung": "hang", "dug": "dig", "swung": "swing", "flung": "fling",
    "hid": "hide", "hidden": "hide", "bit": "bite", "bitten": "bite",
    "ate": "eat", "eaten": "eat", "drank": "drink", "drunk": "drink",
    "sang": "sing", "sung": "sing", "sank": "sink", "sunk": "sink",
    "swam": "swim", "swum": "swim", "rang": "ring", "rung": "ring",
    "blew": "blow", "blown": "blow", "froze": "freeze", "frozen": "freeze",
    "stole": "steal", "stolen": "steal", "tore": "tear", "torn": "tear",
    "swore": "swear", "sworn": "swear", "forgave": "forgive", "forgiven": "forgive",
    "forgot": "forget", "forgotten": "forget", "forbade": "forbid", "forbidden": "forbid",
    "shone": "shine", "shot": "shoot", "rode": "ride", "ridden": "ride",
    "dealt": "deal", "knelt": "kneel", "bent": "bend", "lent": "lend",
    "burnt": "burn", "learnt": "learn", "dreamt": "dream", "meant": "mean",
    "children": "child", "men": "man", "women": "woman", "people": "person",
    "feet": "foot", "teeth": "tooth", "mice": "mouse", "lives": "life",
    "knives": "knife", "wolves": "wolf", "leaves": "leaf", "halves": "half",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
}

EXTRA_STOPWORDS = {
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "mine", "yours", "hers", "ours", "theirs",
    "this", "that", "these", "those", "who", "whom", "whose", "which", "what",
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "while",
    "as", "at", "by", "for", "from", "in", "into", "of", "off", "on", "onto", "out",
    "over", "to", "up", "with", "about", "after", "before", "between", "through",
    "under", "again", "further", "once", "here", "there", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "don", "dont", "should", "now", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "would", "could", "shall", "may",
    "might", "must", "yes", "oh", "ah", "well", "ok", "okay", "hey", "hi", "hello",
    "mr", "mrs", "ms", "dr", "st", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "first", "second", "third", "ll", "ve", "re", "d", "s", "t", "m"
}


class _HTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "tr"}
    SKIP_TAGS = {"script", "style", "head", "title", "nav"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._in_heading = False
        self.headings = []
        self._cur_heading = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0:
            if t in ("h1", "h2", "h3"):
                self._in_heading = True
                self._cur_heading = []
            if t in self.BLOCK_TAGS:
                self.parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif self._skip_depth == 0:
            if t in ("h1", "h2", "h3") and self._in_heading:
                h_txt = " ".join("".join(self._cur_heading).split()).strip()
                if h_txt:
                    self.headings.append(h_txt)
                self._in_heading = False
            if t in self.BLOCK_TAGS:
                self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.parts.append(data)
            if self._in_heading:
                self._cur_heading.append(data)

    def get_text(self):
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def slugify_title(title: str) -> str:
    norm = unicodedata.normalize("NFKD", (title or "midia").strip().lower())
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return (slug[:42] or "midia")


def clean_subtitle_text(raw_text: str) -> str:
    """Converte .srt ou .vtt em texto corrido limpo preservando frases."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^WEBVTT.*?\n\n", "", text, flags=re.IGNORECASE | re.DOTALL)
    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if re.match(r"^\d+$", s):
            continue
        if "-->" in s:
            continue
        if s.upper().startswith(("NOTE", "STYLE", "REGION")):
            continue
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"\{\\[^}]+\}", "", s)
        s = re.sub(r"\[[^\]]*\]", "", s)
        s = s.strip()
        if s:
            lines.append(s)
    joined = " ".join(lines)
    joined = re.sub(r"\s{2,}", " ", joined)
    return joined.strip()


def extract_epub_chapters(raw_bytes: bytes):
    """Extrai capítulos em ordem de leitura (spine) de um arquivo .epub usando apenas stdlib."""
    chapters = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
        names = set(zf.namelist())
        opf_path = None
        if "META-INF/container.xml" in names:
            try:
                c_root = ET.fromstring(zf.read("META-INF/container.xml"))
                for elem in c_root.iter():
                    if elem.tag.endswith("rootfile") and elem.attrib.get("full-path"):
                        opf_path = elem.attrib["full-path"]
                        break
            except Exception:
                opf_path = None

        ordered_hrefs = []
        if opf_path and opf_path in names:
            try:
                opf_dir = os.path.dirname(opf_path)
                opf_root = ET.fromstring(zf.read(opf_path))
                manifest = {}
                for elem in opf_root.iter():
                    if elem.tag.endswith("item") and elem.attrib.get("id") and elem.attrib.get("href"):
                        manifest[elem.attrib["id"]] = elem.attrib["href"]
                for elem in opf_root.iter():
                    if elem.tag.endswith("itemref") and elem.attrib.get("idref"):
                        href = manifest.get(elem.attrib["idref"])
                        if href:
                            full = f"{opf_dir}/{href}" if opf_dir else href
                            full = full.replace("\\", "/")
                            ordered_hrefs.append(full)
            except Exception:
                ordered_hrefs = []

        if not ordered_hrefs:
            ordered_hrefs = sorted(
                n for n in names
                if n.lower().endswith((".xhtml", ".html", ".htm")) and "toc" not in n.lower()
            )

        idx = 0
        for href in ordered_hrefs:
            target = href if href in names else None
            if not target:
                continue
            try:
                html_raw = zf.read(target).decode("utf-8", errors="ignore")
            except Exception:
                continue
            parser = _HTMLTextExtractor()
            try:
                parser.feed(html_raw)
            except Exception:
                continue
            txt = parser.get_text()
            wc = len(re.findall(r"[A-Za-z]+", txt))
            if wc < 45:
                continue
            idx += 1
            title = parser.headings[0][:72] if parser.headings else f"Capítulo {idx}"
            chapters.append({
                "index": idx,
                "title": title,
                "word_count": wc,
                "text": txt,
            })
    return chapters


def split_plain_text_chapters(text: str):
    """Divide texto plano em capítulos se houver cabeçalhos 'Chapter X', senão retorna 1 bloco."""
    cleaned = text.replace("\r\n", "\n").strip()
    matches = list(re.finditer(r"(?im)^(chapter\s+[0-9ivxlcdm]+[^\n]*)$", cleaned))
    if len(matches) >= 2:
        chapters = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
            chunk = cleaned[start:end].strip()
            wc = len(re.findall(r"[A-Za-z]+", chunk))
            if wc >= 25:
                chapters.append({
                    "index": len(chapters) + 1,
                    "title": m.group(1).strip()[:72],
                    "word_count": wc,
                    "text": chunk,
                })
        if chapters:
            return chapters
    wc = len(re.findall(r"[A-Za-z]+", cleaned))
    return [{"index": 1, "title": "Texto Completo", "word_count": wc, "text": cleaned}]


def extract_media_chapters(text: str = "", file_name: str = "", file_b64: str = ""):
    """Ponto de entrada unificado para .epub, .srt, .vtt, .txt/.md ou texto colado."""
    ext = os.path.splitext((file_name or "").lower())[1]
    raw_bytes = None
    if file_b64:
        b64_clean = file_b64.split(",", 1)[-1]
        raw_bytes = base64.b64decode(b64_clean)

    if ext == ".epub" and raw_bytes:
        chapters = extract_epub_chapters(raw_bytes)
        if not chapters:
            raise ValueError("Nenhum capítulo com texto em inglês encontrado neste EPUB.")
        return chapters, "epub"

    if ext == ".pdf":
        raise ValueError("PDF ainda não é decodificado nativamente sem biblioteca externa. Converta para .epub/.txt ou cole o texto do capítulo.")

    if raw_bytes is not None and not text:
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1", errors="ignore")

    text = (text or "").strip()
    if not text:
        raise ValueError("Nenhum texto fornecido para análise.")

    if ext in (".srt", ".vtt") or "-->" in text[:1200]:
        cleaned = clean_subtitle_text(text)
        wc = len(re.findall(r"[A-Za-z]+", cleaned))
        return [{"index": 1, "title": "Legenda Completa", "word_count": wc, "text": cleaned}], "subtitle"

    return split_plain_text_chapters(text), "text"


def split_sentences(text: str):
    """Divide o texto em frases reais de tamanho legível para cards i+1."""
    norm = re.sub(r"\s+", " ", text or "").strip()
    if not norm:
        return []
    raw_sents = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'\u201c])', norm)
    out = []
    for s in raw_sents:
        s = s.strip()
        if 18 <= len(s) <= 260:
            out.append(s)
        elif len(s) > 260:
            # Pega um recorte limpo de até 240 caracteres respeitando palavras
            cut = s[:235].rsplit(" ", 1)[0].strip()
            if len(cut) >= 18:
                out.append(cut + "...")
    return out


def lemmatize_word(token: str, mwld_by_word: dict) -> str:
    """Resolve flexões inglesas comuns para o lema exato presente no MWLD."""
    w = token.lower().strip("'")
    if not w:
        return ""
    if w in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[w]
    if w in mwld_by_word:
        return w

    candidates = []
    if w.endswith("ies") and len(w) > 4:
        candidates.append(w[:-3] + "y")
    if w.endswith("ied") and len(w) > 4:
        candidates.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        candidates.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        candidates.append(w[:-1])
    if w.endswith("ing") and len(w) > 5:
        base = w[:-3]
        candidates.extend([base, base + "e"])
        if len(base) >= 3 and base[-1] == base[-2]:
            candidates.append(base[:-1])
    if w.endswith("ed") and len(w) > 4:
        base = w[:-2]
        candidates.extend([base, base + "e"])
        if len(base) >= 3 and base[-1] == base[-2]:
            candidates.append(base[:-1])
    if w.endswith("er") and len(w) > 4:
        candidates.extend([w[:-2], w[:-1]])
    if w.endswith("est") and len(w) > 5:
        candidates.extend([w[:-3], w[:-2]])
    if w.endswith("ly") and len(w) > 4:
        candidates.append(w[:-2])
        if w.endswith("ily"):
            candidates.append(w[:-3] + "y")

    for cand in candidates:
        if cand in mwld_by_word:
            return cand
    return w


def _build_structures_index(structures_by_subdeck: dict):
    """Constrói índice de expressões (Phrasal Verbs, Idioms, Collocations) agrupado pela primeira palavra."""
    by_first = {}
    seen = set()
    priority_decks = ["pv-top150", "idioms", "pv-all", "collocations"]
    for dk in priority_decks:
        for entry in structures_by_subdeck.get(dk, []) or []:
            expr = (entry.get("word") or "").strip().lower()
            if not expr or " " not in expr or expr in seen:
                continue
            words = re.findall(r"[a-z]+", expr)
            if len(words) < 2 or len(words) > 5:
                continue
            seen.add(expr)
            by_first.setdefault(words[0], []).append((words, expr, dk, entry))
    return by_first


def _is_word_known(lemma: str, vocab_map: dict, pure_function_words: set) -> str:
    if lemma in pure_function_words or lemma in EXTRA_STOPWORDS:
        return "functional"
    t = vocab_map.get(lemma)
    if not t:
        return "pending"
    if t.get("status_geral") == "conhecido":
        return "conhecido"
    statuses = [ac.get("status") for ac in t.get("acepcoes", []) if ac.get("status")]
    if "desconhecido" in statuses:
        return "desconhecido"
    if "duvida" in statuses:
        return "duvida"
    if "conhecido" in statuses:
        return "conhecido"
    return "pending"


def mine_media_deck(
    title: str,
    text: str,
    media_type: str,
    mwld_by_word: dict,
    structures_by_subdeck: dict,
    knowledge_map: dict,
    pure_function_words: set,
    chapter_label: str = "Texto Completo",
    max_words: int = 80,
):
    """
    Analisa o texto da obra, calcula cobertura real (Nation 95%/98%), detecta
    palavras-chave e expressões (Phrasal Verbs, Idioms, Collocations) e gera um deck completo.
    """
    vocab_map = (knowledge_map or {}).get("mapa_vocabulario", {})
    sentences = split_sentences(text)
    if not sentences and text.strip():
        sentences = [text.strip()[:240]]

    # 1. Passagem de detecção estatística de Nomes Próprios (inclusive nomes que existem no dicionário, ex: "Sunny", "Rain", "Jet")
    token_re = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
    mid_cap_counts = Counter()
    mid_low_counts = Counter()
    for sent in sentences:
        words_in_sent = list(token_re.finditer(sent))
        for idx_w, m in enumerate(words_in_sent):
            raw = m.group(0)
            low = raw.lower().split("'")[0]
            if len(low) < 2 or raw.isupper():
                continue
            if idx_w > 0:
                if raw[0].isupper():
                    mid_cap_counts[low] += 1
                else:
                    mid_low_counts[low] += 1

    # Palavra que aparece predominantemente capitalizada no meio das frases (>=80%, min 2 ocorrências) é Nome Próprio da obra
    proper_nouns = set()
    for w_low, cap_c in mid_cap_counts.items():
        low_c = mid_low_counts.get(w_low, 0)
        tot_mid = cap_c + low_c
        if cap_c >= 2 and (cap_c / tot_mid) >= 0.80:
            proper_nouns.add(w_low)

    def _quote_quality_score(sent_str: str, raw_token: str, idx_in_sent: int) -> int:
        score = 0
        if idx_in_sent > 0 and raw_token[0].islower():
            score += 40
        if "[" not in sent_str and "]" not in sent_str and "—" not in sent_str and ":" not in sent_str:
            score += 25
        if 35 <= len(sent_str) <= 155:
            score += 20
        return score

    # 2. Contagem de tokens totais e por lema + melhor frase narrativa da obra
    total_tokens = 0
    known_tokens = 0
    lemma_counts = Counter()
    lemma_quote = {}
    lemma_quote_score = {}
    lemma_status = {}
    lower_seen = set(mid_low_counts.keys())

    for sent in sentences:
        words_in_sent = list(token_re.finditer(sent))
        for idx_w, m in enumerate(words_in_sent):
            raw = m.group(0)
            low = raw.lower().split("'")[0]
            if len(low) < 2:
                continue
            total_tokens += 1

            # Ignora nomes próprios detectados (conta como conhecidos na cobertura para não distorcer a meta 95%)
            if low in proper_nouns:
                known_tokens += 1
                continue

            if idx_w == 0 and low in mwld_by_word and low not in proper_nouns:
                lower_seen.add(low)

            lemma = lemmatize_word(low, mwld_by_word)
            if not lemma or lemma in proper_nouns:
                known_tokens += 1
                continue
            st = _is_word_known(lemma, vocab_map, pure_function_words)
            if st in ("functional", "conhecido"):
                known_tokens += 1
            if st == "functional":
                continue

            # Filtra nomes próprios não presentes no MWLD (ex: Dursley, Hogwarts, Nephis)
            if lemma not in mwld_by_word and low not in lower_seen:
                known_tokens += 1
                continue

            lemma_counts[lemma] += 1
            lemma_status[lemma] = st
            q_score = _quote_quality_score(sent, raw, idx_w)
            if lemma not in lemma_quote or q_score > lemma_quote_score.get(lemma, -1):
                lemma_quote[lemma] = sent
                lemma_quote_score[lemma] = q_score

    # 2. Detecção de Expressões / Phrasal Verbs / Idioms / Collocations na obra
    struct_index = _build_structures_index(structures_by_subdeck or {})
    expr_counts = Counter()
    expr_meta = {}
    expr_quote = {}

    for sent in sentences:
        toks = re.findall(r"[a-z]+", sent.lower())
        n_toks = len(toks)
        for i in range(n_toks):
            first = toks[i]
            # Também checa lema do verbo inicial (ex: "picked up" -> "pick up")
            first_lemma = lemmatize_word(first, mwld_by_word)
            candidates = []
            if first in struct_index:
                candidates.extend(struct_index[first])
            if first_lemma != first and first_lemma in struct_index:
                candidates.extend(struct_index[first_lemma])
            if not candidates:
                continue
            for words_seq, expr_str, dk, entry in candidates:
                seq_len = len(words_seq)
                if i + seq_len > n_toks:
                    continue
                # Match exato nos tokens seguintes (tolerando 1 pronome no meio de phrasal verb: "pick it up")
                matched = False
                if toks[i + 1:i + seq_len] == words_seq[1:]:
                    matched = True
                elif seq_len == 2 and i + 2 < n_toks and toks[i + 1] in ("it", "him", "her", "them", "me", "us", "you") and toks[i + 2] == words_seq[1]:
                    matched = True
                if matched:
                    expr_counts[expr_str] += 1
                    if expr_str not in expr_meta:
                        expr_meta[expr_str] = (dk, entry)
                        expr_quote[expr_str] = sent

    # 3. Curva de Cobertura (Nation 95% / 98%) sobre palavras desconhecidas/pendentes
    # Prioriza palavras presentes no MWLD, mas inclui termos raros/específicos da obra com fallback limpo
    unknown_ranked = [
        (lem, cnt)
        for lem, cnt in lemma_counts.most_common()
        if lemma_status.get(lem) != "conhecido" and (lem in mwld_by_word or lem in lower_seen)
    ]
    total_tokens_safe = max(1, total_tokens)
    current_cov = round((known_tokens / total_tokens_safe) * 100.0, 1)

    running_known = known_tokens
    words_to_95 = None
    words_to_98 = None
    coverage_curve = [{"words_learned": 0, "coverage_pct": current_cov}]
    checkpoints = {10, 20, 35, 50, 75, 100, 150, 200}

    for rank_idx, (lem, cnt) in enumerate(unknown_ranked, 1):
        running_known += cnt
        cov_now = round((running_known / total_tokens_safe) * 100.0, 1)
        if words_to_95 is None and cov_now >= 95.0:
            words_to_95 = rank_idx
        if words_to_98 is None and cov_now >= 98.0:
            words_to_98 = rank_idx
        if rank_idx in checkpoints or rank_idx == len(unknown_ranked):
            coverage_curve.append({"words_learned": rank_idx, "coverage_pct": cov_now})

    # 4. Monta entradas compatíveis com MWLD_BY_SUBDECK (Modo Foco, Grade, Fila Anki, Podcast)
    slug = slugify_title(f"{title}-{chapter_label}" if chapter_label != "Texto Completo" else title)
    subdeck_id = f"media:{slug}"
    entries = []

    raw_limit = str(max_words).strip().lower()
    if raw_limit == "auto95":
        target_words = words_to_95 if words_to_95 is not None else len(unknown_ranked)
        effective_words_limit = max(15, min(1500, target_words))
        max_expr = min(len(expr_counts), max(12, min(80, effective_words_limit // 3)))
    elif raw_limit == "all":
        effective_words_limit = min(1500, len(unknown_ranked))
        max_expr = min(len(expr_counts), 150)
    else:
        try:
            num_lim = max(15, min(1500, int(raw_limit)))
        except ValueError:
            num_lim = 80
        max_expr = min(len(expr_counts), max(8, min(120, num_lim // 4)))
        effective_words_limit = max(10, num_lim - max_expr)

    top_expressions = []
    for expr_str, freq in expr_counts.most_common(max_expr):
        dk, src_entry = expr_meta[expr_str]
        quote = expr_quote.get(expr_str, "")
        st = _is_word_known(expr_str, vocab_map, pure_function_words)
        kind_lbl = {"pv-top150": "Phrasal Verb", "pv-all": "Phrasal Verb", "idioms": "Idiom", "collocations": "Collocation"}.get(dk, "Expressão")
        entry_obj = {
            "id": f"media_{slug}_expr_{re.sub(r'[^a-z0-9]+', '_', expr_str)}",
            "word": src_entry.get("word", expr_str),
            "pos": kind_lbl,
            "ipa": src_entry.get("ipa", ""),
            "audio_url": src_entry.get("audio_url", ""),
            "definition_en": src_entry.get("definition_en", ""),
            "example_1": quote or src_entry.get("example_1", ""),
            "example_2": src_entry.get("example_1", "") if quote else src_entry.get("example_2", ""),
            "subdeck": subdeck_id,
            "theme": f"{title[:28]} · {freq}x na obra",
            "media_freq": freq,
            "media_kind": "expression",
            "media_source_title": title,
            "status_snapshot": st,
        }
        entries.append(entry_obj)
        top_expressions.append({
            "word": entry_obj["word"],
            "kind": kind_lbl,
            "freq": freq,
            "status": st,
            "definition_en": entry_obj["definition_en"],
            "quote": entry_obj["example_1"],
        })

    # Depois: palavras de maior impacto na cobertura (desconhecidas/pendentes mais repetidas na obra)
    remaining_slots = effective_words_limit
    top_words = []
    for lem, freq in unknown_ranked[:remaining_slots]:
        mw_list = mwld_by_word.get(lem) or []
        mw0 = mw_list[0] if mw_list else {}
        quote = lemma_quote.get(lem, "")
        st = lemma_status.get(lem, "pending")
        clean_def_en = re.sub(r"<br\s*/?>", " · ", mw0.get("definition_en", "Termo extraído da obra (use Jev IA [J] para definição contextual)."), flags=re.IGNORECASE)
        clean_def_en = re.sub(r"<[^>]+>", "", clean_def_en).strip()
        entry_obj = {
            "id": mw0.get("id", f"media_{slug}_{lem}"),
            "word": mw0.get("word", lem),
            "pos": mw0.get("pos", "term"),
            "ipa": mw0.get("ipa", ""),
            "audio_url": mw0.get("audio_url", ""),
            "definition_en": clean_def_en,
            "example_1": quote or mw0.get("example_1", ""),
            "example_2": mw0.get("example_1", "") if quote else mw0.get("example_2", ""),
            "subdeck": subdeck_id,
            "theme": f"{title[:28]} · {freq}x na obra",
            "media_freq": freq,
            "media_kind": "word",
            "media_source_title": title,
            "status_snapshot": st,
        }
        entries.append(entry_obj)
        top_words.append({
            "word": entry_obj["word"],
            "pos": entry_obj["pos"],
            "ipa": entry_obj["ipa"],
            "freq": freq,
            "status": st,
            "definition_en": entry_obj["definition_en"],
            "quote": entry_obj["example_1"],
        })

    projected_known = known_tokens + sum(freq for _, freq in unknown_ranked[:remaining_slots])
    projected_cov = round(min(100.0, (projected_known / total_tokens_safe) * 100.0), 1)

    return {
        "slug": slug,
        "subdeck": subdeck_id,
        "title": title,
        "chapter_label": chapter_label,
        "media_type": media_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "total_tokens": total_tokens,
            "unique_lemmas": len(lemma_counts),
            "unknown_unique": len(unknown_ranked),
            "expressions_found": len(expr_counts),
            "current_coverage_pct": current_cov,
            "projected_coverage_pct": projected_cov,
            "words_to_95_pct": words_to_95 if words_to_95 is not None else len(unknown_ranked),
            "words_to_98_pct": words_to_98 if words_to_98 is not None else len(unknown_ranked),
            "deck_size": len(entries),
        },
        "coverage_curve": coverage_curve[:10],
        "top_words": top_words[:40],
        "top_expressions": top_expressions[:30],
        "entries": entries,
    }


def compute_live_deck_progress(deck_obj: dict, knowledge_map: dict):
    """Recalcula o progresso e cobertura estimada ao vivo conforme o usuário avalia palavras."""
    vocab_map = (knowledge_map or {}).get("mapa_vocabulario", {})
    entries = deck_obj.get("entries", [])
    known_in_deck = 0
    gaps_in_deck = 0
    doubts_in_deck = 0
    for e in entries:
        w_low = (e.get("word") or "").lower().strip()
        t = vocab_map.get(w_low)
        if not t:
            continue
        if t.get("status_geral") == "conhecido":
            known_in_deck += 1
        else:
            sts = [ac.get("status") for ac in t.get("acepcoes", [])]
            if "desconhecido" in sts:
                gaps_in_deck += 1
            elif "duvida" in sts:
                doubts_in_deck += 1
            elif "conhecido" in sts:
                known_in_deck += 1

    total = max(1, len(entries))
    base_cov = float(deck_obj.get("stats", {}).get("current_coverage_pct", 0.0))
    proj_cov = float(deck_obj.get("stats", {}).get("projected_coverage_pct", base_cov))
    gain = max(0.0, proj_cov - base_cov) * (known_in_deck / total)
    live_cov = round(min(100.0, base_cov + gain), 1)
    return {
        "evaluated": known_in_deck + gaps_in_deck + doubts_in_deck,
        "known": known_in_deck,
        "gaps": gaps_in_deck,
        "doubts": doubts_in_deck,
        "total": len(entries),
        "percent": round(((known_in_deck + gaps_in_deck + doubts_in_deck) / total) * 100.0, 1),
        "live_coverage_pct": live_cov,
    }
