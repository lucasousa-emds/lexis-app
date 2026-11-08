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
