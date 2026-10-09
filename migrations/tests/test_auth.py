def test_login_success(auth_client):
    """The auth_client fixture already logged in; just confirm session works."""
    resp = auth_client.get("/")
    # Flask-Login adds `current_user.is_authenticated` to the template context
    # The home page renders the navbar; we can look for the logout link.
    assert b"Logout" in resp.data

def test_login_failure(client):
    resp = client.post(
        "/auth/login",
        data=dict(username="nonexistent", password="badpass"),
        follow_redirects=True,
    )
    # Should stay on the login page and flash an error
    assert b"Invalid username or password" in resp.data
    assert resp.status_code == 200   # 200 because we render the login template again
    