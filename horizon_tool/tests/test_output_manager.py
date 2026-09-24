# horizon_tool/tests/test_output_manager.py
from horizon_tool.core.output_manager import (
    prepare_output_dir, output_paths, save_raw_response,
    OVERWRITE, SKIP, TIMESTAMP,
)


def test_prepare_creates_dir(tmp_path):
    d = prepare_output_dir(tmp_path, 5, OVERWRITE)
    assert d == tmp_path / "5"
    assert d.is_dir()


def test_prepare_skip_returns_none_when_exists(tmp_path):
    (tmp_path / "5").mkdir()
    assert prepare_output_dir(tmp_path, 5, SKIP) is None


def test_prepare_overwrite_reuses_existing(tmp_path):
    (tmp_path / "5").mkdir()
    d = prepare_output_dir(tmp_path, 5, OVERWRITE)
    assert d == tmp_path / "5"


def test_prepare_timestamp_makes_new_dir(tmp_path):
    (tmp_path / "5").mkdir()
    d = prepare_output_dir(tmp_path, 5, TIMESTAMP, suffix="20260924_101500")
    assert d == tmp_path / "5_20260924_101500"
    assert d.is_dir()


def test_output_paths_naming(tmp_path):
    paths = output_paths(tmp_path / "7", 7)
    assert paths["docx"].name == "7.docx"
    assert paths["img_9x16"].name == "7_9x16.png"
    assert paths["img_16x9"].name == "7_16x9.png"
    assert paths["video"].name == "7.mp4"
    assert paths["raw"].name == "raw_response.txt"


def test_save_raw_response(tmp_path):
    d = tmp_path / "1"
    d.mkdir()
    p = save_raw_response(d, "nội dung thô")
    assert p.read_text(encoding="utf-8") == "nội dung thô"
