"""Phase 3F acceptance: the whole permission lifecycle through the real API (SYNTHETIC FIXTURE text).

One document is imported, summarised, reviewed and published, then its permission is revoked and restored, the summary
is withdrawn and republished, and finally the source text is purged. At every step the public answer must follow the
current decision at once, and no response may ever carry document text, model output, reviewer or approver names or
notes. This is the end-to-end form of the unit tests for each gate.
"""

import json

from nzstats.research import purge
from nzstats.research import summary_store as ss
from nzstats.sources.artifacts import ArtifactStore

from .conftest import NOW
from .test_purge import APPROVALS, SENTINEL, imported_and_published, inst

PRIVATE = (SENTINEL, "RAW MODEL OUTPUT", "PRIVATE REVIEW NOTE", "Private Reviewer Name", "Private Approver",
           "PRIVATE PUBLICATION NOTE", "Test Owner", "downloaded in a browser", "saved from")  # fmt: skip
ROUTES = ("/api/research/feed", "/api/research/forecasts", "/api/research/summaries/1")


def revoked_display():
    return inst(public_display="none", public_display_approved_by=None, public_display_approved_on=None,
                public_display_note=None)  # fmt: skip


def shown(client) -> bool:
    bodies = [client.get(route) for route in ROUTES]
    for r in bodies:
        assert not [p for p in PRIVATE if p in r.text], f"{r.url} leaked a private value"
    return client.get("/api/research/feed").json()["total"] == 1 and bodies[2].status_code == 200


def test_the_public_answer_follows_each_decision_and_never_leaks(make, tmp_path):
    build, conn = make
    artifacts = ArtifactStore(tmp_path / "data" / "raw")
    version, sid = imported_and_published(conn, artifacts)
    live = {"reg": {"example": inst()}}
    client = build(enabled=True, reg=lambda: live["reg"])

    assert shown(client), "a published, approved, permitted summary is shown"

    live["reg"] = {"example": revoked_display()}  # revocation: the next request already hides it
    assert not shown(client) and client.get("/api/research/summaries/1").status_code == 404
    live["reg"] = {
        "example": inst()
    }  # nothing was deleted: restoring the permission restores the answer
    assert shown(client)

    ss.record_publication(
        conn, sid, decision="withdraw", approver="Private Approver", note="PRIVATE NOTE", now=NOW
    )
    assert not shown(client)  # withdrawal
    ss.record_publication(
        conn, sid, decision="publish", approver="Private Approver", note="PRIVATE NOTE", now=NOW
    )
    assert shown(client)  # republication is a new decision

    backup = tmp_path / "before-purge.db"
    conn.execute("VACUUM INTO ?", (str(backup),))
    plan = purge.plan_purge(conn, "example", acquisition="manual")
    result = purge.apply_purge(conn, plan, artifacts, reason="permission_withdrawn", purged_by="Test Owner",
                               note="licence withdrawn", now=NOW)  # fmt: skip
    assert result.pending == 0 and not shown(client)
    assert client.get("/api/research/summaries/1").status_code == 404
    # Restoring the permission cannot bring purged content back: there is nothing left to show.
    live["reg"] = {"example": inst(**{k: v for k, v in APPROVALS.items() if k == "public_display"})}
    assert not shown(client)
    assert json.loads(client.get("/api/research/feed").text)["items"] == []
    # What a purge cannot do: a backup taken before it still holds the text, so backups must be expired.
    assert SENTINEL.encode() in backup.read_bytes()
