def test_obtain_jwt_token(client):
    response = client.post(
        "/api/auth/token",
        json={"username": "admin", "password": "Secret123!"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]


def test_parking_api_requires_a_valid_token(client, bearer_headers):
    valid = client.get("/api/spots", headers=bearer_headers)
    assert valid.status_code == 200
    assert valid.get_json() == []

    assert client.get("/api/spots").status_code == 401
    assert client.get(
        "/api/spots", headers={"Authorization": "Bearer invalid"}
    ).status_code == 401


def test_browser_spot_api_token_requires_a_signed_in_user(client):
    assert client.post("/api/auth/session-token").status_code == 401


def test_signed_in_browser_can_obtain_a_spot_api_token(auth_client):
    response = auth_client.post("/api/auth/session-token")
    assert response.status_code == 200
    assert response.get_json()["access_token"]


def test_legacy_spot_crud_keeps_occupancy_compatible(client, bearer_headers):
    created = client.post(
        "/api/spots",
        headers=bearer_headers,
        json={"spot_number": "P42", "is_occupied": False},
    )
    assert created.status_code == 201
    spot_id = created.get_json()["id"]
    changed = client.put(
        f"/api/spots/{spot_id}",
        headers=bearer_headers,
        json={"is_occupied": True},
    )
    assert changed.status_code == 200
    assert changed.get_json()["is_occupied"] is True
    released = client.put(
        f"/api/spots/{spot_id}",
        headers=bearer_headers,
        json={"is_occupied": False},
    )
    assert released.status_code == 200
    assert released.get_json()["status"] == "AVAILABLE"
    assert client.delete(f"/api/spots/{spot_id}", headers=bearer_headers).status_code == 204


def test_expired_jwt_is_rejected(app, client):
    app.config["JWT_EXP_DELTA_SECONDS"] = -1
    token_response = client.post(
        "/api/auth/token",
        json={"username": "admin", "password": "Secret123!"},
    )
    headers = {
        "Authorization": f"Bearer {token_response.get_json()['access_token']}"
    }
    response = client.get("/api/spots", headers=headers)
    assert response.status_code == 401
    body = response.get_json()
    assert body.get("msg", body.get("message")) == "Token has expired"
