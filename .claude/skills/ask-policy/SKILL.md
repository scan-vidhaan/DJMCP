---
name: ask-policy
description: When a DJ agent may ask the user a question and when it must decide alone. Use before calling request_input and whenever a request is vague or ambiguous.
---

# Ask policy: decide, don't interrogate

The people using this are often not technical. A request like "make a mashup with the trending songs in Bollywood" must produce a finished mix with nothing more typed. When something is unclear, **make a sensible choice, record it with `state_add_assumption`, and keep going.** Never answer a vague request with a list of clarifying questions.

## The only three questions you may ask

| Key | When | Default |
| --- | --- | --- |
| `resume_old_job` | An unfinished job looks like the same request (orchestrator only) | Continue the most recent matching job |
| `style` | The user did not say how to combine songs (mashup-builder only) | 2 songs: Layered. 3 to 4 songs: Both. 5 or more: Sequence |
| `plan_choice` | More than one plan is realistic: the top two scores are within 0.1 of each other, or the job is long (more than 4 songs, or about 15 minutes of mixing) | The top-ranked plan |

Anything else, decide yourself.

## How to ask

- Always use the `request_input` tool with a `key`, a short plain-language `prompt`, 2 to 4 `options`, and a `default` that is one of the options. Never ask in plain chat text.
- If it returns `{"answered": true, "answer": ...}`, use the answer and continue. This also happens when the user turned on Autopilot (the default was taken and recorded for you) or when you asked the same `key` before.
- If it returns `{"answered": false}`, **stop and end your turn.** The job is parked; you will be run again once the user answers.
- Ask at most one question at a time, and never ask the same key twice.
- Write options a non-technical person understands: "One after another", "Vocals over another song's beat", not "sequence" or "layered". Include a short reason on plan options ("same key, tempo within 4%").

## Autopilot

When the user chose Autopilot, `request_input` answers for you. Do not skip the call: it is what records the assumption shown to the user.
