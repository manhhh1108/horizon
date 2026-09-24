from horizon_tool.core.input_reader import scan_input_folder, filter_by_selection


def test_scan_sorts_numerically_and_skips_invalid(tmp_path):
    (tmp_path / "2.txt").write_text("two", encoding="utf-8")
    (tmp_path / "10.txt").write_text("ten", encoding="utf-8")
    (tmp_path / "1.txt").write_text("one", encoding="utf-8")
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("no number", encoding="utf-8")
    (tmp_path / "readme.md").write_text("ignored", encoding="utf-8")

    scripts, skipped = scan_input_folder(tmp_path)

    assert [s.ordinal for s in scripts] == [1, 2, 10]
    skipped_names = {s.path.name for s in skipped}
    assert "empty.txt" in skipped_names
    assert "notes.txt" in skipped_names
    assert "readme.md" not in skipped_names


def test_filter_by_selection_range():
    class S:
        def __init__(self, o): self.ordinal = o
    items = [S(1), S(2), S(5), S(7), S(20)]
    picked = filter_by_selection(items, "5-20")
    assert [s.ordinal for s in picked] == [5, 7, 20]


def test_filter_by_selection_list():
    class S:
        def __init__(self, o): self.ordinal = o
    items = [S(1), S(3), S(7), S(9)]
    picked = filter_by_selection(items, "3,7,9")
    assert [s.ordinal for s in picked] == [3, 7, 9]


def test_filter_by_selection_empty_returns_all():
    class S:
        def __init__(self, o): self.ordinal = o
    items = [S(1), S(2)]
    assert filter_by_selection(items, "") == items
