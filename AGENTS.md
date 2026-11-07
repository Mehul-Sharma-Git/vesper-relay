# Working with Vesper Relay

Read README.md for install and use, docs/WORKFLOWS.md for workflow routing,
and integrations/vesper-relay/SKILL.md for the shared assistant entry point.

Run `python3 -B -m unittest discover -s tests -v` and
`python3 -B examples/replay_repo_fix.py PATH_TO_NEW_DIRECTORY` before shipping.
The coordinator has no third-party Python dependencies.

Keep worker code separate from accepted snapshots, local learning, and gate
files. Do not broaden permissions or automatically apply generated self-edits.
Changes to the Git bridge must preserve unrelated user edits and require the
reviewed patch digest.
