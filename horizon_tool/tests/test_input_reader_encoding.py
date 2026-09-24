from horizon_tool.core.input_reader import read_text_file


def test_reads_utf8(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Xin chào thế giới", encoding="utf-8")
    assert read_text_file(p) == "Xin chào thế giới"


def test_reads_utf8_bom(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("Nội dung", encoding="utf-8-sig")
    assert read_text_file(p) == "Nội dung"


def test_reads_utf16(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("Kịch bản", encoding="utf-16")
    assert read_text_file(p) == "Kịch bản"


def test_reads_cp1258(tmp_path):
    # "Cà phê Đà" uses only precomposed letters cp1258 supports; the encoded
    # bytes are invalid UTF-8, so the reader must fall through to cp1258.
    text = "Cà phê Đà"
    p = tmp_path / "d.txt"
    p.write_bytes(text.encode("cp1258"))
    assert read_text_file(p) == text
