"""Integration tests requiring a running Lexis server on port 5050."""

import json
from urllib.request import urlopen


BASE_URL = "http://127.0.0.1:5050"
REQUEST_TIMEOUT = 15


def test_status():
    with urlopen(f"{BASE_URL}/api/status", timeout=REQUEST_TIMEOUT) as response:
        assert response.status == 200
        data = json.load(response)

    assert isinstance(data, dict)
    assert {"usuario", "stats", "total_indexed"} <= data.keys()


def test_subdecks():
    with urlopen(f"{BASE_URL}/api/subdecks", timeout=REQUEST_TIMEOUT) as response:
        assert response.status == 200
        data = json.load(response)

    assert isinstance(data, dict)
    assert isinstance(data["subdecks"], list)


def test_gaps():
    with urlopen(f"{BASE_URL}/api/gaps?subdeck=02k", timeout=REQUEST_TIMEOUT) as response:
        assert response.status == 200


def test_export_knowledge_map():
    with urlopen(
        f"{BASE_URL}/api/export-knowledge-map", timeout=REQUEST_TIMEOUT
    ) as response:
        assert response.status == 200
        data = json.load(response)

    assert isinstance(data, dict)
    assert "mapa_vocabulario" in data
