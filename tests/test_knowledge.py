"""Knowledge packs (P3-T2): front matter, BM25 search over paragraphs, the top passages in the
worker's brief with the pack mounted read-only at /knowledge, the pack in the role's revision,
and a staleness warning for facts not rechecked in 180 days."""
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from builder import knowledge, team
from builder.brains import Selection
from builder.contracts import BuilderError
from builder.providers import worker_prompt
from builder.sandbox import agent_job
import test_agent_foundation as foundation

TODAY = date.today().isoformat()


def page(body, **meta):
    fields = {"title": "CSRF and Origin", "tags": "[security, web]", "last_checked": TODAY,
              "sources": "[https://owasp.org/www-community/attacks/csrf]", "licence": "none quoted"}
    fields.update(meta)
    head = "".join(f"{key}: {value}\n" for key, value in fields.items() if value is not None)
    return f"---\n{head}---\n{body}"


CORPUS = {
    "csrf.md": page("# CSRF and Origin\n\nA state-changing request from another site rides the user's cookie. "
                    "Check the Origin header against an allow list and require a CSRF token.\n\n"
                    "## Cookies\n\nSet SameSite=Lax on session cookies; it is defence in depth, not the fix.\n"),
    "queries.md": page("# Query performance\n\n## N+1 queries\n\nA loop that runs one query per row "
                       "multiplies round trips. Batch the rows with one query and a join.\n\n"
                       "Paginate every list endpoint so input stays bounded.\n",
                       title="Query performance", tags="[performance]"),
    "logs.md": page("# Logging\n\nNever write tokens, passwords or session cookies to logs.\n",
                    title="Logging", tags="[security]"),
}


class FrontMatterTests(unittest.TestCase):
    def test_a_valid_page_parses_inline_and_block_lists(self):
        meta, body = knowledge.front_matter(CORPUS["csrf.md"], "csrf.md")
        self.assertEqual(meta["title"], "CSRF and Origin")
        self.assertEqual(meta["tags"], ["security", "web"])
        self.assertEqual(meta["last_checked"], date.today())
        self.assertEqual(meta["sources"], ["https://owasp.org/www-community/attacks/csrf"])
        self.assertTrue(body.startswith("# CSRF and Origin"))
        block = page("Body\n", sources="\n  - https://a.example/one\n  - https://b.example/two")
        self.assertEqual(knowledge.front_matter(block, "b.md")[0]["sources"],
                         ["https://a.example/one", "https://b.example/two"])

    def test_each_missing_or_bad_field_is_refused_with_the_file_and_field(self):
        cases = {
            "title": page("x", title=None), "tags": page("x", tags="[]"),
            "last_checked": page("x", last_checked="21 Nov 2026"),
            "sources": page("x", sources="[ftp://example.com/a]"), "licence": page("x", licence=""),
        }
        for field, text in cases.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(BuilderError, f"bad.md.*{field}"):
                    knowledge.front_matter(text, "bad.md")
        with self.assertRaisesRegex(BuilderError, "bad.md.*front matter"):
            knowledge.front_matter("# No front matter\n", "bad.md")
        with self.assertRaisesRegex(BuilderError, "bad.md.*unknown"):
            knowledge.front_matter(page("x", owner="me"), "bad.md")
        with self.assertRaisesRegex(BuilderError, "bad.md.*future"):
            knowledge.front_matter(page("x", last_checked=(date.today() + timedelta(days=3)).isoformat()), "bad.md")

    def test_a_date_a_day_or_two_ahead_is_a_time_zone_not_the_future(self):
        # Review of PR #57: the author's "today" is tomorrow for a runner behind them.
        for days in (1, 2):
            ahead = (date.today() + timedelta(days=days)).isoformat()
            self.assertEqual(knowledge.front_matter(page("x", last_checked=ahead), "a.md")[0]["last_checked"],
                             date.fromisoformat(ahead))

    def test_a_pack_folder_is_read_sorted_and_refuses_links_and_bad_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "qa").mkdir()
            for name, text in CORPUS.items():
                (root / "qa" / name).write_text(text)
            (root / "qa" / "notes.txt").write_text("ignored")
            self.assertEqual(list(knowledge.pack("qa", root)), ["csrf.md", "logs.md", "queries.md"])
            self.assertEqual(knowledge.pack("designer", root), {})  # no pack: no files
            (root / "qa" / "link.md").symlink_to(root / "qa" / "csrf.md")
            with self.assertRaisesRegex(BuilderError, "link.md"):
                knowledge.pack("qa", root)
            (root / "qa" / "link.md").unlink()
            (root / "qa" / "broken.md").write_text("no front matter")
            with self.assertRaisesRegex(BuilderError, "broken.md"):
                knowledge.pack("qa", root)


class SearchTests(unittest.TestCase):
    def test_paragraphs_carry_their_file_and_heading(self):
        found = knowledge.passages(CORPUS)
        self.assertIn({"file": "csrf.md", "heading": "Cookies",
                       "text": "Set SameSite=Lax on session cookies; it is defence in depth, not the fix."}, found)
        self.assertFalse(any(item["text"].startswith("#") or item["text"].startswith("title:") for item in found))

    def test_the_best_paragraph_ranks_first_and_unrelated_ones_are_left_out(self):
        hits = knowledge.search(CORPUS, "check the Origin header for CSRF")
        self.assertEqual((hits[0]["file"], hits[0]["heading"]), ("csrf.md", "CSRF and Origin"))
        self.assertTrue(all(hit["score"] > 0 for hit in hits))
        self.assertNotIn("queries.md", [hit["file"] for hit in hits])
        top = knowledge.search(CORPUS, "N+1 query per row in a loop")[0]
        self.assertEqual((top["file"], top["heading"]), ("queries.md", "N+1 queries"))
        self.assertEqual(knowledge.search(CORPUS, "kubernetes helm"), [])
        self.assertEqual(knowledge.search(CORPUS, ""), [])
        self.assertEqual(len(knowledge.search(CORPUS, "cookies session logs query", limit=2)), 2)

    def test_rare_terms_outweigh_common_ones(self):
        # "cookies" is in two files, "samesite" in one: the SameSite paragraph wins.
        top = knowledge.search(CORPUS, "samesite cookies")[0]
        self.assertEqual(top["heading"], "Cookies")

    def test_ranking_is_deterministic(self):
        self.assertEqual(knowledge.search(CORPUS, "session cookies"), knowledge.search(dict(reversed(CORPUS.items())),
                                                                                        "session cookies"))


def contract_and_job(role="backend", goal="Add an Origin check against CSRF"):
    contract = {"title": "T", "delivery": "patch", "checks": [], "jobs": [],
                "requirements": [{"id": "R", "description": "d", "checks": ["G"]}]}
    return contract, {"id": "J", "role": role, "goal": goal, "paths": ["a.py"], "checks": ["G"]}


class PromptTests(unittest.TestCase):
    def brief(self, specialist, **options):
        contract, job = contract_and_job()
        with mock.patch("builder.providers.reviewed_text", return_value=""):
            return worker_prompt(contract, job, None, {}, None, specialist=specialist, **options)

    def test_the_top_passages_for_the_goal_and_the_pack_path_are_in_the_brief(self):
        specialist = {**team.profile("backend"), "knowledge": CORPUS}
        brief = self.brief(specialist, knowledge_path="/knowledge")
        self.assertIn("Knowledge passages", brief)
        self.assertIn("csrf.md > CSRF and Origin", brief)
        self.assertIn("Check the Origin header against an allow list", brief)
        self.assertIn("Knowledge packs for every role, as approved for this run, are read-only in /knowledge/",
                      brief)
        section = brief[brief.index("Knowledge passages"):brief.index("Knowledge packs for every role")]
        self.assertLessEqual(section.count("\n- "), knowledge.PROMPT_PASSAGES)

    def test_at_most_five_passages_and_none_without_a_pack(self):
        many = {f"p{n}.md": page(f"# Origin {n}\n\nOrigin check number {n} for CSRF.\n") for n in range(9)}
        brief = self.brief({**team.profile("backend"), "knowledge": many}, knowledge_path="/knowledge")
        self.assertEqual(knowledge.PROMPT_PASSAGES, 5)
        self.assertEqual(brief.count("Origin check number"), 5)
        self.assertNotIn("Knowledge passages", self.brief(team.profile("backend")))
        unrelated = {"x.md": page("# Fonts\n\nPick two typefaces.\n")}
        self.assertNotIn("Knowledge passages", self.brief({**team.profile("backend"), "knowledge": unrelated},
                                                          knowledge_path="/knowledge"))

    def test_a_role_without_a_pack_still_learns_where_the_packs_are(self):
        # Review of PR #57: a backend worker can read the reviewer's failure catalogue too.
        brief = self.brief(team.profile("backend"), knowledge_path="/knowledge")
        self.assertNotIn("Knowledge passages", brief)
        self.assertIn("read-only in /knowledge/", brief)
        self.assertNotIn("/knowledge", self.brief(team.profile("backend")))

    def test_the_reviewer_prompt_names_the_packs_only_when_mounted(self):
        from builder.review_gate import prompt
        packet = {"attempt_id": "a", "base_digest": "b", "candidate_digest": "c", "checks": []}
        self.assertIn("read-only in /knowledge/", prompt(team.profile("reviewer"), packet, "/knowledge"))
        self.assertNotIn("/knowledge", prompt(team.profile("reviewer"), packet))

    def test_the_sandbox_mounts_the_pack_read_only_at_knowledge(self):
        with tempfile.TemporaryDirectory() as temp:
            job = agent_job("worker", ("claude",), Path(temp), knowledge=Path(temp) / "knowledge")
            self.assertIn((Path(temp) / "knowledge", "/knowledge", True), job.mounts)
            self.assertNotIn("/knowledge", [target for _, target, _ in agent_job("worker", ("claude",),
                                                                                 Path(temp)).mounts])


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.team = Path(self.temp.name) / "team"
        shutil.copytree(team.ROOT, self.team)
        patcher = mock.patch.object(team, "ROOT", self.team)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_pack_file_change_changes_the_role_revision(self):
        before = team.profile("qa")
        self.assertTrue(before["knowledge"])
        name = sorted(before["knowledge"])[0]
        path = self.team / "knowledge" / "qa" / name
        path.write_text(path.read_text() + "\nOne more line.\n")
        after = team.profile("qa")
        self.assertNotEqual(before["revision"], after["revision"])
        self.assertIn("One more line.", after["knowledge"][name])
        self.assertEqual(after["knowledge"][name], path.read_text())

    def test_a_role_without_a_pack_keeps_its_revision(self):
        # The approved Pocket Todo plan names the technical-lead revision (verify-facts.sh).
        before = team.profile("technical-lead")
        self.assertNotIn("knowledge", before)
        (self.team / "knowledge" / "designer").mkdir(parents=True, exist_ok=True)
        (self.team / "knowledge" / "designer" / "a.md").write_text(CORPUS["logs.md"])
        self.assertEqual(team.profile("technical-lead")["revision"], before["revision"])
        self.assertIn("a.md", team.profile("designer")["knowledge"])

    def test_the_frozen_team_binds_every_pack(self):
        contract = {"team": 1, "jobs": [{"id": "J", "role": "backend", "paths": ["a.py"], "checks": []}]}
        frozen = team.freeze_team(contract)
        self.assertEqual(frozen["reviewer"]["knowledge"], knowledge.pack("reviewer", self.team / "knowledge"))
        # The whole team/knowledge/ tree, as approved, for the /knowledge mount (item 3).
        self.assertEqual(frozen["knowledge"], knowledge.tree(self.team / "knowledge"))
        self.assertGreaterEqual(set(frozen["knowledge"]), {"qa", "reviewer"})
        shutil.rmtree(self.team / "knowledge")
        self.assertNotIn("knowledge", team.freeze_team(contract))

    def test_the_tree_refuses_a_linked_pack_folder(self):
        (self.team / "knowledge" / "designer").symlink_to(self.team / "knowledge" / "qa")
        with self.assertRaisesRegex(BuilderError, "designer"):
            knowledge.tree(self.team / "knowledge")


class ShippedPackTests(unittest.TestCase):
    def test_every_pack_file_has_valid_front_matter(self):
        roles = sorted(path.name for path in (team.ROOT / "knowledge").iterdir() if path.is_dir())
        self.assertGreaterEqual(set(roles), {"qa", "reviewer"})
        for role in roles:
            self.assertIn(role, team.PROFILES)
            self.assertTrue(knowledge.pack(role))

    def test_stale_pack_files_warn(self):
        # Warning only for now (P3-T2): a fact not rechecked in 180 days should be rechecked.
        stale = knowledge.stale(team.ROOT / "knowledge")
        for name, checked in stale:
            warnings.warn(f"knowledge pack {name}: last_checked {checked} is older than "
                          f"{knowledge.STALE_DAYS} days; recheck it", stacklevel=1)
        old = (date.today() - timedelta(days=knowledge.STALE_DAYS + 1)).isoformat()
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "qa").mkdir()
            (Path(temp) / "qa" / "old.md").write_text(page("x", last_checked=old))
            (Path(temp) / "qa" / "new.md").write_text(page("x"))
            self.assertEqual(knowledge.stale(Path(temp)), [("qa/old.md", old)])

    def test_the_first_content_covers_the_plan(self):
        qa = " ".join(knowledge.pack("qa").values()).lower()
        for topic in ("test pyramid", "scenario", "flaky", "accessibility", "core web vitals", "test data",
                      "can fail"):
            self.assertIn(topic, qa)
        reviewer = " ".join(knowledge.pack("reviewer").values()).lower()
        for topic in ("object ownership", "injection", "csrf", "origin", "secrets", "race", "idempoten", "n+1",
                      "unbounded", "error", "stale", "accessibility", "google.github.io/styleguide/go",
                      "google.github.io/styleguide/tsguide"):
            self.assertIn(topic, reviewer)
        hits = knowledge.search(knowledge.pack("reviewer"), "CSRF Origin check on a cookie session")
        self.assertTrue(hits)
        self.assertIn("csrf", (hits[0]["heading"] + hits[0]["text"]).lower())


class CommandTests(unittest.TestCase):
    def test_kb_search_prints_passages_with_file_and_heading(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "kb", "search", "--role",
                                 "reviewer", "CSRF Origin header"], capture_output=True, text=True, check=True)
        found = json.loads(result.stdout)
        self.assertEqual(found["role"], "reviewer")
        self.assertTrue(1 <= len(found["passages"]) <= 5)
        self.assertTrue(all({"file", "heading", "text", "score"} <= set(item) for item in found["passages"]))
        none = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "kb", "search", "--role",
                               "designer", "anything"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(none.stdout)["passages"], [])
        bad = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "kb", "search", "--role",
                              "nobody", "x"], capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)


class RunTests(unittest.TestCase):
    """A launched worker gets the passages and a read-only copy of its role's frozen pack."""
    setUp = foundation.DepthRuleTests.setUp
    write = foundation.DepthRuleTests.write
    report = foundation.DepthRuleTests.report
    stand_in = foundation.DepthRuleTests.stand_in
    approve_skip = foundation.DepthRuleTests.approve_skip
    run_once = foundation.DepthRuleTests.run_once

    def test_the_brief_has_the_passages_and_the_attempt_keeps_the_frozen_pack(self):
        fake = Path(self.temp.name) / "team"
        shutil.copytree(team.ROOT, fake)
        (fake / "knowledge" / "backend").mkdir(parents=True)
        (fake / "knowledge" / "backend" / "versions.md").write_text(page(
            "# Stale writes\n\nCompare the stored version on every stale write and refuse an old one.\n",
            title="Stale writes"))
        with mock.patch.object(team, "ROOT", fake):
            bin_dir = self.stand_in()
            self.approve_skip()
        # Edits after approval do not reach the run: it uses the frozen pack.
        (fake / "knowledge" / "backend" / "versions.md").write_text("changed")
        self.run_once()
        brief = (bin_dir / "brief.md").read_text()
        self.assertIn("Knowledge passages", brief)
        self.assertIn("refuse an old one", brief)
        attempt = self.runner.state()["attempts"][0]
        packs = self.runner.attempt_dir(attempt) / "knowledge"
        copy = packs / "backend" / "versions.md"
        self.assertIn("refuse an old one", copy.read_text())
        self.assertFalse(stat.S_IMODE(copy.stat().st_mode) & 0o222)
        self.assertTrue((packs / "reviewer" / "failure-modes.md").is_file())  # every role's pack
        self.assertIn(f"read-only in {packs}/", brief)  # on the host the brief names the host copy
        # The launched reviewer is told where the packs are; they sit outside its review copy.
        self.assertIn("Knowledge packs for every role", (bin_dir / "review.md").read_text())


if __name__ == "__main__":
    unittest.main()
