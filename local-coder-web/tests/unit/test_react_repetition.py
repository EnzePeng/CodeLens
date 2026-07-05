from core.react import _is_repetitive


def test_repetition_detector_allows_structured_reports_with_repeated_terms():
    report = """
# Agent mode implementation review

## Summary
Agent mode uses the agent route, agent status, and agent history panels.

## Findings
- Agent mode should show the final report as rendered Markdown.
- Agent mode should keep evidence visible while the final report is readable.
- Agent mode should not stop just because a report repeats domain terms.

## Next steps
Agent mode needs clearer output. Agent mode needs readable Markdown.
Agent mode needs a visible fullscreen action. Agent mode needs history.
"""

    assert _is_repetitive(report) is False


def test_repetition_detector_still_catches_clear_tail_loops():
    loop = "正常分析内容已经完成。\n" + ("alpha beta gamma " * 8)

    assert _is_repetitive(loop) is True
