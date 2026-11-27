"""Self-contained API endpoint integration tests for Lexis Suite."""

import importlib.util
import json
import os
import pathlib
import threading
import urllib.error
from urllib.request import urlopen

import pytest


@pytest.fixture(scope="module")
def base_url():
    explicit_url = os.environ.get("LEXIS_TEST_URL", "").strip()
    if explicit_url:
        yield explicit_url.rstrip("/")
        return

    source = pathlib.Path(__file__).resolve().parents[1] / "vocab_review_server.py"
    spec = importlib.util.spec_from_file_location("lexis_api_under_test", source)
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)

    backend.load_knowledge_map()
    server = backend.ThreadingHTTPServer(("127.0.0.1", 0), backend.RequestHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_status(base_url):
    with urlopen(f"{base_url}/api/status", timeout=10) as response:
        assert response.status == 200
        data = json.load(response)

    assert isinstance(data, dict)
    assert {"usuario", "stats", "total_indexed"} <= data.keys()


def test_subdecks(base_url):
    with urlopen(f"{base_url}/api/subdecks", timeout=10) as response:
        assert response.status == 200
        data = json.load(response)

    assert isinstance(data, dict)
    assert isinstance(data["subdecks"], list)


def test_gaps(base_url):
    with urlopen(f"{base_url}/api/gaps?subdeck=02k", timeout=10) as response:
        assert response.status == 200


def test_export_knowledge_map(base_url):
    with urlopen(f"{base_url}/api/export-knowledge-map", timeout=10) as response:
        assert response.status == 200
        data = json.load(response)

    assert isinstance(data, dict)
    assert "mapa_vocabulario" in data


def test_youtube_transcript_invalid_id_returns_400(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urlopen(f"{base_url}/api/youtube-transcript?v=invalid", timeout=5)
    assert exc_info.value.code == 400


def test_analytics_endpoint(base_url):
    with urlopen(f"{base_url}/api/analytics", timeout=10) as response:
        assert response.status == 200
        data = json.load(response)

    assert data.get("success") is True
    assert {"user_level", "totals", "cefr_bands", "structures_bands", "pos_breakdown", "daily_timeline"} <= data.keys()
    assert isinstance(data["cefr_bands"], list)
    assert isinstance(data["totals"]["mapped_terms"], int)


def test_anki_hub_endpoint_resilient_when_anki_closed(base_url):
    with urlopen(f"{base_url}/api/anki-hub", timeout=10) as response:
        assert response.status == 200
        data = json.load(response)

    assert data.get("success") is True
    assert isinstance(data.get("anki_connected"), bool)
    assert {"ready_count", "waiting_count", "injected_count", "total_queue"} <= data["pipeline"].keys()
    assert isinstance(data["top_ready"], list)
    assert isinstance(data["recent_injected"], list)


def test_immersion_playlist_endpoint(base_url):
    with urlopen(f"{base_url}/api/immersion-playlist?source=gaps&limit=10", timeout=10) as response:
        assert response.status == 200
        data = json.load(response)

    assert data.get("success") is True
    assert data.get("source") == "gaps"
    assert isinstance(data.get("tracks"), list)
    if data["tracks"]:
        first = data["tracks"][0]
        assert {"id", "word", "en", "pt", "audio_type", "subdeck"} <= first.keys()


def test_persistent_data_dir_seeding_and_merge(tmp_path):
    source = pathlib.Path(__file__).resolve().parents[1] / "vocab_review_server.py"
    spec = importlib.util.spec_from_file_location("lexis_persist_under_test", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    seed_file = tmp_path / "seed_map.json"
    persist_dir = tmp_path / "mnt_data"
    persist_file = persist_dir / "knowledge_map_english.json"

    seed_payload = {
        "usuario": "Lucas",
        "mapa_vocabulario": {
            "resilient": {
                "termo": "resilient",
                "status_geral": "conhecido",
                "acepcoes": [{"sentido_id": "res_1", "status": "conhecido", "confirmado_em": "2026-11-26T06:00:00"}]
            }
        },
        "estatisticas": {}
    }
    seed_file.write_text(json.dumps(seed_payload), encoding="utf-8")

    mod.PERSISTENT_DATA_DIR = str(persist_dir)
    mod.SEED_MAP_FILE = str(seed_file)
    mod.MAP_FILE = str(persist_file)
    mod.load_knowledge_map()

    assert persist_file.exists()
    assert "resilient" in mod.KNOWLEDGE_MAP["mapa_vocabulario"]


def test_static_assets_served(base_url):
    for rel, expected_ctype in [
        ("/static/css/lexis.css", "text/css"),
        ("/static/js/lexis.js", "application/javascript"),
    ]:
        with urlopen(f"{base_url}{rel}", timeout=5) as response:
            assert response.status == 200
            ctype = response.headers.get("Content-Type", "")
            assert expected_ctype in ctype
            body = response.read().decode("utf-8")
            assert len(body) > 100


def test_static_path_traversal_blocked(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urlopen(f"{base_url}/static/../.env", timeout=5)
    assert exc_info.value.code in (403, 404)


def test_dev_watch_endpoint(base_url):
    with urlopen(f"{base_url}/api/dev-watch", timeout=5) as response:
        assert response.status == 200
        data = json.load(response)
    assert {"html", "css", "js"} <= data.keys()
    assert all(isinstance(data[k], int) and data[k] > 0 for k in ("html", "css", "js"))


def test_media_miner_epub_and_subtitle_extraction():
    import base64, io, zipfile
    import media_miner

    # Synthetic minimal EPUB in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/container.xml", '<?xml version="1.0"?><container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        zf.writestr("OEBPS/content.opf", '<package><manifest><item id="c1" href="ch1.xhtml"/></manifest><spine><itemref idref="c1"/></spine></package>')
        zf.writestr("OEBPS/ch1.xhtml", "<html><body><h1>The Boy Who Lived</h1><p>" + ("The wizard picked up his strange cloak and muttered a quiet spell in the corridor. " * 6) + "</p></body></html>")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    chapters, mtype = media_miner.extract_media_chapters(file_name="hp.epub", file_b64=b64)
    assert mtype == "epub"
    assert len(chapters) == 1
    assert chapters[0]["title"] == "The Boy Who Lived"
    assert chapters[0]["word_count"] >= 45

    srt = "1\n00:00:01,000 --> 00:00:03,000\n<i>I never gave up on this dream.</i>\n\n2\n00:00:04,000 --> 00:00:06,000\nWe figured it out together.\n"
    sub_chaps, stype = media_miner.extract_media_chapters(text=srt, file_name="ep01.srt")
    assert stype == "subtitle"
    assert "-->" not in sub_chaps[0]["text"]
    assert "never gave up" in sub_chaps[0]["text"]


def test_media_miner_api_roundtrip(base_url):
    import urllib.parse
    sample_text = (
        "The young wizard picked up his heavy cloak and hurried down the narrow corridor. "
        "He never gave up looking for the mysterious letter hidden beneath the staircase. "
        "Every corridor echoed with strange whispers, and the wizard held his lantern steady. "
        "She figured out the riddle before the corridor grew completely dark."
    )
    req = urllib.request.Request(
        f"{base_url}/api/media-mine",
        data=json.dumps({"title": "Harry Potter Sample", "media_type": "book", "text": sample_text, "max_words": 40}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        mined = json.loads(resp.read().decode("utf-8"))
    assert mined["success"] is True
    deck = mined["deck"]
    assert deck["subdeck"].startswith("media:")
    assert deck["stats"]["total_tokens"] > 20
    assert deck["stats"]["deck_size"] > 0
    assert len(deck["coverage_curve"]) >= 1

    # Verify the mined deck is listed and queryable by /api/words
    with urllib.request.urlopen(f"{base_url}/api/media-decks", timeout=5) as resp:
        listed = json.loads(resp.read().decode("utf-8"))
    assert listed["success"] is True
    assert any(d["slug"] == deck["slug"] for d in listed["decks"])

    q = urllib.parse.urlencode({"subdeck": deck["subdeck"], "status": "all", "limit": 20})
    with urllib.request.urlopen(f"{base_url}/api/words?{q}", timeout=5) as resp:
        words_res = json.loads(resp.read().decode("utf-8"))
    assert len(words_res["words"]) > 0

    # Clean up via /api/media-delete
    del_req = urllib.request.Request(
        f"{base_url}/api/media-delete",
        data=json.dumps({"slug": deck["slug"]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(del_req, timeout=5) as resp:
        del_res = json.loads(resp.read().decode("utf-8"))
    assert del_res["success"] is True
    assert del_res["removed"] is True


def test_media_miner_filters_proper_nouns_matching_dictionary_words():
    import media_miner
    # "Sunny" exists in dictionary ("having sunlight") but is used as a character's proper name mid-sentence
    text = (
        "On this particular day, Sunny decided to pamper himself in the dark alley. "
        "Before long, Sunny stared at the ancient lantern while Sunny muttered quietly. "
        "Eventually, Sunny opened the rusty door and stepped into the silent corridor."
    )
    mwld_mock = {
        "sunny": [{"id": "mw_sunny", "word": "sunny", "pos": "adjective", "definition_en": "having sunlight"}],
        "lantern": [{"id": "mw_lantern", "word": "lantern", "pos": "noun", "definition_en": "a portable lamp<br>with a handle"}],
        "corridor": [{"id": "mw_corr", "word": "corridor", "pos": "noun", "definition_en": "a long hallway"}],
    }
    deck = media_miner.mine_media_deck(
        title="Shadow Slave Sample",
        text=text,
        media_type="book",
        mwld_by_word=mwld_mock,
        structures_by_subdeck={},
        knowledge_map={},
        pure_function_words=set(),
        max_words="auto95",
    )
    mined_words = [w["word"].lower() for w in deck["top_words"]]
    assert "sunny" not in mined_words
    assert "lantern" in mined_words
    lantern_item = next(w for w in deck["top_words"] if w["word"] == "lantern")
    assert "<br>" not in lantern_item["definition_en"]
