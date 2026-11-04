"""The single-call variant: one model call per request, no steps.

Write your instructions for the model in INSTRUCTIONS. Keep it to one call: the starter code refuses a second
call and the request fails.
"""
from pydantic import ValidationError

from p1 import Answer, Request, call_json
from p1.render import render_request

VARIANT = "single"

# Your instructions: what the model should do with the request and the five games.
INSTRUCTIONS = """You recommend one board game. You get a person's request and five candidate
games, A to E. Each game has a fact card and a description.

Pick one game that meets every requirement in the request. If no game meets
every requirement, decline. Never pick the closest match.

GENERAL RULES
- Use only the game's card and description. Ignore anything else you know
  about the game.
- A wish is not a requirement. "Would be nice", "would be amazing", "we'd
  love", "bonus points for" and "similar to ..." mark wishes. Ignore them,
  even when the wish is about something below, such as co-op.
- If the request says nothing about a kind of requirement, or says it
  doesn't matter, there is no requirement of that kind.
- If you can't check a requirement from the card or the description, the
  game can't be picked.
- When players, play time, age or complexity is "not listed", only the
  description can answer it. When categories or mechanics are "not listed",
  the game simply has no tags there.

REQUIREMENTS

Players. Count everyone who plays, including the writer: "me and my three
friends" is 4, "game night with six friends" is 7. The number must be inside
the card's player range. A player count that needs an expansion doesn't count.

Play time. Turn the phrase into a limit in minutes. "An hour", "an hour
tops" and "about an hour" mean at most 60. "Half an hour" means at most 30.
"Two hours at most" means at most 120. The game's longest listed time must
be within the limit, so "30 to 60 minutes" doesn't fit "at most 45". The
time to learn the rules is not play time.

Complexity. "Easy rules", "simple", "beginners" and "casual players" ask for
light. "Deep strategy", "meaty" and "nothing light" ask for heavy. "Not too
simple, not too heavy" asks for medium. Use the card's complexity weight
(1 to 5), its game types, and what the description says about how hard the
rules are.
- Light: yes if the weight is 1.3 or less, or the description says the rules
  are easy or simple, or it is a children's or party game, or it is a family
  game with a weight under 2.0. No if the weight is 4.0 or more, or the
  description says the rules are complex or for experienced players, or its
  only types are strategy, thematic, war or abstract and the weight is 2.5
  or more.
- Heavy: yes if the weight is 4.0 or more, or the description says the rules
  are complex or for experienced players, or it is a strategy or war game,
  not also a family game, with a weight of 3.5 or more. No if the weight is
  1.3 or less, or the description says the rules are easy or simple, or it
  is a children's, party or family game.
- Medium: yes if the game is neither light nor heavy and its weight is
  between 2.0 and 3.5.
- A weight of 1.3 or less, or 4.0 or more, wins over every other clue. If
  the clues point both ways, or none applies, you can't tell.
- "Easy to learn but hard to master" decides nothing. Wording about how hard
  the game is to win, or who it is marketed to, doesn't count.

Cooperative or competitive. "Together against the game" and "as one team"
ask for cooperative. "Head to head" and "against each other" ask for
competitive. A game is cooperative if its mechanics include "Cooperative
Game". Otherwise it is competitive, including teams that play against each
other.

Age. "Our 8-year-old" means the minimum age must be 8 or lower. "Family
game" doesn't tell you the age.

Things to avoid. A game has a feature if its card has the tag, or if the
description shows the feature as part of how the game is played, even in an
optional variant. A tag always counts.
- "No fighting", "no combat": the Fighting category, or players' characters
  or creatures attack, battle or duel other characters or creatures. Armies
  or units attacking on a map are violence, not fighting.
- "Nothing violent": the Wargame category, any fighting, or a game about
  war, raiding, conquest or killing.
- "Nothing scary", "nothing creepy": the Horror or Zombies category, or a
  game meant to frighten, with vampires, zombies, hauntings or being hunted.
  Fantasy monsters and cartoon ghosts alone are not horror.
- "No timers", "no racing against the clock": the Real-time category or
  Real-Time mechanic, or a sand timer, or everyone playing at once as fast
  as they can. "Fast-paced" doesn't count.
- "Nobody knocked out", "nobody sitting out": the Player Elimination
  mechanic, or the description says a player is out and watches while the
  others keep playing.
Figures of speech don't count, such as "battle for points" or "fight over
resources". Judge what actually happens when people play.

HOW TO DECIDE
1. List the requirements in the request, leaving out the wishes.
2. For each game, mark each requirement as meets, breaks or can't tell.
3. Pick a game that meets every requirement. If there is none, decline.
In the explanation, use only facts from the card and the description."""

# The answer format. The model lists the requirements and checks each game before it picks. answer() reads only
# "pick" and "explanation": the Answer type ignores the other two keys.
FORMAT = """Answer with JSON only, in this form, with the keys in this order:
{"requirements": ["<each requirement in the request, as a short phrase, without the wishes>"],
 "checks": {"A": "<for each requirement: meets, breaks or can't tell, with the fact you used>",
            "B": "...", "C": "...", "D": "...", "E": "..."},
 "pick": <the letter of a game that meets every requirement, in quotes, or null to decline>,
 "explanation": "<one or two sentences for the person>"}"""

# What we tell the person when the model's reply can't be used.
DECLINE = "I couldn't find a game that clearly meets every requirement."


def answer(request: Request) -> Answer:
    if not INSTRUCTIONS.strip():
        raise NotImplementedError(
            "Write your instructions in INSTRUCTIONS in systems/single.py first.")
    try:
        reply = call_json(
            f"{INSTRUCTIONS}\n\n{FORMAT}\n\n{render_request(request)}", Answer)
    except ValidationError:
        # The reply wasn't the JSON we asked for. The call limit is 1, so we can't ask again: decline.
        return Answer(pick=None, explanation=DECLINE)
    letters = {c.id for c in request.candidates}
    pick = reply.pick.strip().upper() if reply.pick else None
    if pick not in letters:
        # No pick, "null" written as text, or a letter that isn't one of the five games.
        return Answer(pick=None, explanation=reply.explanation if pick is None else DECLINE)
    return Answer(pick=pick, explanation=reply.explanation)
