---
name: critical-thinking
description: Loaded for every role. Use for every hand-off: label every factual claim, and critique your own work before handing it off.
---

# Critical thinking

Say how you know each thing you claim, and attack your own work before
anyone else does.

## Claim labels

Tag every factual claim in a hand-off:

| Label | Meaning |
| --- | --- |
| `[verified]` | You ran or read it. Say how: the command and its result, or the file and line |
| `[inferred]` | It follows from something you verified. Say from what |
| `[assumed]` | You did not check it |

"Should work" is not allowed: either run it and label it `[verified]`, or
label it `[assumed]` and say what would check it. A `[verified]` claim with
no evidence is a finding in its own right.

## Self-critique

Before finishing, re-read your diff or output as a hostile reviewer would.
List what that reviewer would flag: a broken input, an unhandled error, a
claim without evidence, a change outside scope. Fix each item, or say why it
stands. Then hand off.
