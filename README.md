# Vesper Relay

**A local workshop for your AI software assistant.** Start a site, investigate a
bug, redesign a section, or change a backend. Vesper separates the conversation,
the approved plan, the work copy, and the checks. The longer-term direction is
a personal engineering assistant that can coordinate specialized workers and
improve its workflows from experience.

## Install once, use from any project

Requires Python 3.11+ on macOS or Linux and Git for existing-repo workflows.
The runner itself has no Python package dependencies.

```sh
# Clone this repository, then run this from the Vesper Relay checkout.
python3 -B vesper.py install --for both
```

Open your website's checkout in VS Code and start a local assistant session.
In Codex, invoke `$vesper-relay`. In Claude Code, invoke `/vesper-relay`.
For example, ask it to fix a spinner that never stops after a request fails.
If the skill does not appear in an open session, start a fresh session. The
installer gives both assistants the same instructions and creates
`~/.local/bin/vesper`. Keep this checkout in place or rerun the installer after
moving it. If needed, put `~/.local/bin` on PATH.

The install locations follow [Codex's user skill location](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code's personal skills](https://code.claude.com/docs/en/skills).
This is a local assistant integration; a remote editor session needs an
installation in the environment where the assistant and terminal run.

See [Using Vesper Relay](docs/USAGE.md) for the full workflow for people and AI clients.

## How the parts fit

| Part | Responsibility |
|---|---|
| Assistant skill | Selects the workflow, asks about the work, and uses the CLI |
| Approved contract | Defines scope, job ownership, and independent acceptance checks |
| Runner | Executes jobs in disposable copies, retries within a budget, and records accepted snapshots |
| Git bridge | Reads a committed baseline and produces a reviewable patch for the original checkout |
| Local learning | Records evidence from verified runs and proposes changes to the playbook |

Use `vesper start --mode bug --idea "The filters ignore status"` from an existing
repo, or use `--mode build` for a new site. Pass the returned run path to later
commands as `vesper --project PATH …`. The assistant can handle those details for
you. Run `vesper runs --repo .` to find previous runs for the current checkout.
See [WORKFLOWS.md](docs/WORKFLOWS.md) for routing and [START-HERE.md](START-HERE.md)
for the underlying supervised and provider commands.

The initial Git seed comes from HEAD. A reviewable patch can be applied to the
working tree after approval. Vesper rejects a moved HEAD and tracked, staged,
or untracked changes that overlap the patch. Unrelated edits stay in place.
Git symlinks and submodules require a future intake extension. Changed paths
with Git content conversion rules may require manual patch application. This release
treats committed source as the baseline, so resolve desired uncommitted
changes before intake. Repo-local files containing secrets should stay outside
tracked source and away from any hosted model context.

## Learning and self-maintenance

Verified runs record typed, local signals automatically. Two separate runs
with the same signal can propose a shipped guidance rule. `vesper learn` shows
evidence and proposals. `vesper learn --promote RULE` activates a proposed rule
for matching future work. Raw logs and source never enter shared lesson text.

`vesper maintain` starts a scoped run against the Vesper checkout. It attaches
the local evidence and a frozen baseline regression suite. Review the plan,
build and verify the fix in a work copy, then review its patch before applying.
This provides a path for Vesper to help repair itself with the same review
boundaries as your website. The lesson catalog is bounded. Changes to the
runner or skill go through normal tested patches.

## Run the checks or try a real existing-repo fix

```sh
python3 -B -m unittest discover -s tests -v
python3 -B examples/replay_repo_fix.py /tmp/vesper-repo-pilot
```

The replay creates a disposable Git repo, demonstrates a failing HTTP filter
test, verifies the scoped fix, applies the reviewed patch, and preserves an
unrelated local edit. Its worker changes are supplied in supervised mode.
Existing supervised and provider-isolation guidance is in [START-HERE.md](START-HERE.md).
