from fastapi.testclient import TestClient

from app.capabilities import Capability
from app.main import create_app
from app.optimization import ArchitectureCandidate, ArchitectureMetrics


def test_system_catalogues_start_empty(client):
    capabilities = client.get("/api/system/capabilities")
    architectures = client.get("/api/system/architectures")

    assert capabilities.status_code == 200
    assert capabilities.json() == {"capabilities": []}
    assert architectures.status_code == 200
    assert architectures.json() == {"architectures": []}


def test_registered_entries_round_trip_without_seed_data():
    app = create_app()
    app.state.capabilities.register(Capability(name="read", description="Read a supplied artifact", implies=("view",)))
    app.state.architectures.register(
        ArchitectureCandidate(
            id="held",
            name="Held",
            metrics=ArchitectureMetrics(quality=0.5, cost=1.0, latency=10.0, risk=0.25),
        )
    )
    client = TestClient(app)

    assert client.get("/api/system/capabilities").json() == {
        "capabilities": [
            {"name": "read", "description": "Read a supplied artifact", "implies": ["view"]}
        ]
    }
    body = client.get("/api/system/architectures").json()
    assert body["architectures"] == [
        {
            "id": "held",
            "name": "Held",
            "quality": 0.5,
            "cost": 1.0,
            "latency": 10.0,
            "risk": 0.25,
            "metadata": None,
        }
    ]


def test_pareto_endpoint_classifies_explicit_input(client):
    response = client.post(
        "/api/system/pareto-frontier",
        json={
            "candidates": [
                {"id": "lean", "quality": 0.5, "cost": 1.0, "latency": 10.0, "risk": 0.25},
                {"id": "careful", "quality": 1.0, "cost": 2.0, "latency": 20.0, "risk": 0.125},
                {"id": "heavy", "quality": 0.75, "cost": 4.0, "latency": 40.0, "risk": 0.5},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "frontier": ["careful", "lean"],
        "dominated": ["heavy"],
    }


def test_pareto_duplicate_ids_return_validation_error(client):
    response = client.post(
        "/api/system/pareto-frontier",
        json={
            "candidates": [
                {"id": "same", "quality": 1, "cost": 1, "latency": 1, "risk": 1},
                {"id": "same", "quality": 0, "cost": 2, "latency": 2, "risk": 2},
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_evaluate_policy_endpoint_honors_scope_and_denial(client):
    payload = {
        "capabilities": [
            {"name": "read", "description": None, "implies": []},
            {"name": "draft", "description": None, "implies": ["read"]},
        ],
        "requirements": [
            {"capability": "read", "mandatory": True},
            {"capability": "export", "mandatory": False},
        ],
        "denied": ["export"],
        "leases": [
            {
                "capability": "draft",
                "allowed": True,
                "task_scope": "alpha",
                "expires_at": None,
                "max_calls": None,
                "calls_used": 0,
                "source": "profile",
            }
        ],
        "task_scope": "alpha",
    }

    allowed = client.post("/api/system/evaluate-policy", json=payload)
    payload["task_scope"] = "beta"
    denied_scope = client.post("/api/system/evaluate-policy", json=payload)

    assert allowed.status_code == 200
    body = allowed.json()
    assert body["allowed"] is True
    assert body["granted"] == ["draft", "read"]
    assert "export" in body["denied"]
    assert body["missing_optional"] == ["export"]
    assert denied_scope.json()["allowed"] is False
    assert "draft" not in denied_scope.json()["granted"]


def test_resolve_fallback_endpoint_is_deterministic(client):
    response = client.post(
        "/api/system/resolve-fallback",
        json={
            "candidates": [
                {
                    "id": "primary",
                    "available": False,
                    "capabilities": ["read"],
                    "privacy_class": "restricted",
                    "allowed_tasks": ["review"],
                },
                {
                    "id": "local",
                    "available": True,
                    "capabilities": ["read"],
                    "privacy_class": "restricted",
                    "allowed_tasks": ["review"],
                },
            ],
            "mandatory_capabilities": ["read"],
            "accepted_privacy_classes": ["restricted"],
            "task": "review",
            "preference_order": ["primary", "local"],
            "capabilities": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_id"] == "local"
    assert body["rejected"] == [{"id": "primary", "reason": "unavailable"}]
    assert "api_key" not in response.text
    assert "secret" not in response.text.lower()


def test_bad_lease_timestamp_is_a_validation_error(client):
    response = client.post(
        "/api/system/evaluate-policy",
        json={
            "capabilities": [],
            "requirements": [],
            "denied": [],
            "leases": [
                {
                    "capability": "read",
                    "allowed": True,
                    "expires_at": "not-a-timestamp",
                }
            ],
            "task_scope": None,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
