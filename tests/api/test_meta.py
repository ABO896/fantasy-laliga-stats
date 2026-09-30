def test_get_meta(client):
    response = client.get("/api/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["app_name"] == "Fantasy LaLiga Stats"
    assert "db_path" in body
