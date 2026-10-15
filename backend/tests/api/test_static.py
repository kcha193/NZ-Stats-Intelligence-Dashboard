from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings


def test_spa_is_served_with_client_side_routing_fallback(tmp_path) -> None:
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "a.js").write_text("console.log(1)")
    settings = load_settings(
        {"NZSTATS_DATA_DIR": str(tmp_path / "data"), "NZSTATS_STATIC_DIR": str(static)}
    )
    with TestClient(create_app(settings)) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/migration").text == "<html>app</html>"  # client-side route
        assert c.get("/releases/12").text == "<html>app</html>"
        assert c.get("/assets/a.js").text == "console.log(1)"
        missing = c.get("/api/nope")
        assert missing.status_code == 404
        assert missing.headers["content-type"].startswith("application/json")
