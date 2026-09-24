# horizon_tool/tests/test_chatgpt_loop.py
from horizon_tool.automation.chatgpt import should_continue, run_continue_loop

CONTINUE = r'\[PART\s+\d+\s+COMPLETE.*?CONTINUE.*?\]'


def test_should_continue_detects_marker():
    assert should_continue('text\n[PART 1 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]', CONTINUE)
    assert not should_continue("just a normal ending.", CONTINUE)


def test_run_continue_loop_collects_all_parts():
    responses = [
        'PART ONE BODY\n[PART 1 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]',
        'PART TWO BODY\n[PART 2 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]',
        'PART THREE BODY (final)',
    ]
    reads = iter(responses)
    sent: list[str] = []

    def read_response() -> str:
        return next(reads)

    def send_message(text: str) -> None:
        sent.append(text)

    parts = run_continue_loop(read_response, send_message, CONTINUE, max_parts=10)

    assert len(parts) == 3
    assert parts[0].startswith("PART ONE")
    assert sent == ["CONTINUE", "CONTINUE"]  # sent twice, not after the last


def test_run_continue_loop_respects_max_parts():
    def read_response() -> str:
        return '...\n[PART 9 COMPLETE — TYPE "CONTINUE" FOR THE NEXT PART]'  # never ends
    sent: list[str] = []
    parts = run_continue_loop(read_response, lambda t: sent.append(t), CONTINUE, max_parts=3)
    assert len(parts) == 3  # stopped at the cap
    # No CONTINUE after the final collected part: 3 parts -> 2 CONTINUEs.
    assert len(sent) == 2
