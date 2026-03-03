from click.testing import CliRunner

from harness.verify import app


def test_db_migrate_invokes_migration_runner(monkeypatch):
    called = {}

    def _fake_run_migrations(revision="head", db_url=None, db_path=None):
        called["revision"] = revision
        called["db_url"] = db_url
        called["db_path"] = db_path

    monkeypatch.setattr("harness.verify.run_migrations", _fake_run_migrations)

    runner = CliRunner()
    result = runner.invoke(app, ["db", "migrate", "--db-path", "/tmp/harness-test.duckdb"])

    assert result.exit_code == 0, result.output
    assert called["revision"] == "head"
    assert called["db_path"] == "/tmp/harness-test.duckdb"
    assert called["db_url"].startswith("duckdb:///")

