"""Structural guards for the decision-gate ROUTE (#6).

The decision gate is the moat: it must keep REJECTing unverifiable work even as it routes one-time missions.
These tests are deliberately about *structure*, not prose — they fail loudly if a future edit drops the
hard REJECT verdict or the routing table, so the gate can't silently turn into a rubber stamp.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DG = (ROOT / "references" / "decision-gate.md").read_text(encoding="utf-8")
DG_L = DG.lower()
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
SKILL_L = SKILL.lower()


def test_tier0_gate_preserved():
    # The 4 conditions remain the entry test.
    assert "The 4 conditions" in DG
    for cond in ("recurs", "objective gate", "budget", "agent can run"):
        assert cond in DG_L, f"Tier-0 condition missing: {cond}"


def test_hard_reject_verdict_is_the_moat():
    # Unverifiable/unsafe work must still hard reject and recommend an honest alternative.
    assert "hard reject" in DG_L
    assert "human-reviewed task" in DG_L or "human-gated" in DG_L
    assert "one high-quality pass" in DG_L or "single high-quality pass" in DG_L
    assert "no external gate" in DG_L or "no objective gate" in DG_L


def test_route_branch_present_for_all_archetypes():
    assert "route" in DG_L
    for archetype in ("mission / goal run", "ratchet", "critic-panel", "checkpoint", "budget", "quorum"):
        assert archetype in DG_L, f"route table does not cover: {archetype}"


def test_one_time_missions_are_not_collapsed_to_reject():
    assert "not a reusable loop blueprint" in DG_L
    assert "single verified pass" in DG_L
    assert "recurrence is the reusable" in DG_L
    assert "not the whole outcome-orchestration test" in DG_L
    assert "routes to mission / goal-run or single-pass below" in SKILL
    assert "is single-pass mode below" not in SKILL


def test_capability_readiness_is_in_pipeline_route():
    pipeline = (ROOT / "references" / "pipeline.md").read_text(encoding="utf-8").lower()
    assert "local capability readiness inventory" in pipeline
    for surface in ("skills", "plugins", "connectors", "mcps", "agents", "data sources"):
        assert surface in pipeline, f"capability inventory missing: {surface}"
    assert "route.md" in pipeline
    assert "mission.yaml" in pipeline


def test_route_expands_pass_set_without_lowering_the_bar():
    # The strategic claim must be explicit so it can't drift: archetypes expand what passes, the bar is unchanged.
    assert "without lowering the bar" in DG_L
    assert "bar is unchanged" in DG_L or "never waves a task through" in DG_L


def test_skill_routes_on_pass_and_pins_shape():
    # Step 1 routes on Pass; Step 4 pins the verifier shape/kind, not just a work pattern.
    assert "route" in SKILL_L
    assert "mission / goal-run" in SKILL_L
    assert "verifier.shape" in SKILL or "verifier.kind" in SKILL
    assert "orthogonal" in SKILL_L  # the axis discipline is stated in the wizard


def test_skill_branches_non_reusable_routes_before_loop_artifacts():
    # Mission/single-pass routes must not fall through into LoopPrint package generation.
    branch_idx = SKILL.index("Immediately branch on the selected route")
    profile_idx = SKILL.index("Reusable-loop Profile Selection")
    artifact_idx = SKILL.index("Reusable-loop Artifact Generation")
    assert branch_idx < profile_idx < artifact_idx

    mission_idx = SKILL.index("Mission / Goal Run route")
    single_pass_idx = SKILL.index("Single Verified Pass route")
    assert branch_idx < mission_idx < profile_idx
    assert branch_idx < single_pass_idx < profile_idx
    assert "Mission / Goal Run route:** do **not** continue to loop profile or artifact generation" in SKILL
    assert "Single Verified Pass route:** do **not** continue to loop profile or artifact generation" in SKILL
    assert "Mission / Goal Run route" in SKILL and "continue to Stage 3 Plan" in SKILL
    assert "mission.yaml" in SKILL and "looptimal-lint.txt" in SKILL
    assert "Single Verified Pass route" in SKILL and "follow the `single-pass` Degrade path" in SKILL
    assert "Never resume across a hard REJECT" in SKILL


def test_one_shot_shortcut_does_not_bypass_mission_decision():
    one_time_line = next(
        line for line in SKILL.splitlines() if "Explicit one-time delivery language" in line
    )
    assert '"one-shot"' in one_time_line
    assert '"just do X once"' in one_time_line
    assert '"build/fix/ship this once"' in one_time_line
    assert "full pipeline so the Decision Gate can choose mission / goal-run vs single-pass" in one_time_line

    single_pass_line = next(
        line for line in SKILL.splitlines() if "Explicit one-shot language that also rules out useful retries" in line
    )
    assert '"single pass"' in single_pass_line
    assert '"no retry loop needed"' in single_pass_line
    assert "single-pass directly" in single_pass_line


def test_mission_package_is_stage3_gated_before_simulate():
    pipeline = (ROOT / "references" / "pipeline.md").read_text(encoding="utf-8")
    stage2_outputs = pipeline.split("## Stage 3 — Plan", 1)[0].split("### Outputs / artifacts", 1)[1]
    stage3_gate = pipeline.split("### GATE → Stage 4", 1)[1].split("## Stage 4 — Simulate", 1)[0]

    assert "`mission.yaml`" not in stage2_outputs
    assert "Mission / Goal Run routes have `mission.yaml`" in stage3_gate
    assert "`looptimal-lint` GREEN before Simulate" in stage3_gate
