from conftest import PASSWORD, csrf_token, sign_in


def test_admin_area_sends_a_visitor_to_sign_in(client):
    response = client.get("/admin")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/sign-in")


def test_curator_signs_in_with_the_password_and_sees_the_cafe_list(client):
    response = sign_in(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")
    assert client.get("/admin").status_code == 200


def test_wrong_password_is_refused(client):
    response = sign_in(client, password="wrong")

    assert response.status_code == 401
    assert "That password is not right" in response.text
    assert client.get("/admin").status_code == 302


def test_no_password_configured_means_nobody_can_sign_in(make_app):
    client = make_app(ADMIN_PASSWORD="").test_client()

    response = sign_in(client, password="")

    assert response.status_code == 401
    assert client.get("/admin").status_code == 302


def test_sign_in_without_a_csrf_token_is_rejected(client):
    response = client.post("/admin/sign-in", data={"password": PASSWORD})

    assert response.status_code == 400
    assert client.get("/admin").status_code == 302


def test_curator_stays_signed_in_for_the_browser_session_only(client):
    response = sign_in(client)

    cookie = response.headers["Set-Cookie"]
    assert "session=" in cookie
    assert "Expires" not in cookie
    assert "HttpOnly" in cookie


def test_curator_signs_out(curator):
    token = csrf_token(curator, "/admin")

    response = curator.post("/admin/sign-out", data={"csrf_token": token})

    assert response.status_code == 302
    assert curator.get("/admin").status_code == 302
