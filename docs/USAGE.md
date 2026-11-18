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
4. Approve the plan digest once the scope and checks look right. A specialist
   implements each job in a disposable copy. An independent reviewer inspects
   the tested candidate before the runner accepts it. Review the delivered Git
   diff and its digest before approving application to your checkout. New sites
   can be exported to a new directory.

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
| Specialist roles and skills | `team/roles/` and `team/skills/` | Supplies domain playbooks, role boundaries, handoffs, and review criteria |

The installer copies the **same included skill** to Codex's
`~/.agents/skills/vesper-relay/` and Claude Code's personal skills directory
(`~/.claude/skills/vesper-relay/` by default). It also creates
`~/.local/bin/vesper`. People do not need to write or download extra skills
to start. Open a new assistant session if the installed entry point is absent.

The installer gives you one entry skill. The CLI supplies specialized role and
skill context as each job needs it. Provider mode starts separate processes for
writers and reviewers. Supervised mode can use the editor assistant for writing
and a separate session for review. See [the RC1 guide](RC1.md) for the role map,
the visual planning gate, and the source repair workflow.

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
  `vesper --project PATH submit ATTEMPT_ID` to run the approved checks, then
  `review-candidate` with a reviewer brain (`--brain NAME`) or an attested independent report.
  Repeat for ready jobs. Resume with `status` and the existing run.
- **Deliver.** For a Git run, use `review-change` and `patch` to show the final
  diff and digest. Use `apply --digest DIGEST` only after approval. For a new
  site, use `export NEW_DIRECTORY`. Report evidence that passed and any
  behaviors still needing verification.
- **Learn.** Verified Vesper runs record typed local signals automatically.
  Use `vesper learn` to see proposals and `vesper --project PATH incidents` to
  triage failures. Use `vesper repair` for a confirmed Vesper source defect and
  `vesper maintain` for other planned changes to Vesper.

- **Configure.** Personal settings (brains, roles, sandbox, limits) live in
  `~/.config/vesper/config.toml` (or `--config PATH` / `VESPER_CONFIG`); project
  settings (stack, hosting, checks) live in a committed `vesper.toml` in the
  target repository. Run `vesper config show` to print every effective value and
  where it came from (`flag`, `project`, `personal` or `default`); add
  `--repo PATH` for another repository and `--set KEY=VALUE` to preview an
  override. Neither file may hold secrets: keys named like `api_key`, `token`,
  `secret`, `password` or `credential` are refused; use the macOS Keychain or
  `~/.config/vesper/secrets.env` (mode 600).
- **Choose brains.** Any supported AI can do every role; one is enough. The
  adapters are `claude-code`, `codex` and `gemini-cli`. Name brains by purpose
  in the personal config (`[brains.strong] use = "claude-code"`, optional `model`
  and `effort` when the adapter accepts them) and map roles to them under
  `[roles]` (`frontend = "strong"`, `reviewer = "reviewer"`). `--brain NAME` on
  `run`, `review-candidate`, `consult`, `review-plan` and `repair-run` names a
  configured brain or an adapter and overrides the roles; `run` and `repair-run`
  also take `--reviewer-brain NAME`. The reviewer defaults to `[roles] reviewer`,
  then to the worker's brain. `--provider claude|codex` and
  `--reviewer-provider` are deprecated aliases kept for one release.

Supervised mode uses the current assistant and the local runner. Unattended
mode uses a separately authenticated agent CLI (a brain) and the operator's approved
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
The existing-repo demo also launches a deterministic reviewer fixture.
See [PILOT.md](PILOT.md) for the remaining browser, provider, and planning gaps.
