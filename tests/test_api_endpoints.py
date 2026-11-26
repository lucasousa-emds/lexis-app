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
