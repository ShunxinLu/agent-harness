import json
from pathlib import Path

from agent_harness.session_manager import get_next_feature, update_feature_status


def _write_feature_ledger(project_root: Path, payload: dict):
    harness_dir = project_root / ".harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "feature_list.json").write_text(json.dumps(payload, indent=2) + "\n")


def test_get_next_feature_uses_priority_and_pending_status(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    _write_feature_ledger(
        project,
        {
            "version": 1,
            "features": [
                {
                    "id": "FEAT-LOW",
                    "category": "impl",
                    "description": "low priority pending",
                    "priority": "low",
                    "steps": [],
                    "passes": False,
                    "last_verified_at": None,
                    "evidence": [],
                },
                {
                    "id": "FEAT-HIGH",
                    "category": "impl",
                    "description": "high priority pending",
                    "priority": "high",
                    "steps": [],
                    "passes": False,
                    "last_verified_at": None,
                    "evidence": [],
                },
                {
                    "id": "FEAT-DONE",
                    "category": "impl",
                    "description": "already done",
                    "priority": "high",
                    "steps": [],
                    "passes": True,
                    "last_verified_at": "2026-03-03T00:00:00+00:00",
                    "evidence": ["run:abc"],
                },
            ],
        },
    )

    feature = get_next_feature(project)
    assert feature is not None
    assert feature.id == "FEAT-HIGH"


def test_update_feature_status_requires_evidence_for_pass(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    _write_feature_ledger(
        project,
        {
            "version": 1,
            "features": [
                {
                    "id": "FEAT-1",
                    "category": "impl",
                    "description": "feature",
                    "priority": "medium",
                    "steps": [],
                    "passes": False,
                    "last_verified_at": None,
                    "evidence": [],
                }
            ],
        },
    )

    try:
        update_feature_status(project, "FEAT-1", passes=True, evidence=[])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "without evidence" in str(exc)


def test_update_feature_status_sets_and_clears_verification_metadata(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    _write_feature_ledger(
        project,
        {
            "version": 1,
            "features": [
                {
                    "id": "FEAT-2",
                    "category": "impl",
                    "description": "feature",
                    "priority": "medium",
                    "steps": [],
                    "passes": False,
                    "last_verified_at": None,
                    "evidence": [],
                }
            ],
        },
    )

    passed = update_feature_status(
        project_root=project,
        feature_id="FEAT-2",
        passes=True,
        evidence=["run:session-123"],
    )
    assert passed.passes is True
    assert passed.last_verified_at is not None
    assert passed.evidence == ["run:session-123"]

    failed = update_feature_status(
        project_root=project,
        feature_id="FEAT-2",
        passes=False,
        evidence=[],
    )
    assert failed.passes is False
    assert failed.last_verified_at is None
    assert failed.evidence == []

