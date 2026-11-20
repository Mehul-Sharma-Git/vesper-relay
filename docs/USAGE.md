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
  packet and independent checks. Run `vesper --project PATH review` to print the
  plain-language approval sheet (`review --json` gives the raw bundle for tools). Run
  `vesper --project PATH approve --digest DIGEST` only after authorization; the owner
  then confirms it (see Approvals).
- **Execute.** Run `vesper --project PATH prepare`, read the returned job brief,
  and edit only its work copy within the assigned scope. Run
  `vesper --project PATH submit ATTEMPT_ID` to run the approved checks, then
  `review-candidate` with a reviewer brain (`--brain NAME`) or an attested independent report.
  Repeat for ready jobs. Resume with `status` and the existing run.
- **Add a check after approval.** `vesper --project PATH add-check --id G_X --script x.py
  --jobs J_X[,J_Y] --reason "..."` (or `--command "go test ./..."` in place of `--script`)
  adds a new gate without a full re-approval. It may only add: a new check ID, a new script
  name, and jobs that are not accepted yet and whose candidate is not awaiting review;
  approved checks are never removed, edited or reassigned. The amendment is kept under
  `.builder/amendments/` with a digest chained to the approval, the owner confirms it on its
  sheet (see Approvals), and the next verification of each assigned job runs the new check
  (the last job to finish runs every gate). `status` lists every amendment.
- **Deliver.** For a Git run, use `review-change` and `patch` to show the final
  diff and digest. Use `apply --digest DIGEST` only after approval. For a new
  site, use `export NEW_DIRECTORY`. Report evidence that passed and any
  behaviors still needing verification.
- **Findings and decisions.** Every finding of a plan critique or a job review has a
  category (correctness, security, data, performance, maintainability, design, other)
  and is kept in `.builder/backlog.json` with an ID (`F1`, `F2`, …); `status` lists the
  backlog and `awaiting_decision`. Reviewers find and explain; you decide. A plan-critique
  blocker, a security or data advisory on a job, and the review blockers of a job whose
  attempts are used up all wait for you (status `awaiting_decision`): run
  `vesper --project PATH decide F3 --fix` to send the plan back, return the job for
  correction (it counts as a retry) or grant one more attempt, or
  `decide F3 --accept-risk --reason "..."` to accept it as a risk, which you confirm on a
  risk sheet (see Approvals). Once every plan blocker is accepted, `approve` can proceed and
  the plan sheet lists each acceptance; security and data advisories from the critique are
  listed under the risks you accept by approving. A run never reaches `complete` while a
  finding still waits for you.
- **Approvals.** Approving a plan, applying a patch, committing a repair,
  attesting that a report came from an independent reviewer, adding a check after
  approval and accepting a risk are human-only. Each
  shows a plain-language sheet (what is delivered or changed, each promise and its
  gate, what each job may change, the critique or review verdict, what changed since
  the last confirmation, and the short digest) and runs only after a person confirms.
  `[approvals] confirmer` in the personal config chooses how: `tty` (default) prints
  the sheet in a terminal and asks you to type back a short code, and refuses when
  standard input is not a terminal, so an assistant's tool call cannot confirm;
  `macos-dialog` shows a short form in a native dialog with a "Show full sheet"
  button. An assistant runs the command and asks you to confirm. Both make approval
  a deliberate human act; neither is authentication against software that controls
  your machine. `VESPER_TEST_CONFIRMER` names a test-only stand-in for automated
  tests; `vesper doctor` warns whenever it is set.
- **Plan usage.** Every AI call Vesper starts is logged in
  `~/.local/state/vesper-relay/usage.jsonl` (run, job, role, brain, model, start, end,
  and tokens when the AI reports them). Estimates are in % of your plan's session and
  weekly limits and wall time, never dollars. Vendors don't publish exact plan numbers,
  so Vesper learns from your runs: before and after a run, log what your plan shows
  with `vesper usage record --account claude --session 42 --week 13` (accounts:
  `claude`, `chatgpt`, `gemini`). `vesper --project PATH estimate` (and the plan sheet
  from `review`) then shows jobs, AI calls, tokens, wall time, session and weekly % per
  account as a low–high band, sessions needed with your reserve
  (`[limits] reserve_percent`), and a confidence level, low until 5 calibrated runs.
  Before any readings it says "uncalibrated" and shows tokens and time only. Before
  each job `run` checks the last reading, the usage since it and the job's estimate
  against your reserve; if the job could cross it, `run` stops before that job (never
  during one) with status `paused_for_limits` and exit code 3, says when the window
  should reset, and continues from the accepted work when you run it again.
  `run --start-after HH:MM` waits for that local time first.
- **Learn.** Verified Vesper runs record typed local signals automatically.
  Use `vesper learn` to see proposals and `vesper --project PATH incidents` to
  triage failures. Use `vesper repair` for a confirmed Vesper source defect and
  `vesper maintain` for other planned changes to Vesper.

- **Set up and check.** `vesper setup` walks a new machine through everything
  automatic runs need: it lists the AI CLIs it finds, asks which one works and which
  reviews (one is enough), checks Docker, Colima or Podman and offers to install or
  start it, builds the sandbox image, stores each brain's sandbox login in the macOS
  Keychain or `~/.config/vesper/secrets.env` (mode 600), asks for the plan-usage
  reserve, writes `~/.config/vesper/config.toml` (keeping any old one as
  `config.toml.bak`) and runs `vesper doctor`. `vesper doctor` checks Python, the
  config, the sandbox engine, the image and its architecture, whether the engine can
  see the run folder, and for each configured brain its CLI, whether `--help` still
  lists every flag Vesper uses, its sandbox login and a tiny dry call (`--no-call`
  skips it; `--json` for scripts). Every failure prints its fix. The installed `vesper`
  command finds a Python 3.11+ on its own (`bin/vesper`), so no virtual environment is
  needed; if there is none, `vesper setup` offers to install one with Homebrew or uv.
- **Configure.** Personal settings (brains, roles, sandbox, limits) live in
  `~/.config/vesper/config.toml` (or `--config PATH` / `VESPER_CONFIG`); project
  settings (stack, hosting, checks) live in a committed `vesper.toml` in the
  target repository. Run `vesper config show` to print every effective value and
  where it came from (`flag`, `project`, `personal` or `default`); add
  `--repo PATH` for another repository and `--set KEY=VALUE` to preview an
  override. Neither file may hold secrets: keys named like `api_key`, `token`,
  `secret`, `password` or `credential` are refused; use the macOS Keychain or
  `~/.config/vesper/secrets.env` (mode 600).
- **Sandbox.** Brains, gates and reviewers run in a container: `sandbox.backend` in the
  personal config (`docker` by default) or `--sandbox docker|podman|none` on `run`,
  `submit`, `review-candidate`, `consult`, `review-plan`, `repair-reproduce` and `repair-run`. `vesper sandbox build`
  builds the image from `sandbox/Dockerfile`; `vesper sandbox selftest` (or
  `sh sandbox/selftest.sh`) tries to escape from every operation and passes only when every
  attempt fails. `none` and `--trust-host` run on the host and warn every time; `--launcher
  PATH` keeps a custom launcher. Sandboxed brains log in from the macOS Keychain (service
  `vesper-relay`) or `~/.config/vesper/secrets.env` (mode 600); see START-HERE.md.
- **Gate evidence.** A gate can save evidence (screenshots, traces) in the folder named
  by `VESPER_ARTIFACTS`. The independent reviewer's copy holds the approved gate scripts
  (`checks/`), each gate's log (`logs/<ID>.log`, the last 256 KB when longer) and what
  each gate saved (`artifacts/<ID>/`, up to 20 MB in all). Any change to that copy is
  refused before the verdict counts. `review.json` lists the code the change touches
  (`touched`: each enclosing function, method or class, or the whole file for top-level
  code and languages Vesper does not parse), and `diff.patch` shows it in full; the
  reviewer sweeps it and reports reachable defects there even when the change did not
  introduce them.
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
