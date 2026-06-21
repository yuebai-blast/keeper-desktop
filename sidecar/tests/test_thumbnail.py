from unittest.mock import patch

from dependency_injector import providers
from fastapi.testclient import TestClient

from keeper_engine.app import create_app
from keeper_engine.config.settings import Settings


def _client(tmp_path):
    # 不用 with TestClient(...)：避免触发 lifespan（建表/模型预热）。
    app = create_app()
    s = Settings(home=tmp_path)
    app.container.settings.override(providers.Object(s))
    return TestClient(app), s


def test_thumbnail_rejects_path_outside_workspace(tmp_path):
    client, _ = _client(tmp_path)
    with patch("keeper_engine.util.imaging.cached_thumbnail") as m:
        r = client.get("/thumbnail", params={"path": "/etc/passwd"})
    assert r.status_code == 404
    m.assert_not_called()  # 白名单在解码前就拦下


def test_thumbnail_allows_path_inside_workspace(tmp_path):
    client, s = _client(tmp_path)
    inside = s.workspace_dir / "proj" / "x.jpg"
    with patch("keeper_engine.util.imaging.cached_thumbnail", return_value=b"JPEGDATA") as m:
        r = client.get("/thumbnail", params={"path": str(inside)})
    assert r.status_code == 200
    assert r.content == b"JPEGDATA"
    m.assert_called_once()


def test_thumbnail_rejects_dotdot_traversal(tmp_path):
    """.. 穿越：路径 resolve 后落到 workspace 外，应被白名单拒绝。"""
    client, s = _client(tmp_path)
    # 构造形如 {workspace_dir}/../<外部文件> 的穿越路径
    traversal = str(s.workspace_dir / ".." / "outside.jpg")
    with patch("keeper_engine.util.imaging.cached_thumbnail") as m:
        r = client.get("/thumbnail", params={"path": traversal})
    assert r.status_code == 404
    m.assert_not_called()  # 路径校验在解码前已拦截


def test_thumbnail_rejects_symlink_escape(tmp_path):
    """symlink 逃逸：workspace 内的 symlink 指向 workspace 外，resolve 后应被拒绝。"""
    client, s = _client(tmp_path)
    # workspace 外的真实目标目录（位于 tmp_path 外但仍在 tmp 下）
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    (outside / "secret.jpg").write_bytes(b"secret")
    # 在 workspace 内建一个指向 workspace 外的 symlink
    workspace = s.workspace_dir
    workspace.mkdir(parents=True, exist_ok=True)
    link = workspace / "escape_link.jpg"
    link.symlink_to(outside / "secret.jpg")
    with patch("keeper_engine.util.imaging.cached_thumbnail") as m:
        r = client.get("/thumbnail", params={"path": str(link)})
    assert r.status_code == 404
    m.assert_not_called()  # symlink resolve 后落到 workspace 外，被白名单拦截
