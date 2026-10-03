from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import NotFoundError, ValidationError, register_exception_handlers


def _app_with_failing_routes() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/missing")
    async def missing():
        raise NotFoundError("Thing does not exist.", details={"thing_id": "abc"})

    @app.get("/invalid")
    async def invalid():
        raise ValidationError("Bad input.")

    return app


def test_app_error_renders_structured_body():
    client = TestClient(_app_with_failing_routes())
    response = client.get("/missing")
    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Thing does not exist."
    assert body["error"]["details"] == {"thing_id": "abc"}


def test_error_subclass_status_codes():
    client = TestClient(_app_with_failing_routes())
    response = client.get("/invalid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
