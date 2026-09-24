import logging

from horizon_tool.core.logging_setup import setup_session_logger


def _file_handlers(logger):
    return [h for h in logger.handlers if isinstance(h, logging.FileHandler)]


def test_same_path_twice_adds_one_handler(tmp_path):
    path = tmp_path / "log.txt"
    setup_session_logger(path, name="test_same")
    setup_session_logger(path, name="test_same")
    logger = logging.getLogger("test_same")
    assert len(_file_handlers(logger)) == 1


def test_new_path_replaces_stale_handler(tmp_path):
    setup_session_logger(tmp_path / "run1.txt", name="test_new")
    setup_session_logger(tmp_path / "run2.txt", name="test_new")
    logger = logging.getLogger("test_new")
    handlers = _file_handlers(logger)
    assert len(handlers) == 1  # stale handler removed, only current session
    assert getattr(handlers[0], "_horizon_path").endswith("run2.txt")


def test_writes_to_file(tmp_path):
    path = tmp_path / "sub" / "log.txt"
    logger = setup_session_logger(path, name="test_write")
    logger.info("dòng nhật ký")
    for h in _file_handlers(logger):
        h.flush()
    assert "dòng nhật ký" in path.read_text(encoding="utf-8")
