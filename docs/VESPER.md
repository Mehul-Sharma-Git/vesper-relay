# Vesper Relay implementation

Vesper Relay uses the existing verified runner as its execution engine. One checkout
installs a portable assistant entry point and a local command. A separate local run
holds the plan, check inputs, snapshots, and results. The target repo owns its source.

1. Add a Git bridge and workflow intake. Copy the committed tree into an isolated
   seed, bind the baseline to the plan, produce a binary-safe review patch, and
   apply only by digest to the original baseline with overlapping changes protected.
2. Add one canonical skill and a repeatable installer for Codex and Claude.
   Exercise an existing-repo bug from intake, through a failing check and scoped
   fix, through review and application without touching unrelated local changes.
3. Add local, typed lessons from verified runs. Count repeat signals across
   independent completed runs. Use only active, trusted guidance in new worker
   briefs. Reuse the Git workflow for maintenance proposals on Vesper itself.
4. Verify both discovery layouts, the full regression suite, fresh-clone setup,
   and a shareable Git artifact. Track what remains unverified in provider UIs.
