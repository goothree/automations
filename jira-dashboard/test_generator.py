"""
Generate test steps from Jira issue (summary, description, subtasks, acceptance criteria).
Hybrid: use structured content (bullets, AC, Given/When/Then) when present; else LLM fallback.
Always returns at least one step when the issue has any content (fallback from summary/subtasks).
"""
import re

from config import OPENAI_API_KEY, OPENAI_MODEL


# Section headers that often introduce acceptance criteria or test steps
AC_HEADERS = re.compile(
    r"^(?:acceptance\s+criteria?|ac\s*:?|test\s+cases?|test\s+steps?|steps to (?:verify|test)|verification)\s*:?\s*$",
    re.IGNORECASE,
)
GIVEN_WHEN_THEN = re.compile(r"^\s*(?:given|when|then)\s+.+", re.IGNORECASE)


def generate_test_steps(summary=None, description=None, issue=None):
    """
    Return a list of test step strings from Jira issue data.
    Prefer passing issue (dict with summary, description, subtasks, acceptance_criteria); otherwise summary + description.
    Uses: structured parsing (bullets, AC, Given/When/Then) → LLM → fallback steps from summary/subtasks.
    """
    if issue is not None and isinstance(issue, dict):
        summary = issue.get("summary") or ""
        description = issue.get("description") or ""
        subtasks = issue.get("subtasks") or []
        acceptance_criteria = issue.get("acceptance_criteria") or ""
    else:
        summary = summary or ""
        description = description or ""
        subtasks = []
        acceptance_criteria = ""

    text = _build_combined_text(summary, description, subtasks, acceptance_criteria)
    if not text.strip():
        return [_fallback_step(summary or "Issue")]

    steps = _parse_structured_steps(text)
    if steps:
        return steps

    if OPENAI_API_KEY:
        steps = _llm_generate_steps(summary, description, subtasks, acceptance_criteria)
        if steps:
            return steps

    return _fallback_steps(summary, description, subtasks)


def _build_combined_text(summary, description, subtasks, acceptance_criteria):
    """Combine all issue text for parsing and LLM so we can derive steps from the whole ticket."""
    parts = [summary, description, acceptance_criteria]
    if subtasks:
        parts.append("Subtasks / items to verify:\n" + "\n".join(f"- {s}" for s in subtasks))
    return "\n\n".join(p for p in parts if (p or "").strip()).strip()


def _fallback_step(label):
    """Single fallback step when we have no parsed or LLM steps."""
    return f"Verify: {label[:200]}" if label else "Verify the issue requirements."


def _fallback_steps(summary, description, subtasks):
    """Return a small set of steps so the script is never empty; cover summary and key items."""
    steps = []
    if summary:
        steps.append(_fallback_step(summary))
    for s in (subtasks or [])[:5]:
        if s and (s.strip() not in [x.strip() for x in steps]):
            steps.append(f"Verify: {s.strip()[:200]}")
    if not steps and description:
        first_line = (description.strip().split("\n")[0] or "").strip()[:200]
        if first_line:
            steps.append(f"Verify: {first_line}")
    if not steps:
        steps.append("Verify the issue requirements and acceptance criteria.")
    return steps[:15]


def _parse_structured_steps(text):
    """Extract test steps from bullets, numbered lines, or Given/When/Then."""
    steps = []
    lines = text.replace("\r\n", "\n").split("\n")
    in_ac_section = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if AC_HEADERS.match(stripped):
            in_ac_section = True
            continue
        if in_ac_section or _looks_like_step(stripped):
            step = _normalize_step(stripped)
            if step and len(step) > 2:
                steps.append(step)
    if steps:
        return steps
    for line in lines:
        stripped = line.strip()
        if GIVEN_WHEN_THEN.match(stripped):
            step = _normalize_step(stripped)
            if step:
                steps.append(step)
    if steps:
        return steps
    for line in lines:
        stripped = line.strip()
        if _looks_like_step(stripped):
            step = _normalize_step(stripped)
            if step and len(step) > 2:
                steps.append(step)
    return steps


def _looks_like_step(s):
    """Heuristic: line looks like a test step (bullet, number, or short imperative)."""
    if len(s) < 4:
        return False
    if re.match(r"^[\-\*•]\s+", s) or re.match(r"^\d+[\.\)]\s+", s):
        return True
    if GIVEN_WHEN_THEN.match(s):
        return True
    return False


def _normalize_step(s):
    """Remove bullet/number prefix and trim."""
    s = re.sub(r"^[\-\*•]\s+", "", s.strip())
    s = re.sub(r"^\d+[\.\)]\s+", "", s)
    return s.strip() if s else ""


def _llm_generate_steps(summary, description, subtasks=None, acceptance_criteria=None):
    """Use OpenAI to generate test steps from the full Jira ticket so they cover most of what's there."""
    try:
        from openai import OpenAI
    except ImportError:
        return []
    if not OPENAI_API_KEY:
        return []
    client = OpenAI(api_key=OPENAI_API_KEY)
    subtasks = subtasks or []
    acceptance_criteria = (acceptance_criteria or "").strip()
    body = f"Summary: {summary}\n\nDescription:\n{(description or '')[:2500]}"
    if acceptance_criteria:
        body += f"\n\nAcceptance criteria:\n{acceptance_criteria[:1500]}"
    if subtasks:
        body += "\n\nSubtasks / items to cover:\n" + "\n".join(f"- {s}" for s in subtasks[:20])
    prompt = f"""Given this Jira issue, list concrete manual test steps that cover most of what's in the ticket. Include steps for the main behavior, acceptance criteria if present, and each subtask or listed item where relevant. Output one step per line, short and actionable. No numbering or bullets in the output.

{body}

Test steps (one per line):"""
    try:
        r = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        content = (r.choices[0].message.content or "").strip()
        steps = []
        for line in content.split("\n"):
            step = _normalize_step(line)
            if step and len(step) > 2:
                steps.append(step)
        return steps[:30]
    except Exception:
        return []
