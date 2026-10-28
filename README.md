# Project 1: single call vs compound

Team: Adrika Pradhan and Odinaka Ogbujiagba. Engineering AI Systems, USI, Fall 2026.

Both systems take one person's request and five candidate games, and return the one game that meets every
requirement, or a decline when none does. The right answers follow `RUBRIC.md`. The starter code's own README is
kept at the end of this file.

## How the project fits together

Every system is a Python file that defines `VARIANT` and `answer(request) -> Answer`. The starter code (`p1/`,
which we don't change) does everything around it:

| Part | File | What it does |
| --- | --- | --- |
| Input and output types | `p1/types.py` | `Request` is the person's text plus five `Candidate` games (A to E), each with a fact `Card` (players, minutes, age, complexity weight, types, categories, mechanics) and a description. `Answer` is `pick` (a letter or `null` to decline) and `explanation`. |
| Model calls | `p1/llm.py` | `call_json(prompt, Type)` sends one prompt to the course model and parses the JSON reply into `Type`. It counts calls and refuses one past the limit: 1 for `single`, 10 for `compound`. |
| Prompt text | `p1/render.py` | `render_request(request)` turns a request and its five games into plain text for a prompt. |
| Declared steps | `p1/steps.py` | `@step` checks a step's input and output types, records them in the trace, and lets labels stand in for a step's output (the swap-in test). |
| Runner | `p1/run.py` | `python -m p1.run` runs a system on a file of requests and writes `answers.jsonl`, `traces.jsonl` and `summary.json` to a run folder. |
| Checks | `p1/contracts.py`, `p1/connected.py` | Call limits and contracts of a run; whether a compound system's model steps are connected. |
| Labels | `p1/labels.py`, `p1/app.py` | Send step inputs to the course app, pull labels, and measure a step's accuracy against them. |

---

## Milestone 1: single-call system and scorer (due Wed 7 Oct)

**Requirement:** a single-call system with our own prompt that passes the quick checks and does clearly better than
random guessing. Picking at random among five games or declining gets about 1 or 2 of 10 right.

The files below hold our Milestone 1 code, as we submitted it on Gradescope.

### `systems/single.py`: one model call per request

The whole system is one prompt and one call:

```python
def answer(request: Request) -> Answer:
    return call_json(f"{INSTRUCTIONS}\n\n{FORMAT}\n\n{render_request(request)}", Answer)
```

1. **`VARIANT = "single"`** tells the runner to allow exactly 1 model call per request. A second call fails.
2. **`INSTRUCTIONS`** is our summary of `RUBRIC.md`. In order, it tells the model to:
   - pick a game only if its card or description shows it meets *every* requirement, and otherwise decline; and
     not to use outside knowledge about the games;
   - find the requirements first: count the writer among the players ("I", "we", "us"), read play-time phrases
     such as "about an hour" as an upper limit, and leave out wishes ("would be nice", "would love");
   - check each game against each kind of requirement:
     - **Players:** the number must be inside the card's range. Use the description only if the card doesn't
       list players. Expansions don't count.
     - **Play time:** the card's longest time must fit the limit. Learning time isn't play time.
     - **Complexity:** the rubric's rules for light, heavy and medium, from the weight (1 to 5), the game types
       and what the description says about the rules. Conflicting clues mean "can't tell".
     - **Cooperative or competitive:** the "Cooperative Game" mechanic decides.
     - **Things to avoid** (fighting, violence, horror, timer, player elimination): a card tag always counts.
       The description can add a feature but can't remove a tag. Figures of speech don't count.
     - **Age:** the game's minimum age must not be above the child's age.
   - treat a game it can't check as unacceptable, and keep the explanation to one or two sentences.
3. **`FORMAT`** asks for JSON only: `{"pick": "<letter or null>", "explanation": "..."}`.
4. **`render_request(request)`** adds the request and the five games' cards and descriptions.
5. **`call_json(..., Answer)`** makes the single call and parses the reply straight into an `Answer`.

### `score.py`: how many answers in a run are right

`score(run_dir, answers)` returns `(right, total, wrong_ids)`. `main()` prints `"N of M right"`, then each
wrong id.

1. **Load the right answers.** It reads the answers file (by default `data/public_answers.jsonl`) into a dict:
   request id → list of acceptable letters. An empty list means the right answer is to decline.
2. **Find the run's answers.** It accepts a run folder (it reads `answers.jsonl` inside) or the answers file
   itself.
3. **Check every answer.** For each line it adds 1 to `total`, then:
   - an answer with an `"error"`, or an id missing from the answers file, is wrong;
   - a pick is right if it is one of the acceptable letters;
   - a decline (`pick` is `null`) is right only if the list of acceptable letters is empty.
4. Every request in the run counts, so a run on 10 requests is scored out of 10.

### Milestone 1 results

| Run | System | Right | Model calls | Cost |
| --- | --- | --- | --- | --- |
| `runs/m1-single-test` | `systems/single.py`, first 10 public requests | 5 of 10 | 10 (1 per request) | $0.0041 |
| `runs/m1-single-test-2` | same code, run again | 6 of 10 | 10 (1 per request) | $0.0022 |

Both runs pass the call-limit and contract checks (`python -m p1.contracts`). 5 to 6 of 10 is clearly better than
random guessing. On these 10 requests the system declined 4 times in both runs.

---

## Milestone 2: compound system and labels (due Fri 9 Oct)

**Requirement:** a compound system with at least 2 connected model steps that passes the quick checks and does
clearly better than random guessing, plus labels for the 10 public practice requests.

### `systems/compound.py`: two model steps and two code steps

At most 7 model calls per request (the limit is 10). On the public requests it made at most 4.

| Order | Step | Kind | Input → output |
| --- | --- | --- | --- |
| 1 | `read_request` | model, `@step` | `RequestText` → `Requirements` |
| 2 | `check_card` | plain Python | `Requirements` + one game's `Card` → a check per requirement |
| 3 | `read_description` | model, `@step` | `DescriptionQuestions` → `DescriptionFacts` |
| 4 | `answer` | plain Python | everything above → `Answer` |

**Step 1, `read_request` (model).** It gets only the person's text, not the games.

- Its output, `Requirements`, has one field per kind of requirement: `players`, `max_minutes`,
  `complexity` (light/medium/heavy), `mode` (cooperative/competitive), `child_age`, and five yes/no fields
  `no_fighting`, `no_violence`, `no_horror`, `no_timer` and `no_elimination`. Each field has fixed choices, so each
  one can be labeled.
- The prompt `READ_REQUEST` gives worked examples ("me and my three friends" is 4, "an hour tops" is 60) and says
  to leave out wishes.
- If the reply doesn't fit `Requirements`, it asks once more. If the second reply doesn't fit either, `answer`
  declines.

**Step 2, `check_card` (code).** It checks one game's card against the requirements. Each requirement gets one of
four results: `meets`, `breaks`, `can't tell`, or `ask` (the card can't settle it, so ask the description).

- **Players, play time, age:** exact range checks on the card. If the card doesn't list one, the result is
  `ask`.
- **Cooperative or competitive:** whether the card has the "Cooperative Game" mechanic.
- **Things to avoid:** the rubric's tags (`TAGS`, e.g. Horror or Zombies for horror). A tag means `breaks`.
  Without a tag the result is `ask`.
- **Complexity:** `is_light`, `is_heavy` and `check_complexity` are the rubric's rules in code. `check_card` tries
  all three things the description could say about the rules ("easy", "complex", "unclear"):
  - if all three give the same result, the card alone decides;
  - if none of them gives `meets`, the result is `can't tell`;
  - otherwise the result is `ask`.

**Step 3, `read_description` (model).** It runs only for a game the card hasn't ruled out, and asks only the
questions the card left open.

- Its input, `DescriptionQuestions`, is the game's name, its description, and an `ask_...` flag per open question.
- `QUESTIONS` holds one prompt piece per question: players, minutes, age, rules, fighting, violence, horror,
  timer and elimination. Each piece spells out what counts and what doesn't.
- Its output, `DescriptionFacts`, has one field per question. Answers to questions that weren't asked are thrown
  away.
- **Our final change:** an `"easy"` or `"complex"` rules answer only stands if `rules_quote` is at least two words
  that really appear in the description (checked by `quoted`). Otherwise it becomes `"unclear"`.
- If the reply doesn't fit, every answer stays empty, so the game can't be picked.
- `apply_facts` then replaces each `ask` with `meets`, `breaks` or `can't tell` from those facts.

**Step 4, `answer` (code).**

1. Run `read_request` once.
2. Run `check_card` on all five games. A game with any `breaks` or `can't tell` is dropped. The first game
   that meets everything on its card alone is picked straight away, with no description call.
3. For each remaining game, run `read_description`, apply the facts, and pick the first game that now meets
   everything.
4. If no game is left, decline. The explanation gives one reason per game.

**Why this design.** In the single-call runs the model often got simple range checks wrong, or marked a game as
meeting everything and then declined anyway. Here the model only reads language (the request, a description),
and code does every comparison and the final decision. The model is only asked questions the card can't answer.

### Labels

We sent the inputs of both model steps to the course app (`python -m p1.labels send`), labeled them there, and
downloaded them with `python -m p1.labels pull`:

| File | Step | Labeled inputs |
| --- | --- | --- |
| `labels/read_request.jsonl` | `read_request` | 20: 10 public practice requests (P…) and 10 hidden labeling requests (L…) |
| `labels/read_description.jsonl` | `read_description` | 14: 9 from practice requests and 5 from labeling requests (`read_description` only runs when the card leaves a question open) |

### Milestone 2 results

| Check | Result |
| --- | --- |
| `runs/m2-compound-test`, first 10 public requests | 10 of 10 right, 15 model calls (at most 2 per request), $0.0019 |
| `runs/m2-compound-test-2`, same code, run again | 10 of 10 right, 15 model calls, $0.0019 |
| Call limits and contracts (`python -m p1.contracts runs/m2-compound-test-2`) | passed |
| Connected model steps (`python -m p1.contracts systems/compound.py`) | passed: `read_request` and `read_description` are both connected |
| `read_request` vs our labels, `runs/labeling-compound` | 10 of 10, every field right |
| `read_description` vs our labels, `runs/labeling-compound` | 5 of 5, every field right |

The full results on all 150 public requests and the 50 checkpoint requests are under [Results](#results) below.

---

## How to test, step by step

You need Python 3.10 or newer (the Mac's built-in Python 3.9 is too old). Run each command from this folder.

**Setup, once:**

```bash
uv venv --python 3.12 .venv
```

```bash
source .venv/bin/activate
```

```bash
uv pip install -e ".[test]"
```

Without `uv`: `python3.12 -m venv .venv`, then `pip install -e ".[test]"`.

**Every new terminal:** turn on the environment and load the token. `.env` holds the two `export` lines from the
course app's Project 1 page, `P1_ENDPOINT` and `P1_TOKEN`. It is in `.gitignore`, so it is never committed.

```bash
source .venv/bin/activate
```

```bash
source .env
```

**1. Starter tests** (no model calls, free). Expect 39 passed.

```bash
python -m pytest
```

**2. Milestone 1 scorer on saved runs** (free). Expect `137 of 150 right` and `48 of 50 right`.

```bash
python score.py runs/compound-fix-1
```

```bash
python score.py runs/checkpoint-compound-fix --answers data/checkpoint_answers.jsonl
```

**3. Milestone 1 single-call system** (uses the team budget, about $0.004). Give each run a new `--out` folder.

```bash
python -m p1.run systems/single.py --requests data/public.jsonl --limit 10 --out runs/m1-single-test-3
```

```bash
python score.py runs/m1-single-test-3
```

```bash
python -m p1.contracts runs/m1-single-test-3
```

**4. Milestone 2 compound system** (uses the team budget, about $0.002).

```bash
python -m p1.run systems/compound.py --requests data/public.jsonl --limit 10 --out runs/m2-compound-test-3
```

```bash
python score.py runs/m2-compound-test-3
```

```bash
python -m p1.contracts runs/m2-compound-test-3
```

**5. Milestone 2 checks** (free).

```bash
python -m p1.contracts systems/compound.py
```

```bash
python -m p1.labels accuracy runs/labeling-compound --step read_request --labels labels/read_request.jsonl
```

```bash
python -m p1.labels accuracy runs/labeling-compound --step read_description --labels labels/read_description.jsonl
```

**Other runs.** Leave out `--limit 10` to run all 150 public requests. Use
`--requests data/checkpoint_requests.jsonl` and score with `--answers data/checkpoint_answers.jsonl` for the 50
checkpoint requests. Set `P1_BACKEND=fake` to run without the model, at no cost.

### What the starter tests cover

| File | What it checks |
| --- | --- |
| `tests/test_score.py` | `score.py` prints the count and then the wrong ids, and accepts another answers file with `--answers`. |
| `tests/test_starter.py` | The data fits the types; the single variant refuses a second call; a compound system is limited to 10 calls, all inside steps; contracts are checked and reported; traces, the swap-in test, step accuracy and the model backends work. |
| `tests/test_connected.py` | The connected-steps check: unused or pointless steps don't count as connected; steps that feed the answer do. |
| `tests/test_labels_app.py` | `p1.labels send` and `pull`: sending step inputs without the model, and pulled labels working for the swap-in test and step accuracy. |

---

## Checkpoint and final (13 and 16 Oct)

The sections below are the write-up of our final submission: results on all 150 public requests and the 50
checkpoint requests, error analysis, and the one change we made and measured. The single-call numbers in them
(`single-3`, `single-4`, `checkpoint-single`) come from a later version of `systems/single.py`. That version had
a longer prompt, asked the model to list the requirements and check each game before picking, and declined when
the reply was broken. It is in the git history at commit `0c375f8`. The compound numbers come from the
`systems/compound.py` in this folder.

## Results

Every number below comes from a run folder in `runs/`. Cost and time are per request; the time is the median of
the requests' own times (the runner works on 4 requests at once).

### Public requests (150), two runs of each system

| System | Run | Right | Cost per request | Median time |
| --- | --- | --- | --- | --- |
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
| --- | --- | --- |
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
| --- | --- | --- | --- | --- |
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
| --- | --- | --- |
| H1-006 | Read "a game that everyone can play together" as a cooperative requirement, which ruled out E, a competitive game that fit everything else. | `read_request` |
| H1-016 | Answered that the rules are "complex" from "planning and strategy" in the description, which ruled out D (strategy, weight 2.89, medium by the card). | `read_description` |
| H1-030 | Turned the wish "It would be nice if the game can be played either PvP or co-op" into a cooperative requirement, which ruled out C and E. | `read_request` |
| H1-047 | Answered that the rules are "complex" with the evidence "none", which ruled out B (weight 3.3, medium by the card). | `read_description` |
| H1-088 | Answered that the rules are "complex" with the evidence "none", which ruled out D (weight 2.8, medium by the card). | `read_description` |

| Group | Count |
| --- | --- |
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
| --- | --- | --- |
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
| --- | --- | --- |
| `runs/single-3`, `runs/single-4` | single call | public |
| `runs/compound-2`, `runs/compound-3` | compound, before the change | public |
| `runs/compound-fix-1`, `runs/compound-fix-2` | compound, after the change | public |
| `runs/checkpoint-single`, `runs/checkpoint-compound` | single call; compound before the change | checkpoint |
| `runs/checkpoint-compound-fix` | compound, after the change | checkpoint |
| `runs/labeling-compound` | compound, after the change | hidden labeling (for step accuracy) |
| `runs/m1-single-test`, `runs/m1-single-test-2` | Milestone 1 single call (current `systems/single.py`) | first 10 public |
| `runs/m2-compound-test`, `runs/m2-compound-test-2` | compound, after the change | first 10 public |

Earlier runs (`single-1`, `single-2`, `compound-1`) were 10-request development runs and aren't reported.

---

# Project 1 starter code

This folder holds the starter code for Project 1. Read the
[Project 1 handout](https://www.composablesystems.org/courses/engineering-ai-systems/fa2026/projects/project-1/)
first. In it, you find the task, the rules, how to set up, the steps for each milestone, how to label, and how
to submit.

## Files

| File | What it holds |
| --- | --- |
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
