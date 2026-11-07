"""Phase 4V: offline diagnosis and replay of a stored summary (SYNTHETIC FIXTURE).

Reproduces the shape of the Phase 4U finding on synthetic text: a colon vote, a figure compared with a base, a US-dollar price the
contract cannot express, and a decision whose cited clause carries a forward-looking word. The tool opens the database read-only,
re-runs the stored verifier and a proposed one, and reports claim ids, error codes, evidence locations and root-cause clusters.
It prints no source text or model output unless asked, and it changes nothing.
"""

import dataclasses
import json
import sqlite3

import pytest

from nzstats.research.diagnostics import (
    CASCADE_GUARANTEED,
    LABELS,
    DiagnosticError,
    cascade_clusters,
    open_readonly,
    render_html,
    replay_summary,
)

from .diag_support import SECRET, store_verify_4_summary


@pytest.fixture()
def stored(conn):
    return store_verify_4_summary(conn)


def snapshot(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(r) for r in conn.execute("SELECT * FROM research_summary ORDER BY id")]


# --- the fixture really has the shapes the tool is meant to explain -------------------------------------------
def test_the_stored_summary_fails_verify_4_in_the_phase_4u_shapes(stored):
    _, _, report = stored
    errors = {(p.path, p.code) for p in report.errors}
    assert ("decisions[0]", "vote_not_in_evidence") in errors
    assert ("facts[0]", "period_not_supported") in errors
    assert ("facts[1]", "missing_unit") in errors
    assert ("decisions[1]", "decision_not_in_evidence") in errors


# --- replay ---------------------------------------------------------------------------------------------------
def test_replay_compares_the_stored_verifier_with_the_proposed_one_claim_by_claim(stored):
    conn, sid, _ = stored
    replay = replay_summary(conn, sid)
    assert (replay.baseline.version, replay.proposed.version) == ("verify-4", "verify-5")
    assert (
        replay.stored_verifier == "verify-4"
        and replay.stored_reproduced is True
        and replay.output_hash_ok is True
    )
    assert set(replay.newly_accepted) == {"decisions[0]", "facts[0]"}
    assert replay.newly_rejected == ()
    assert (
        replay.baseline.errors["vote_not_in_evidence"] == 1
        and "vote_not_in_evidence" not in replay.proposed.errors
    )
    assert replay.baseline.claims_failed > replay.proposed.claims_failed


def test_the_remaining_failures_are_kept_and_labelled_never_called_valid(stored):
    conn, sid, _ = stored
    replay = replay_summary(conn, sid)
    labels = {(f.path, f.code): f.label for f in replay.findings}
    assert labels[("decisions[0]", "vote_not_in_evidence")] == "resolved_by_proposed"
    assert labels[("facts[0]", "period_not_supported")] == "resolved_by_proposed"
    assert labels[("facts[1]", "missing_unit")] == "contract_limitation"
    assert labels[("decisions[1]", "decision_not_in_evidence")] == "conservative_failure"
    assert set(labels.values()) <= set(LABELS)
    assert not any("valid" in label and "invalid" not in label for label in LABELS)
    still = [f for f in replay.findings if f.label != "resolved_by_proposed"]
    assert {f.code for f in still} >= {"missing_unit", "decision_not_in_evidence"}


def test_the_cascade_of_a_failed_decision_is_grouped_under_its_root(stored):
    conn, sid, _ = stored
    replay = replay_summary(conn, sid)
    (cluster,) = [c for c in replay.clusters if c.root == "decision_not_in_evidence"]
    assert cluster.path == "decisions[1]"
    assert set(cluster.guaranteed) == {"decision_instrument_not_supported", "decision_rate_not_supported",
                                       "decision_action_not_supported"}  # fmt: skip
    assert set(cluster.guaranteed) <= CASCADE_GUARANTEED
    labels = {(f.path, f.code): f.label for f in replay.findings}
    assert labels[("decisions[1]", "decision_rate_not_supported")] == "cascade"
    assert (
        replay.root_causes_baseline < replay.baseline.n_errors
    )  # fewer independent causes than errors


def test_claim_ids_carry_evidence_locations_without_text(stored):
    conn, sid, _ = stored
    replay = replay_summary(conn, sid)
    claim = next(c for c in replay.claims if c.path == "facts[0]")
    (site,) = claim.evidence
    assert (site.section, site.page) == (1, 2)
    assert site.start is not None and site.end is not None and site.sentence == 1
    assert (
        claim.kind == "fact"
        and claim.baseline_errors == ("period_not_supported",)
        and claim.proposed_errors == ()
    )


def test_replay_changes_nothing_and_opens_nothing_for_writing(stored):
    conn, sid, _ = stored
    before = snapshot(conn)
    replay_summary(conn, sid)
    assert snapshot(conn) == before


def test_the_read_only_opener_refuses_writes(stored, tmp_path):
    conn, sid, _ = stored
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    ro = open_readonly(path)
    assert replay_summary(ro, sid).stored_reproduced is True
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("UPDATE research_summary SET status = 'verified'")


def test_a_missing_or_unusable_summary_is_a_clear_error(stored):
    conn, sid, _ = stored
    with pytest.raises(DiagnosticError, match="no stored summary"):
        replay_summary(conn, sid + 99)
    with pytest.raises(DiagnosticError, match="unknown verifier"):
        replay_summary(conn, sid, proposed="verify-99")


# --- the report -------------------------------------------------------------------------------------------------
def test_the_html_report_holds_codes_and_locations_but_no_source_text_by_default(stored):
    conn, sid, _ = stored
    html = render_html(replay_summary(conn, sid))
    for needle in (SECRET, "Brent crude", "Monetary Policy Committee", "US$82", "Annual CPI"):
        assert needle not in html
    for needle in ("facts[0]", "decisions[0]", "vote_not_in_evidence", "period_not_supported", "verify-4", "verify-5",
                   "cascade", "contract_limitation"):  # fmt: skip
        assert needle in html
    assert "<script" not in html.lower() and "http://" not in html and "https://" not in html
    assert "Content-Security-Policy" in html


def test_text_is_absent_from_the_replay_itself_unless_asked_for(stored):
    conn, sid, _ = stored
    plain = replay_summary(conn, sid)
    assert all(c.text is None and c.quotes == () for c in plain.claims)
    with_text = replay_summary(conn, sid, with_text=True)
    assert any(c.text and c.quotes for c in with_text.claims)
    assert SECRET not in json.dumps(plain.to_json()) and "Brent" not in json.dumps(plain.to_json())


def test_the_html_report_can_include_text_for_the_owner_and_escapes_it(stored):
    conn, sid, _ = stored
    replay = replay_summary(conn, sid, with_text=True)
    assert "Brent crude averaged" in render_html(replay)
    hostile = dataclasses.replace(
        replay,
        claims=tuple(
            dataclasses.replace(c, text="<script>alert(1)</script>") for c in replay.claims
        ),
    )
    page = render_html(hostile)
    assert (
        "<script>alert(1)</script>" not in page
        and "&lt;script&gt;" in page
        and "<script" not in page.lower()
    )


def test_the_report_states_what_it_is_not(stored):
    conn, sid, _ = stored
    html = render_html(replay_summary(conn, sid))
    assert (
        "not a check of economic accuracy" in html.lower()
        or "does not test the economics" in html.lower()
    )
    assert "new assessment" in html.lower()


# --- the cascade rule itself, against the real verifier -----------------------------------------------------------
def test_a_failed_decision_wording_always_brings_the_three_guaranteed_cascade_errors(stored):
    _, _, report = stored
    at = {p.code for p in report.errors if p.path == "decisions[1]"}
    assert {"decision_not_in_evidence", *CASCADE_GUARANTEED} <= at


def test_cascade_clusters_are_computed_from_codes_alone():
    problems = [("decisions[2]", c) for c in
                ("decision_not_in_evidence", "decision_instrument_not_supported", "decision_rate_not_supported",
                 "decision_action_not_supported", "decision_date_not_supported", "vote_not_in_evidence")]  # fmt: skip
    (cluster,) = cascade_clusters(problems)
    assert cluster.root == "decision_not_in_evidence"
    assert set(cluster.guaranteed) == CASCADE_GUARANTEED and cluster.possible == (
        "decision_date_not_supported",
    )
    assert cascade_clusters([("decisions[0]", "vote_not_in_evidence")]) == ()
    assert (
        cascade_clusters([("decisions[0]", "decision_rate_not_supported")]) == ()
    )  # a cascade code with no root is its own cause


# --- found by the independent review: the report path must never become a way to overwrite a file ---------------------
def test_a_report_is_written_inside_the_data_directory_owner_only(tmp_path):
    from nzstats.research.diagnostics import write_report

    root = tmp_path / "data"
    target = root / "diag" / "r.html"
    write_report(target, "<title>Offline diagnostic, summary 1</title>", root=root)
    assert (
        target.read_text().startswith("<title>Offline") and (target.stat().st_mode & 0o777) == 0o600
    )
    write_report(
        target, "<title>Offline diagnostic, summary 2</title>", root=root
    )  # replacing a previous report is fine
    assert "summary 2" in target.read_text()


@pytest.mark.parametrize("name", ["../outside.html", "nzstats.db", "notes.txt", "x"])
def test_a_report_path_outside_the_directory_or_not_html_is_refused(tmp_path, name):
    from nzstats.research.diagnostics import write_report

    root = tmp_path / "data"
    root.mkdir()
    victim = (root / name).resolve()
    with pytest.raises(DiagnosticError, match="refused"):
        write_report(root / name, "x", root=root)
    assert not victim.exists()


def test_a_report_never_follows_a_symlink_or_replaces_a_file_that_is_not_a_report(tmp_path):
    from nzstats.research.diagnostics import write_report

    root = tmp_path / "data"
    root.mkdir()
    precious = root / "precious.html"
    precious.write_text("KEEP ME")
    with pytest.raises(DiagnosticError, match="refused"):
        write_report(
            precious, "<title>Offline diagnostic</title>", root=root
        )  # an existing file that is not our report
    assert precious.read_text() == "KEEP ME"
    link = root / "link.html"
    link.symlink_to(precious)
    with pytest.raises(DiagnosticError, match="refused"):
        write_report(link, "<title>Offline diagnostic</title>", root=root)
    assert precious.read_text() == "KEEP ME"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "dir").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(DiagnosticError, match="refused"):
        write_report(root / "dir" / "r.html", "x", root=root)
    assert list(elsewhere.iterdir()) == []


def test_an_unreadable_stored_date_is_a_clear_error_that_does_not_quote_it(conn):
    from nzstats.research.contract import ModelProvenance  # noqa: F401  (builds the same stored shape as the fixture)

    conn_, sid, _ = store_verify_4_summary(conn)
    with conn_:
        conn_.execute("UPDATE research_publication SET published_on = 'NOT-A-DATE-SECRET'")
    with pytest.raises(DiagnosticError) as excinfo:
        replay_summary(conn_, sid)
    assert "SECRET" not in str(excinfo.value) and "date" in str(excinfo.value)
