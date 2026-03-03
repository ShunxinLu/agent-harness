import json
from pathlib import Path

from harness.session_manager import collect_resume_context


def test_collect_resume_context_reports_missing_artifacts(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()

    context = collect_resume_context(project_root=project, run_smoke_check=False)
    assert context["has_required_artifacts"] is False
    assert len(context["missing_artifacts"]) == 3
    assert context["smoke_check"]["requested"] is False


def test_collect_resume_context_runs_smoke_check_when_available(tmp_path: Path):
    project = tmp_path / "repo"
    harness_dir = project / ".harness"
    harness_dir.mkdir(parents=True)

    (harness_dir / "progress.md").write_text("# progress\n- baseline\n")
    (harness_dir / "feature_list.json").write_text(
        json.dumps(
            {
                "version": 1,
                "features": [
                    {
                        "id": "FEAT-1",
                        "category": "impl",
                        "description": "feature",
                        "priority": "high",
                        "steps": [],
                        "passes": False,
                        "last_verified_at": None,
                        "evidence": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    init_script = harness_dir / "init.sh"
    init_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho smoke-ok\n")
    init_script.chmod(init_script.stat().st_mode | 0o111)

    context = collect_resume_context(project_root=project, run_smoke_check=True)
    assert context["has_required_artifacts"] is True
    assert context["missing_artifacts"] == []
    assert context["next_feature"]["id"] == "FEAT-1"
    assert context["smoke_check"]["requested"] is True
    assert context["smoke_check"]["executed"] is True
    assert context["smoke_check"]["exit_code"] == 0
    assert "smoke-ok" in "\n".join(context["smoke_check"]["output_tail"])

