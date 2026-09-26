from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".cursor" / "agent-system.json"
AGENTS_DIR = ROOT / ".cursor" / "agents"
EXPECTED_ROLES = {
    "roadmap-architect": ("grok-4.7-high", True),
    "repo-explorer": ("grok-4.7-high", True),
    "implementer": ("grok-4.7-high", False),
    "checkpoint-reviewer": ("gpt-5.6-terra-medium-fast", True),
    "git-steward": ("gpt-5.6-luna-medium-fast", False),
    "escalation-reviewer": ("gpt-5.6-terra-high-fast", True),
}


def _config() -> dict[str, object]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _frontmatter(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"missing frontmatter: {path}"
    end = lines.index("---", 1)
    values: dict[str, object] = {}
    for line in lines[1:end]:
        if not line.strip() or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = raw.strip()
        if value.lower() in {"true", "false"}:
            values[key.strip()] = value.lower() == "true"
        else:
            values[key.strip()] = value
    return values


def test_agent_system_has_cost_aware_local_limits() -> None:
    config = _config()
    defaults = config["defaults"]
    assert isinstance(defaults, dict)
    assert defaults["local_only"] is True
    assert defaults["remote_agents_enabled"] is False
    assert defaults["max_parallel_writers"] == 1
    assert defaults["max_writer_agents"] == 1
    assert defaults["max_normal_reviewers"] == 1
    assert defaults["max_rework_rounds"] == 2
    assert defaults["max_escalation_reviews"] == 1
    assert defaults["max_full_regression_runs_after_review_go"] == 1
    assert defaults["phase_advance_requires_human"] is True
    assert defaults["external_git_requires_human"] is True
    assert defaults["destructive_scope_requires_human"] is True


def test_role_models_and_agent_frontmatter_match_exactly() -> None:
    config = _config()
    roles = config["roles"]
    assert isinstance(roles, dict)
    assert set(roles) == set(EXPECTED_ROLES)
    assert {path.stem for path in AGENTS_DIR.glob("*.md")} == set(EXPECTED_ROLES)

    for role, (expected_model, expected_readonly) in EXPECTED_ROLES.items():
        role_config = roles[role]
        assert isinstance(role_config, dict)
        assert role_config["model"] == expected_model
        assert role_config["readonly"] is expected_readonly
        frontmatter = _frontmatter(AGENTS_DIR / f"{role}.md")
        assert frontmatter["name"] == role
        assert frontmatter["model"] == expected_model
        assert frontmatter["readonly"] is expected_readonly
        assert frontmatter["is_background"] is False


def test_profile_has_one_product_writer_and_no_expensive_fallback_models() -> None:
    config = _config()
    roles = config["roles"]
    assert isinstance(roles, dict)
    writers = [name for name, role in roles.items() if role.get("product_writer")]
    assert writers == ["implementer"]
    models = [str(role["model"]).lower() for role in roles.values()]
    assert not any("sol" in model for model in models)
    assert not any("composer" in model for model in models)
    review_policy = config["review_policy"]
    assert isinstance(review_policy, dict)
    assert review_policy["automatic_expensive_fallback"] is False
    assert review_policy["unavailable_model_action"] == "ORCHESTRATOR_REVIEW_OR_HUMAN_GATE"


def test_analyzer_governance_is_linked_without_qmtool_harness() -> None:
    agents_guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    governance_rule = (ROOT / ".cursor" / "rules" / "02-agent-governance.mdc").read_text(
        encoding="utf-8"
    )
    governance_doc = (ROOT / "docs" / "AGENT_GOVERNANCE.md").read_text(encoding="utf-8")
    assert "docs/AGENT_GOVERNANCE.md" in agents_guide
    assert ".cursor/agent-system.json" in agents_guide
    assert "docs/AGENT_GOVERNANCE.md" in governance_rule
    assert ".cursor/agent-system.json" in governance_rule
    assert "QMTool" in governance_doc

    forbidden = (
        ROOT / ".cursor" / "hooks",
        ROOT / ".cursor" / "runtime",
        ROOT / ".cursor" / "worktrees.json",
        ROOT / ".cursor" / "tools" / "codex_review_work_package.ps1",
    )
    assert not any(path.exists() for path in forbidden)
