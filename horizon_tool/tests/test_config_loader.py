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


def test_save_config_preserves_unknown_keys_and_comments(tmp_path):
    # A key/comment the tool doesn't know about must survive a Settings save.
    from horizon_tool.core.config_loader import save_config
    out = tmp_path / "config.yaml"
    out.write_text(
        "# top comment\n"
        "grok:\n"
        "  durations: [\"10s\"]\n"
        "  future_knob: keep-me   # inline comment\n"
        "custom_section:\n"
        "  api_key: secret123\n",
        encoding="utf-8",
    )
    # Save only a known change; do NOT include the unknown keys in cfg.
    save_config(out, {"grok": {"durations": ["15s"]}})
    reloaded = load_yaml(out)
    assert reloaded["grok"]["durations"] == ["15s"]        # applied
    assert reloaded["grok"]["future_knob"] == "keep-me"    # unknown sub-key kept
    assert reloaded["custom_section"]["api_key"] == "secret123"  # unknown section kept
    assert "# top comment" in out.read_text(encoding="utf-8")    # comments kept
