from pathlib import Path

import pytest

from horizon_tool.core.config_loader import load_yaml, AppConfig

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def test_load_yaml_reads_mapping():
    data = load_yaml(CONFIG_DIR / "config.yaml")
    assert isinstance(data, dict)
    assert data["grok"]["durations"] == ["10s", "15s", "20s"]


def test_appconfig_exposes_gui_values():
    cfg = AppConfig.load(CONFIG_DIR / "config.yaml")
    assert cfg.video_durations == ["10s", "15s", "20s"]
    assert cfg.video_qualities == ["720p", "1080p"]
    assert cfg.send_mode == "two_messages"
    assert cfg.runtime_suffix == ""


def test_load_yaml_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_yaml(CONFIG_DIR / "does_not_exist.yaml")


def test_save_config_roundtrips(tmp_path):
    from horizon_tool.core.config_loader import save_config
    original = load_yaml(CONFIG_DIR / "config.yaml")
    original["timeouts"]["element_wait_seconds"] = 45
    original["auto_resume"]["enabled"] = True
    out = tmp_path / "config.yaml"
    save_config(out, original)
    reloaded = load_yaml(out)
    assert reloaded["timeouts"]["element_wait_seconds"] == 45
    assert reloaded["auto_resume"]["enabled"] is True
    assert reloaded["grok"]["durations"] == original["grok"]["durations"]
    assert reloaded["chatgpt"]["image_wrapper_9x16"] == original["chatgpt"]["image_wrapper_9x16"]
