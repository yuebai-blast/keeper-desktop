from pathlib import Path

from keeper_engine.config.settings import Settings


def test_auth_token_default_empty(monkeypatch):
    monkeypatch.delenv("KEEPER_AUTH_TOKEN", raising=False)
    assert Settings().auth_token == ""


def test_auth_token_from_env(monkeypatch):
    monkeypatch.setenv("KEEPER_AUTH_TOKEN", "abc123")
    assert Settings().auth_token == "abc123"


def test_models_dir_defaults_to_home_subdir(monkeypatch):
    monkeypatch.delenv("KEEPER_MODELS_DIR", raising=False)
    monkeypatch.setenv("KEEPER_HOME", "/tmp/kh")
    s = Settings()
    assert s.models_dir == Path("/tmp/kh/models")
    assert s.workspace_dir == Path("/tmp/kh/workspace")  # 其余派生仍跟随 home


def test_models_dir_env_override(monkeypatch):
    monkeypatch.setenv("KEEPER_HOME", "/tmp/kh")
    monkeypatch.setenv("KEEPER_MODELS_DIR", "/tmp/cache/models")
    s = Settings()
    assert s.models_dir == Path("/tmp/cache/models")
    assert s.workspace_dir == Path("/tmp/kh/workspace")  # home 派生不受 models 覆盖影响


def test_config_toml_read_follows_home_env(tmp_path, monkeypatch):
    """回归：config.toml 的读取位置必须跟随 home（env KEEPER_HOME），而非写死 ~/.keeper。

    prod 下写入端把配置落在 {app_data_dir}/config.toml；若读取端仍固定 ~/.keeper，
    持久化的配置（如 ark_model）下次启动读不回来。
    """
    home = tmp_path / "prod_home"
    home.mkdir()
    (home / "config.toml").write_text('ark_model = "from-home-toml"\n', encoding="utf-8")
    monkeypatch.setenv("KEEPER_HOME", str(home))
    monkeypatch.delenv("KEEPER_ARK_MODEL", raising=False)

    assert Settings().ark_model == "from-home-toml"


def test_config_toml_read_follows_home_init_kwarg(tmp_path, monkeypatch):
    """构造参数传 home 时（测试隔离常用），config.toml 也应从该 home 读取。"""
    home = tmp_path / "init_home"
    home.mkdir()
    (home / "config.toml").write_text('ark_model = "from-init-toml"\n', encoding="utf-8")
    monkeypatch.delenv("KEEPER_HOME", raising=False)
    monkeypatch.delenv("KEEPER_ARK_MODEL", raising=False)

    assert Settings(home=home).ark_model == "from-init-toml"
