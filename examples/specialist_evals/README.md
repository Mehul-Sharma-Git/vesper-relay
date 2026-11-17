# Specialist evaluations

Use `python3 -B examples/specialist_evals/run_evals.py --output NEW_DIR` to
write the matrix and revisions from the installed catalog. Add `--run` to run
matched synthetic trials through an authenticated Codex CLI. Use `--case ID`,
`--repeat N`, `--model`, `--timeout`, or `--parallel` to scope a run. Put the
output directory outside the source checkout.

Each arm uses the same task, model, timeout, read-only policy and response
budget in a fresh temporary directory. The specialist receives the exact
profile and skills. The control receives a generic instruction. The grader
runs separately and receives anonymous outputs and the fixture rubric. The
run retains prompts, output, commands, revisions, deterministic term checks,
blind findings and the variant key. Treat term checks as smoke signals. The
quality target is 8/10 with no critical failure. Repeat close or critical
cases, and inspect the actual artifacts before claiming a gain.

These cases use controlled text fixtures. Code, test plans and wireframes
are scored as submitted artifacts. They need separate execution and visual
checks to establish application behavior. Provider session isolation and
CLI read-only settings do not verify a production launcher boundary.
