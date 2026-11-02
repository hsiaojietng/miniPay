"""Keeps docs/openapi.json, the saved API contract, in step with what the app actually serves."""

import json
from pathlib import Path

from app.main import app

SAVED = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"
REGENERATE = (
    'python -c "import json; from app.main import app; '
    "json.dump(app.openapi(), open('docs/openapi.json', 'w'), indent=2)\""
)


def test_saved_openapi_matches_app():
    assert json.loads(SAVED.read_text()) == app.openapi(), (
        f"docs/openapi.json is out of date. Regenerate it with:\n{REGENERATE}"
    )


def test_every_documented_error_uses_the_error_shape():
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if int(status) >= 400:
                    schema = response["content"]["application/json"]["schema"]
                    assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, (method, path, status)
