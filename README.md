# Project 1: single call vs compound

Team: Adrika Pradhan and Odinaka Ogbujiagba. Engineering AI Systems, USI, Fall 2026.

Both systems take one person's request and five candidate games, and return the one game that meets every
requirement, or a decline when none does. The right answers follow `RUBRIC.md`. The starter code's own README is
kept at the end of this file.

## What we built

### Single-call system: `systems/single.py`

One model call per request. The prompt is our summary of the rubric (`INSTRUCTIONS`), then the answer format
(`FORMAT`), then the request and the five games.

- The format asks the model to list the requirements and check every game against each one before it picks, so
  that the pick comes after the working rather than before it. Our `answer()` reads only `pick` and `explanation`.
- A reply that isn't the JSON we asked for, or whose pick isn't one of the five letters, becomes a decline. The
  call limit is 1, so the system can't ask again.

### Compound system: `systems/compound.py`

Two model steps and two code steps. At most 7 model calls per request (the limit is 10); on the public requests
it made at most 4.

| Order | Step | Kind | What it does |
|---|---|---|---|
| 1 | `read_request` | model | Reads only the request text and returns its requirements: `players`, `max_minutes`, `complexity`, `mode`, `child_age`, and five yes/no `no_...` fields for things to avoid. Wishes are left out. Retries once if the reply doesn't fit. |
| 2 | `check_card` | code | Checks each game's card against the requirements. Players, play time, age, cooperative or competitive, and the tags for things to avoid are exact lookups. The complexity rules of the rubric (light, medium, heavy, from weight and game types) are coded in `is_light`, `is_heavy` and `check_complexity`. Each requirement gets meets, breaks, can't tell, or ask. |
| 3 | `read_description` | model | Only for a game the card hasn't ruled out, and only for the questions the card left open ("ask"): a player count, play time or age the card doesn't list, what the description says about the rules, and whether the game has fighting, violence, horror, a timer or player elimination. |
| 4 | `answer` | code | Picks the first game that meets every requirement, or declines, with one reason per game. |

Design choices:

- **Code does what code can do exactly.** In the single-call runs the model often marked a game as meeting
  everything and then declined anyway, or got simple range checks wrong. In the compound system, the model only
  reads language (the request, a description), and code does every comparison and the final decision.
- **The model is only asked open questions.** A game that the card alone shows to be acceptable is picked with no
  description call, and a game that no description could rescue is dropped without one.
- **Every model step has fields with fixed choices**, so we could label them and measure each step on its own.

## How to run

You need Python 3.10 or newer. From this folder, on macOS or Linux:

```
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
python -m pytest
```

Set `P1_ENDPOINT` and `P1_TOKEN` from the course app's Project 1 page (`P1_BACKEND=fake` runs without a model).
Then:

```
# Run a system and score the run
python -m p1.run systems/compound.py --requests data/public.jsonl --out runs/compound-x
python -m p1.run systems/single.py --requests data/public.jsonl --out runs/single-x
python score.py runs/compound-x

# Checkpoint requests: score against their own answers
python -m p1.run systems/compound.py --requests data/checkpoint_requests.jsonl --out runs/checkpoint-x
python score.py runs/checkpoint-x --answers data/checkpoint_answers.jsonl

# Contracts and call limits of a run; connected model steps
python -m p1.contracts runs/compound-x
python -m p1.contracts systems/compound.py

# A model step's accuracy against our labels (labels/ comes from python -m p1.labels pull)
python -m p1.labels accuracy runs/labeling-compound --step read_description --labels labels/read_description.jsonl
```

## Results

Every number below comes from a run folder in `runs/`. Cost and time are per request; the time is the median of
the requests' own times (the runner works on 4 requests at once).

### Public requests (150), two runs of each system

| System | Run | Right | Cost per request | Median time |
|---|---|---|---|---|
| Single call | `single-3` | 75 of 150 (50%) | $0.00049 | 3.2 s |
| Single call | `single-4` | 85 of 150 (57%) | $0.00049 | 2.9 s |
| Compound, before our change | `compound-2` | 130 of 150 (87%) | $0.00021 | 2.2 s |
| Compound, before our change | `compound-3` | 131 of 150 (87%) | $0.00021 | 2.1 s |
| Compound, after our change | `compound-fix-1` | 137 of 150 (91%) | $0.00021 | 2.1 s |
| Compound, after our change | `compound-fix-2` | 135 of 150 (90%) | $0.00021 | 2.1 s |

- **The single call varies a lot from run to run.** The same code on the same requests scored 75 and 85: 55
  requests were wrong in both runs, 20 only in the first and 10 only in the second. A difference of up to about
  10 of 150 can be chance for this system.
- **The compound system is stable.** 130 and 131, with 17 requests wrong in both runs and 3 and 2 that differ.
- **The compound system is better on every measure we took**: about 45 to 55 more requests right, less than half
  the cost per request, and faster, because most requests need one or two short calls instead of one long one.

### Checkpoint requests (50)

| System | Run | Right |
|---|---|---|
| Single call | `checkpoint-single` | 29 of 50 (58%) |
| Compound, before our change | `checkpoint-compound` | 45 of 50 (90%) |
| Compound, after our change | `checkpoint-compound-fix` | 48 of 50 (96%) |

We have read the checkpoint answers and used these requests for our error analysis, so a score on them after our
change is no longer a measurement on unseen requests.

## Labels and step accuracy

We labeled the inputs of both model steps on the 10 public practice requests and the 10 hidden labeling requests
in the course app; `labels/` has them as downloaded with `python -m p1.labels pull`. On the hidden labeling
requests that is 10 labels for `read_request` and 5 for `read_description` (the card settled the other games
without a description call).

| Step | Requests | Labeled inputs | Right in all labeled fields | Run |
|---|---|---|---|---|
| `read_request` | hidden labeling | 10 | 10 of 10 | `labeling-compound` |
| `read_description` | hidden labeling | 5 | 5 of 5 | `labeling-compound` |

Every labeled field matched, field by field, for both steps (`python -m p1.labels accuracy`). Two cautions: these
are small samples, and they measure agreement with our own labels, not with an answer key. On these 10 requests
the card settled half of the requests without any description call, so `read_description` was only tested on 5
inputs, 4 of them about the rules wording.

With our labels in place of both model steps, the system answers all 10 public practice requests right (the
Gradescope label check, and our own run). On those practice requests, Gradescope's step check gave `read_request`
9 of 10, and `read_description` 4 of 9 for our final system (1 or 2 of 9 before our change, in our checkpoint
submission). Five of our nine practice labels for `read_description` fill in fields whose questions weren't asked,
which the step always leaves empty, so those five can never match; the step matched all four of the others. The
`read_request` miss is P019, where we labeled "nothing violent" as both no fighting and no violence, and the step
answers no violence only.

## Where it fails

### The 50 checkpoint requests, compound system before our change

All 5 failures are declines where a game was acceptable.

| Request | What went wrong | Step |
|---|---|---|
| H1-006 | Read "a game that everyone can play together" as a cooperative requirement, which ruled out E, a competitive game that fit everything else. | `read_request` |
| H1-016 | Answered that the rules are "complex" from "planning and strategy" in the description, which ruled out D (strategy, weight 2.89, medium by the card). | `read_description` |
| H1-030 | Turned the wish "It would be nice if the game can be played either PvP or co-op" into a cooperative requirement, which ruled out C and E. | `read_request` |
| H1-047 | Answered that the rules are "complex" with the evidence "none", which ruled out B (weight 3.3, medium by the card). | `read_description` |
| H1-088 | Answered that the rules are "complex" with the evidence "none", which ruled out D (weight 2.8, medium by the card). | `read_description` |

| Group | Count |
|---|---|
| `read_description` claims rules wording that the description doesn't have | 3 |
| `read_request` invents a cooperative requirement (a wish, or "play together") | 2 |

The same biggest group showed up on the public requests: in `compound-2`, 15 of the 20 wrong answers involved
the `rules` answer of `read_description`. Over that run the step answered "easy" 32 times, "complex" 20 times
and "unclear" 28 times, although most descriptions say nothing about how hard the rules are; in 6 cases it
answered "easy" or "complex" while quoting "none" as evidence.

## What we changed

One change, aimed at the biggest group: **the description step has to quote the rules wording before it judges
it, and code checks the quote.**

1. The `rules` question now asks first for `rules_quote`, the exact words that say how easy or hard the rules
   are, or nothing; most descriptions have none. "easy" and "complex" must come from those words, and the
   question lists what doesn't count (strategy, depth, planning, how hard the game is to win, and the rubric's
   other exclusions).
2. In `read_description`, an "easy" or "complex" answer only stands if `rules_quote` is at least two words that
   really appear in the description (ignoring case, spacing and quote marks). Otherwise the answer becomes
   "unclear", the rubric's answer when the description doesn't say.

The step's inputs didn't change, and `rules_quote` is free text, so our labels still fit.

| | Before | After |
|---|---|---|
| Public, run 1 | 130 of 150 (`compound-2`) | 137 of 150 (`compound-fix-1`) |
| Public, run 2 | 131 of 150 (`compound-3`) | 135 of 150 (`compound-fix-2`) |
| Checkpoint (development data) | 45 of 50 (`checkpoint-compound`) | 48 of 50 (`checkpoint-compound-fix`) |

Cost and time per request didn't change ($0.00021, 2.1 s).

**What the change did on the public requests.** On average 136 right instead of 130.5. That is larger than the
run-to-run variation we measured for this system (1 to 2 requests between two runs of the same code), and it
shows up request by request:

- 17 requests were wrong in both runs before; 11 are wrong in both runs after.
- 9 requests were wrong in both runs before and right in both runs after: P003, P019, P028, P059, P061, P066,
  P068, P130, P146. All 9 had been ruled out by a wrong "easy" or "complex".
- 4 requests were right in both runs before and wrong in both runs after: P045, P105, P135, P145 (see below).
- The step now answers "unclear" for 61 of about 78 rules questions per run, instead of 28 to 30 of about 80.

**On the checkpoint requests**, the three `rules` failures (H1-016, H1-047, H1-088) are now right, and the two
`read_request` failures (H1-006, H1-030) remain. We read these requests before making the change, so this
confirms the change does what it was meant to do; it doesn't measure it on unseen requests.

**What it broke.** In each run, the quote check turned 13 "easy" or "complex" answers into "unclear", because the
model left `rules_quote` empty. Most of those were right to remove (P059: "more challenging than any of the games
I've listed" is about difficulty, not rules). But in three requests the description did have wording that counts,
and the model had put it in `evidence` instead of `rules_quote`: P105 ("a full length expert game"), and P135 and
P145 (the same game, "It's complex and suspenseful enough to keep adults riveted"). Accepting the words in
`evidence` as well would bring those back, but it would also bring back P059 and P146, which the change fixed, so
we kept the stricter check. P045 broke for a different reason: 12 Chip Trick was asked about the rules and about
player elimination in one call, and the step answered "no elimination" in both runs before the change and "yes"
in both runs after. The new rules question shares that prompt, so this looks like a side effect of the change,
not chance.

## Limits and what we would do next

- **The second failure group is untouched.** `read_request` still turns some wishes and "play together" into a
  cooperative requirement (H1-006, H1-030, and P108 on the public requests). That would be our next change.
- **The quote check is blunt.** It depends on the model filling `rules_quote`, and in three requests it threw away
  wording that counts (see above).
- **The other description questions still make mistakes.** The step says a game has player elimination where
  the right answer needs it not to: P141 in every run, and P045 and P071 after the change (P071's rules answer
  is now right, but its elimination answer rules out the right game instead). Its violence answer for P029
  changes from run to run.
- **Our measurements are on data we have seen.** We designed the change from failures on the public requests and
  read the checkpoint answers before measuring on them, so the gain on unseen requests may be smaller than the 5.5
  requests we measured here.
- **The single call is noisy.** Its score moved by 10 of 150 between two runs of the same code, so a comparison
  with it needs more than one run.

## Runs in this repository

| Folder | System | Requests |
|---|---|---|
| `runs/single-3`, `runs/single-4` | single call | public |
| `runs/compound-2`, `runs/compound-3` | compound, before the change | public |
| `runs/compound-fix-1`, `runs/compound-fix-2` | compound, after the change | public |
| `runs/checkpoint-single`, `runs/checkpoint-compound` | single call; compound before the change | checkpoint |
| `runs/checkpoint-compound-fix` | compound, after the change | checkpoint |
| `runs/labeling-compound` | compound, after the change | hidden labeling (for step accuracy) |

Earlier runs (`single-1`, `single-2`, `compound-1`) were 10-request development runs and aren't reported.

---

# Project 1 starter code

This folder holds the starter code for Project 1. Read the
[Project 1 handout](https://www.composablesystems.org/courses/engineering-ai-systems/fa2026/projects/project-1/)
first. In it, you find the task, the rules, how to set up, the steps for each milestone, how to label, and how
to submit.

## Files

| File | What it holds |
|---|---|
| `RUBRIC.md` | the rubric: how we decide the right answer for every request |
| `data/public.jsonl` | the 150 public requests, each with its five candidate games |
| `data/public_answers.jsonl` | the right answer to each public request: the letters of the acceptable games, or an empty list when the right answer is to decline |
| `data/practice.jsonl` | the 10 public practice requests |
| `data/labeling.jsonl` | the 10 hidden labeling requests, without answers |
| `systems/single.py` | your single-call system; you write its instructions |
| `systems/compound.py` | your compound system; at the start, it has one example step |
| `score.py` | your scorer; you write `score()` |
| `p1/` | the starter code's package. Don't change it: on Gradescope, we use our own copy. |
| `p1/version.py` | the version of this starter code |
| `tests/` | the starter code's tests; they make no model calls |

## Commands

Run each command in this folder, with your environment active. Add `--help` to any command to see its options.

```
# Run a system on the first 10 public requests. Leave out --limit to run all 150.
# Give each run its own --out folder.
python -m p1.run systems/single.py --requests data/public.jsonl --limit 10 --out runs/single-1

# Score a run with your scorer.
python score.py runs/single-1

# Check the contracts and the call limits of a run.
python -m p1.contracts runs/compound-1

# Send your model steps' inputs to the course app, then download your team's labels.
python -m p1.labels send systems/compound.py --requests data/practice.jsonl
python -m p1.labels pull

# Check that at least 2 of your compound system's model steps are connected (Milestone 2), with your labels.
python -m p1.contracts systems/compound.py

# Step accuracy: run your system on the requests you labeled, then compare one model step's outputs with your labels.
python -m p1.run systems/compound.py --requests data/practice.jsonl --out runs/compound-practice
python -m p1.labels accuracy runs/compound-practice --step my_step --labels labels/my_step.jsonl

# Swap-in test: run your system with your labels in place of one model step's outputs.
python -m p1.run systems/compound.py --requests data/public.jsonl --ids-from labels/my_step.jsonl \
    --override my_step=labels/my_step.jsonl --out runs/swap-my_step

# Run the starter code's tests.
python -m pytest
```

To test your code without spending budget, set `P1_BACKEND=fake`. You then get the same fake reply to every model
call, `{"pick": null, "explanation": "fake backend: no model was called"}`, so a step with a different output type
fails with a contract error.
