import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_humanize_code_endpoint_end_to_end():
    res = client.post(
        "/api/humanize-code",
        json={
            "code": "def foo():\n    # Es crucial que esto se ejecute primero\n    return 1\n",
            "language": "python",
            "intensity": "high",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "python"
    assert "return 1" in data["humanized"]
    assert data["original"] != data["humanized"]


def test_humanize_code_endpoint_rejects_empty_code():
    res = client.post("/api/humanize-code", json={"code": "   "})
    assert res.status_code == 400


def test_humanize_code_endpoint_rejects_oversized_payload():
    res = client.post("/api/humanize-code", json={"code": "x" * 200_000})
    assert res.status_code == 422


def test_humanize_text_endpoint_end_to_end():
    res = client.post("/api/humanize", json={"text": "Es importante destacar que esto funciona.", "intensity": "high"})
    assert res.status_code == 200
    data = res.json()
    assert "changes" in data and len(data["changes"]) >= 1


def test_humanize_text_endpoint_includes_before_after_score():
    res = client.post("/api/humanize", json={"text": "Es importante destacar que esto funciona.", "intensity": "high"})
    assert res.status_code == 200
    data = res.json()
    assert data["score_before"] is not None
    assert data["score_after"] is not None
    assert 0 <= data["score_before"]["score"] <= 100
    assert 0 <= data["score_after"]["score"] <= 100


def test_detect_text_with_catastrophic_regex_does_not_hang():
    res = client.post(
        "/api/detect/text",
        json={
            "content": "a" * 40 + "!",
            "config": {"keywords": ["(a+)+$"], "use_regex": True},
        },
    )
    assert res.status_code == 200
    assert res.json()["total_findings"] == 0


def test_detect_file_rejects_oversized_upload(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "MAX_SINGLE_FILE_MB", 0)  # anything non-empty now "exceeds" the limit
    res = client.post(
        "/api/detect/file",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert res.status_code == 400


def test_openapi_schema_is_served():
    res = client.get("/openapi.json")
    assert res.status_code == 200
    paths = res.json()["paths"]
    assert "/api/humanize-code" in paths
    assert "/api/humanize" in paths


def test_process_page_includes_code_humanize_panel():
    res = client.get("/process")
    assert res.status_code == 200
    assert "codeInput" in res.text
    assert "code-humanize.js" in res.text
