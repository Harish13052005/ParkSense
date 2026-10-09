def test_get_spots_empty(auth_client):
    """When the DB is empty, GET /api/spots returns an empty list."""
    resp = auth_client.get("/api/spots")
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json() == []


def test_create_and_toggle_spot(auth_client):
    # ---- CREATE --------------------------------------------------------
    create_resp = auth_client.post(
        "/api/spots",
        json={"spot_number": "P42", "is_occupied": False},
    )
    assert create_resp.status_code == 201
    data = create_resp.get_json()
    spot_id = data["id"]
    assert data["spot_number"] == "P42"
    assert data["is_occupied"] is False

    # ---- TOGGLE (PUT) --------------------------------------------------
    toggle_resp = auth_client.put(
        f"/api/spots/{spot_id}",
        json={"is_occupied": True},
    )
    assert toggle_resp.status_code == 200
    toggled = toggle_resp.get_json()
    assert toggled["is_occupied"] is True

    # ---- READ ---------------------------------------------------------
    get_resp = auth_client.get(f"/api/spots/{spot_id}")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["spot_number"] == "P42"

    # ---- DELETE -------------------------------------------------------
    del_resp = auth_client.delete(f"/api/spots/{spot_id}")
    assert del_resp.status_code == 204

    # Verify it really vanished
    not_found = auth_client.get(f"/api/spots/{spot_id}")
    assert not_found.status_code == 404