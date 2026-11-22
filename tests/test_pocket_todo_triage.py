"""P3-T3b: P2-G's accepted findings are folded into the Pocket Todo fixture's gates.

Every finding the owner accepted in the four P2-G Pocket Todo runs (exported to
`p2g-accepted-findings.json`) is triaged exactly once in `findings-triage.md`: a **check** names the
gate assertion that now catches it, **covered** names the assertion that already did, and a **risk**
cites the decision or plan item that keeps it out of the gates. The plan's two failure-path matrices
(`plan/acceptance.md` and `planning.json`'s `failure_paths`) stay row for row in step."""
from collections import Counter
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs" / "plan" / "fixtures" / "pocket-todo"
TRIAGE = FIXTURE / "findings-triage.md"
GATES = {"G_API": "api.py", "G_UI": "ui.py", "G_BROWSER": "browser.py"}
# `G_API: "message"` names a gate assertion by its failure message; a tests/ path names a unit test.
CITED = re.compile(r'(G_API|G_UI|G_BROWSER|tests/[\w./]+): "([^"]+)"')
# What a risk may rest on: an owner decision, a proposed-risk item, the threat model or a plan file.
GROUNDS = re.compile(r"\b(D[1-5]|A9|A1[1-3]|C[568]|threat model|(?:architecture|decisions|design|product|"
                     r"api-contract|acceptance)\.md|planning\.json|contract\.json)\b")


def exported():
    data = json.loads((FIXTURE / "p2g-accepted-findings.json").read_text())
    return Counter((run["run"], finding["id"]) for run in data["runs"] for finding in run["findings"])


def triage_rows():
    """The findings table: one row per (run, finding id), with its group, decision and assertion or reason."""
    rows = []
    for line in TRIAGE.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("| 2026-") and len(cells) == 5:
            rows.append(dict(zip(("run", "id", "group", "decision", "basis"), cells)))
    return rows


class TriageTableTests(unittest.TestCase):
    def test_every_exported_finding_appears_exactly_once(self):
        found = Counter((row["run"], row["id"]) for row in triage_rows())
        self.assertEqual(sorted(key for key, count in found.items() if count > 1), [], "triaged twice")
        self.assertEqual(sorted(set(exported()) - set(found)), [], "not triaged")
        self.assertEqual(sorted(set(found) - set(exported())), [], "not in the export")
        self.assertEqual(sum(exported().values()), 169)

    def test_each_group_is_decided_once(self):
        decisions = {}
        for row in triage_rows():
            decisions.setdefault(row["group"], set()).add((row["decision"], row["basis"]))
        self.assertEqual({group: len(found) for group, found in decisions.items() if len(found) > 1}, {})

    def test_a_check_or_covered_row_names_an_assertion_that_exists(self):
        for row in triage_rows():
            self.assertIn(row["decision"], {"check", "covered", "risk"}, row)
            if row["decision"] == "risk":
                self.assertRegex(row["basis"], GROUNDS, f"{row['run']} {row['id']}: a risk cites its decision")
                continue
            cited = CITED.findall(row["basis"])
            self.assertTrue(cited, f"{row['run']} {row['id']}: name the assertion (gate and failure message)")
            for where, message in cited:
                source = (FIXTURE / "checks" / GATES[where]) if where in GATES else ROOT / where
                self.assertIn(message, source.read_text(), f"{row['run']} {row['id']}: {where} lacks {message!r}")


def acceptance_rows():
    """plan/acceptance.md: (items, gates) per matrix row, in order."""
    rows = []
    for line in (FIXTURE / "plan" / "acceptance.md").read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"[RAC]\d+(, [RAC]\d+)*", cells[0]):
            gates = re.findall(r"G_[A-Z]+", cells[2].rsplit("(", 1)[-1])
            rows.append((cells[0].split(", "), gates))
    return rows


class MatrixTests(unittest.TestCase):
    """Finding run 3 F30 (and C F31, R1 F27): QA reads acceptance.md, the planner reads planning.json."""

    def test_the_manifest_mirrors_the_acceptance_matrix_row_for_row(self):
        matrix = acceptance_rows()
        manifest = json.loads((FIXTURE / "plan" / "planning.json").read_text())["failure_paths"]
        self.assertGreater(len(matrix), 30)
        self.assertEqual(len(manifest), len(matrix), "acceptance.md and failure_paths have different rows")
        for number, ((items, gates), row) in enumerate(zip(matrix, manifest), 1):
            self.assertEqual(sorted(row["gates"]), sorted(gates), f"row {number}: {row['scenario']}")
            self.assertLessEqual(set(items), set(row["items"]), f"row {number}: {row['scenario']}")

    def test_c1_names_the_list_rename(self):
        manifest = json.loads((FIXTURE / "plan" / "planning.json").read_text())
        c1 = next(item for item in manifest["concurrency"] if item["id"] == "C1")
        self.assertIn("renames the list", c1["item"])


if __name__ == "__main__":
    unittest.main()
