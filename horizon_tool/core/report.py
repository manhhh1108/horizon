"""Write the per-session report.xlsx summary."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from horizon_tool.core.statuses import STATUS_REJECTED  # re-exported for callers

_HEADERS = [
    "STT", "File input", "Plugin", "Hash", "Tài khoản",
    "Word", "Ảnh 9:16", "Ảnh 16:9", "Video",
    "Section thiếu", "Lỗi/Bỏ qua", "Thời gian (s)",
]
_REJECT_FILL = PatternFill(start_color="FFF4CCCC", end_color="FFF4CCCC",
                           fill_type="solid")


class ReportWriter:
    """Accumulates report rows and saves an .xlsx with highlighted rejects."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._wb = Workbook()
        self._ws = self._wb.active
        self._ws.title = "Report"
        self._ws.append(_HEADERS)
        for cell in self._ws[1]:
            cell.font = Font(bold=True)

    def add_row(self, *, ordinal: int, input_filename: str, plugin_name: str,
                plugin_hash: str, account: str, word: str, img_9x16: str,
                img_16x9: str, video: str, missing_sections: str, error: str,
                duration_seconds: float) -> None:
        values = [ordinal, input_filename, plugin_name, plugin_hash, account,
                  word, img_9x16, img_16x9, video, missing_sections, error,
                  round(duration_seconds, 1)]
        self._ws.append(values)
        row = self._ws.max_row
        # Highlight any step cell that was rejected.
        for col, value in enumerate(values, start=1):
            if value == STATUS_REJECTED:
                self._ws.cell(row=row, column=col).fill = _REJECT_FILL

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._wb.save(str(self.path))
