---
name: critical-thinking
description: Loaded for every role. Use before any main output: write a reasoning note, label every factual claim, and critique your own work before handing it off.
---

# Critical thinking

Think in writing before you act, say how you know each thing you claim, and
attack your own work before anyone else does.

## Reasoning note

Write this note before your main output. A worker puts it at the start of
its final message, and the runner keeps it with the attempt. The independent
reviewer never sees your reasoning, only the labelled claims of your
hand-off. At `full` planning depth a final message without the note is
rejected.

```
## Reasoning note
Understanding: <the task in one or two sentences>
Assumptions: <each marked how it will be confirmed>
Options considered: <at least two, with the trade-off>
Choice and why: <one paragraph>
Pre-mortem: <how this could fail; what I did about each>
How I'd know I'm wrong: <the observation that would disprove the choice>
```

Fill every line. An assumption you cannot confirm stays in the list, marked
as unconfirmed. "Options considered" names real alternatives you rejected,
not a straw man. The pre-mortem names concrete failures (an input, a race, a
missing check), each with what you did about it.

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
