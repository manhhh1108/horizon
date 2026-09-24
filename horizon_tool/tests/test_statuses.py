from horizon_tool.core import statuses
from horizon_tool.core.report import STATUS_REJECTED as REPORT_REJECTED


def test_report_reexports_shared_rejected():
    assert REPORT_REJECTED == statuses.STATUS_REJECTED == "Bị từ chối"
