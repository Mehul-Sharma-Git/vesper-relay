# Using Vesper Relay

Vesper Relay is a separate Git repository you install once. It runs locally
alongside your website, and your website stays in its own repository. Each run
has its own directory for the plan, approved checks, work copies, and evidence.

## For a person

1. Clone the Vesper Relay repository and keep the checkout on your machine.
   Run the installer from that checkout.

   ```sh
   python3 -B vesper.py install --for both
   ```

   This requires Python 3.11 or later on macOS or Linux. Existing-project
   workflows also need Git. Use `--for codex` or `--for claude` to install
   only one entry point. If you move the checkout, rerun the installer.

2. Open your **website's** checkout in VS Code. Start a local Codex or Claude
   Code session from that workspace. Use `$vesper-relay` in Codex or
   `/vesper-relay` in Claude Code and describe the outcome you want.

   > Fix the orders page. After a failed save the button keeps spinning.
   > Reproduce the failure, show me the proposed scope, then verify the fix.

   For a new site, start from the folder you want to work from and describe
   the site. Vesper keeps that build separate until you export it.

3. Review what the assistant proposes. For a bug, expect the observed failure,
   expected behavior, file scope, and a regression check. For a new site,
   expect a wider planning conversation and the product and design decisions
   needed to approve the build.
4. Approve the plan digest once the scope and checks look right. The assistant
   can run supervised jobs in the disposable work copy. After verification,
   review the Git diff and its digest before approving application to your
   checkout. New sites can be exported to a new directory.

Vesper uses committed HEAD as the baseline for an existing repository. It can
preserve unrelated local edits, but those edits are absent from the baseline
used to run the checks. If an uncommitted edit is required for the work,
include it in the baseline first. Commit and push from the website repo after
reviewing the applied change, using your normal Git workflow.

## For an AI client

### What is included

| Component | Where it comes from | What it does |
|---|---|---|
| Vesper entry skill | `integrations/vesper-relay/SKILL.md` | Selects the workflow, guides approvals, and calls the CLI |
| Workflow and planner guides | [WORKFLOWS.md](WORKFLOWS.md) and [PLANNER.md](PLANNER.md) | Describe the planning packet, role responsibilities, and evidence |
| Runner and Git bridge | `vesper.py`, `build_local.py`, and `builder/` | Execute scoped jobs, run checks, recover, and produce the reviewable patch |
| Agent-specific expertise | The client and the context supplied for each job | Provides engineering or design judgment within the approved role and scope |

The installer copies the **same included skill** to Codex's
`~/.agents/skills/vesper-relay/` and Claude Code's personal skills directory
(`~/.claude/skills/vesper-relay/` by default). It also creates
`~/.local/bin/vesper`. People do not need to write or download extra skills
to start. Open a new assistant session if the installed entry point is absent.

The current release has one bundled entry skill. Planner, designer, frontend,
backend, and QA are responsibilities described in the workflow and job brief.
They can be handled by a client in separate passes. Dedicated role definitions,
role-specific skill packs, and an independent reviewer agent are future work.
The runner already enforces the approved file scope and automated gates.

Clients that can use a terminal can follow the same workflow by reading the
bundled skill and invoking the CLI, even if they use a different skill format.
Use `~/.local/bin/vesper` if `vesper` is not on PATH.

### Run the workflow

- **Intake.** Run `vesper start --mode bug --idea "Describe the problem"` from the
  target checkout, or select `build`, `feature`, `design`, `frontend`, or
  `backend` as appropriate. Read the returned guide and keep the returned
  project path. Use `vesper runs --repo .` to find an earlier run.
- **Plan.** Read the committed seed when applicable. Fill in the planning
  packet and independent checks. Run `vesper --project PATH review` and show the
  proposed scope, evidence, and digest. Run
  `vesper --project PATH approve --digest DIGEST` only after authorization.
- **Execute.** Run `vesper --project PATH prepare`, read the returned job brief,
  and edit only its work copy within the assigned scope. Run
  `vesper --project PATH submit ATTEMPT_ID` to verify it. Repeat for ready jobs.
  Resume with `status` and the existing run.
- **Deliver.** For a Git run, use `review-change` and `patch` to show the final
  diff and digest. Use `apply --digest DIGEST` only after approval. For a new
  site, use `export NEW_DIRECTORY`. Report evidence that passed and any
  behaviors still needing verification.
- **Learn.** Verified Vesper runs record typed local signals automatically.
  Use `vesper learn` to see proposals. Promotion changes the guidance for future
  matching work. Code changes to Vesper itself use `vesper maintain` and the
  reviewed patch flow.

Supervised mode uses the current assistant and the local runner. Unattended
mode uses a separately authenticated provider CLI and the operator's approved
execution boundary. See [START-HERE.md](../START-HERE.md) for launcher details.
A local checkout can still send context to a hosted model if the operator
chooses one. Follow the user's data-sharing rules.

## Verify an installation

From the Vesper Relay checkout:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B examples/replay_repo_fix.py /tmp/vesper-repo-pilot
python3 -B examples/replay_stockroom.py /tmp/vesper-build-pilot
```

Use a fresh destination for each replay. Both demos use supervised job outputs.
See [PILOT.md](PILOT.md) for the remaining browser, provider, and planning gaps.
