# horizon_tool/tests/test_state_store.py
from horizon_tool.core.state_store import StateStore
from horizon_tool.core.statuses import STATUS_DONE, STATUS_FAILED, STATUS_REJECTED, STATUS_SKIPPED


def test_set_and_get_step(tmp_path):
    st = StateStore(tmp_path / "run_state.json")
    st.set_step(1, "word", STATUS_DONE)
    assert st.get_step(1, "word") == STATUS_DONE
    assert st.get_step(1, "video") is None


def test_is_done_only_for_terminal_success(tmp_path):
    st = StateStore(tmp_path / "s.json")
    st.set_step(1, "word", STATUS_DONE)
    st.set_step(1, "img_9x16", STATUS_REJECTED)
    st.set_step(1, "img_16x9", STATUS_SKIPPED)
    st.set_step(1, "video", STATUS_FAILED)
    assert st.is_done(1, "word")        # Xong -> done
    assert st.is_done(1, "img_9x16")    # Bị từ chối -> done (won't retry)
    assert st.is_done(1, "img_16x9")    # Bỏ qua -> done
    assert not st.is_done(1, "video")   # Lỗi -> NOT done (retry on resume)
    assert not st.is_done(2, "word")    # unknown -> not done


def test_meta_roundtrip(tmp_path):
    st = StateStore(tmp_path / "s.json")
    st.set_meta(1, "conversation_url", "https://chat/x")
    assert st.get_meta(1, "conversation_url") == "https://chat/x"
    assert st.get_meta(1, "missing") is None


def test_persistence_survives_reload(tmp_path):
    path = tmp_path / "s.json"
    st = StateStore(path)
    st.set_step(3, "word", STATUS_DONE)
    st.set_meta(3, "conversation_url", "u")
    reloaded = StateStore(path)
    assert reloaded.get_step(3, "word") == STATUS_DONE
    assert reloaded.get_meta(3, "conversation_url") == "u"


def test_atomic_save_no_temp_left(tmp_path):
    path = tmp_path / "s.json"
    StateStore(path).set_step(1, "word", STATUS_DONE)
    assert path.exists()
    assert not (tmp_path / "run_state.json.tmp").exists()


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")
    st = StateStore(path)  # loads in __init__
    assert st.get_step(1, "word") is None
