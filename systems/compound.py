"""The compound variant: our system, built from declared steps.

The design, in the order it runs for one request:
1. read_request (model step): reads only the person's request and lists its requirements.
2. check_card (plain Python): checks each game's fact card against the requirements. The card settles most of them
   exactly: players, play time, age, cooperative or competitive, and the tags for things to avoid.
3. read_description (model step): for a game the card hasn't ruled out, answers only the questions the card
   couldn't, from the game's description.
4. answer (plain Python): picks the first game that meets every requirement, or declines.

At most 7 model calls per request: read_request once, with one retry, and read_description once per game.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from p1 import Answer, Candidate, Card, Request, call_json, step

VARIANT = "compound"

MEETS, BREAKS, CANT_TELL, ASK = "meets", "breaks", "can't tell", "ask"


# ---- Step 1 (model): read the request -------------------------------------------------------------------------------

class RequestText(BaseModel):
    """The input of read_request: what the person wrote, without the games."""
    text: str


class Requirements(BaseModel):
    """The output of read_request. Every field has fixed choices, so we label all of them."""
    players: Optional[int] = Field(description="How many people will play, or null if the request doesn't say or says it doesn't matter")
    max_minutes: Optional[int] = Field(description="The play time limit in minutes, or null")
    complexity: Optional[Literal["light", "medium", "heavy"]] = Field(description="The complexity asked for, or null")
    mode: Optional[Literal["cooperative", "competitive"]] = Field(description="Cooperative or competitive, or null")
    child_age: Optional[int] = Field(description="The age of the youngest child who will play, or null")
    no_fighting: bool
    no_violence: bool
    no_horror: bool
    no_timer: bool
    no_elimination: bool


READ_REQUEST = """You read one person's request for a board game and list its requirements.

A wish is not a requirement. "Would be nice", "would be amazing", "we'd love", "bonus points for" and
"similar to ..." mark wishes. Leave a wish out, even when it is about something below, such as co-op.
If the request says nothing about a requirement, or says it doesn't matter, it has none of that kind.

- players: count everyone who will play, including the writer. "Me and my brother" is 2. "Me and my three friends"
  is 4. "Game night with six friends" is 7. null if the request doesn't say, or says the number doesn't matter.
- max_minutes: the play time limit in minutes. "An hour", "an hour tops" and "about an hour" are 60. "Half an hour"
  is 30. "Two hours at most" is 120. null if there is no limit.
- complexity: "light" for "easy rules", "simple", "beginners", "never play board games" or "casual players".
  "heavy" for "deep strategy", "meaty" or "nothing light". "medium" for "not too simple, not too heavy".
  null if the request doesn't say.
- mode: "cooperative" for "together against the game", "team up against the game" or "as one team". "competitive"
  for "head to head" or "against each other". null if the request doesn't say.
- child_age: the age of the youngest child who will play, when the request gives it: "our 8-year-old" is 8.
  null if no child's age is given. An adult's age is not a requirement.
- no_fighting: true for "no fighting" or "no combat".
- no_violence: true for "nothing violent".
- no_horror: true for "nothing scary" or "nothing creepy".
- no_timer: true for "no timers" or "no racing against the clock".
- no_elimination: true for "nobody knocked out" or "nobody sitting out".

Answer with JSON only, in this form:
{"players": <number or null>, "max_minutes": <number or null>, "complexity": <"light", "medium", "heavy" or null>,
 "mode": <"cooperative", "competitive" or null>, "child_age": <number or null>, "no_fighting": <true or false>,
 "no_violence": <true or false>, "no_horror": <true or false>, "no_timer": <true or false>,
 "no_elimination": <true or false>}"""


@step
def read_request(request: RequestText) -> Requirements:
    prompt = f"{READ_REQUEST}\n\nRequest:\n{request.text.strip()}"
    try:
        return call_json(prompt, Requirements)
    except ValidationError:
        # The reply didn't fit Requirements. Without the requirements we can't check any game, so ask once more.
        # If the second reply doesn't fit either, the error goes to answer(), which declines.
        return call_json(prompt, Requirements)


# ---- Step 2 (plain Python): check a game's card ---------------------------------------------------------------------

# The card tags that show a feature, from section 3 of the rubric: (categories, mechanics).
TAGS = {
    "fighting": ({"Fighting"}, set()),
    "violence": ({"Wargame", "Fighting"}, set()),
    "horror": ({"Horror", "Zombies"}, set()),
    "timer": ({"Real-time"}, {"Real-Time"}),
    "elimination": (set(), {"Player Elimination"}),
}
RULES_WORDINGS = ("easy", "complex", "unclear")


def is_light(card: Card, rules: str) -> Optional[bool]:
    """Is the game light? True, False, or None for can't tell. rules is what the description says about the rules."""
    weight = card.complexity.weight if card.complexity else None
    if weight is not None and weight <= 1.3:
        return True
    if weight is not None and weight >= 4.0:
        return False
    types = set(card.types)
    yes, no = rules == "easy", rules == "complex"
    if weight is not None:  # without a weight on the card, only the description's wording can decide
        yes = yes or bool(types & {"children's", "party"}) or ("family" in types and weight < 2.0)
        no = no or (bool(types) and types <= {"strategy", "thematic", "war", "abstract"} and weight >= 2.5)
    return None if yes == no else yes


def is_heavy(card: Card, rules: str) -> Optional[bool]:
    """Is the game heavy? True, False, or None for can't tell."""
    weight = card.complexity.weight if card.complexity else None
    if weight is not None and weight >= 4.0:
        return True
    if weight is not None and weight <= 1.3:
        return False
    types = set(card.types)
    yes, no = rules == "complex", rules == "easy"
    if weight is not None:
        yes = yes or (bool(types & {"strategy", "war"}) and "family" not in types and weight >= 3.5)
        no = no or bool(types & {"children's", "party", "family"})
    return None if yes == no else yes


def check_complexity(level: str, card: Card, rules: str) -> str:
    """Does the game have the complexity the request asks for, given what the description says about the rules?"""
    if level == "medium":
        if is_light(card, rules) or is_heavy(card, rules):
            return BREAKS
        weight = card.complexity.weight if card.complexity else None
        return MEETS if weight is not None and 2.0 <= weight <= 3.5 else CANT_TELL
    fits = is_light(card, rules) if level == "light" else is_heavy(card, rules)
    return CANT_TELL if fits is None else MEETS if fits else BREAKS


def check_card(req: Requirements, card: Card) -> dict:
    """Check one game's card against the requirements. Returns requirement -> "meets", "breaks", "can't tell", or
    "ask" when the description has to answer it."""
    checks = {}
    if req.players is not None:
        if card.players is None:
            checks["players"] = ASK
        else:
            checks["players"] = MEETS if card.players[0] <= req.players <= card.players[-1] else BREAKS
    if req.max_minutes is not None:
        if card.minutes is None:
            checks["minutes"] = ASK
        else:
            checks["minutes"] = MEETS if card.minutes[-1] <= req.max_minutes else BREAKS
    if req.child_age is not None:
        if card.age is None:
            checks["age"] = ASK
        else:
            checks["age"] = MEETS if card.age <= req.child_age else BREAKS
    if req.mode is not None:
        cooperative = "Cooperative Game" in card.mechanics
        checks["mode"] = MEETS if cooperative == (req.mode == "cooperative") else BREAKS
    if req.complexity is not None:
        # Try each thing the description could say about the rules. If they all give the same result, the card
        # decides. If none of them gives "meets", the game can't be picked whatever the description says.
        results = {check_complexity(req.complexity, card, rules) for rules in RULES_WORDINGS}
        if len(results) == 1:
            checks["rules"] = results.pop()
        elif MEETS not in results:
            checks["rules"] = CANT_TELL
        else:
            checks["rules"] = ASK
    for feature, (categories, mechanics) in TAGS.items():
        if getattr(req, "no_" + feature):
            tagged = bool(categories & set(card.categories)) or bool(mechanics & set(card.mechanics))
            checks[feature] = BREAKS if tagged else ASK  # a tag always counts; without one, the description decides
    return checks


# ---- Step 3 (model): read a game's description ----------------------------------------------------------------------

class DescriptionQuestions(BaseModel):
    """The input of read_description: one game's description, and which questions the card left open."""
    name: str
    description: str
    ask_players: bool = False
    ask_minutes: bool = False
    ask_age: bool = False
    ask_rules: bool = False
    ask_fighting: bool = False
    ask_violence: bool = False
    ask_horror: bool = False
    ask_timer: bool = False
    ask_elimination: bool = False


class DescriptionFacts(BaseModel):
    """The output of read_description. A field is null when its question wasn't asked, or, for the four numbers,
    when the description doesn't state it. We label every field except evidence, which is free text."""
    evidence: str = ""
    min_players: Optional[int] = None
    max_players: Optional[int] = None
    minutes: Optional[int] = None
    min_age: Optional[int] = None
    rules_quote: str = ""
    rules: Optional[Literal["easy", "complex", "unclear"]] = None
    fighting: Optional[bool] = None
    violence: Optional[bool] = None
    horror: Optional[bool] = None
    timer: Optional[bool] = None
    elimination: Optional[bool] = None


READ_DESCRIPTION = """You answer questions about one board game, using only its description below. Don't use
anything else you know about the game. Judge what the description shows actually happens when people play, not
isolated words, creature names or the title. A feature counts even if it is only in an optional variant or in one
scenario in the box."""

# One entry per question: the JSON keys it fills, the form of the answer, and what we ask.
QUESTIONS = {
    "players": (
        '"min_players": <number or null>, "max_players": <number or null>',
        "min_players, max_players: the number of players the description states for the base game, not with an "
        "expansion. If it states one number, use it for both. null if it doesn't state a number of players."),
    "minutes": (
        '"minutes": <number or null>',
        "minutes: the play time the description states, in minutes, and the longest if it gives a range. The time to "
        "learn the rules is not play time. null if it doesn't state a play time."),
    "age": (
        '"min_age": <number or null>',
        'min_age: the minimum age the description states: "ages 8 and up" is 8. "Family game" is not an age. null if '
        "it doesn't state an age."),
    "rules": (
        '"rules_quote": "<the exact words, or empty>", "rules": <"easy", "complex" or "unclear">',
        "rules_quote: copy the exact words from the description that say how easy or hard the game's rules are, or "
        "leave it empty if there are none. Most descriptions have none. "
        'rules: "easy" if those words say the rules are easy or simple, or that the game is lighter than similar '
        'games. "complex" if they say the rules are complex or that the game is for experienced players. "unclear" '
        'if rules_quote is empty, or if the words say both, such as "easy to learn, but challenging to master". '
        "Strategy, depth, planning, player interaction and replayability are not about the rules. Neither is wording "
        "about how hard the game is to win, about one part of the game, about an optional variant, about changes "
        'from another edition, or about who the game is marketed to ("family game", "casual audience").'),
    "fighting": (
        '"fighting": <true or false>',
        "fighting: true if the players' characters or creatures fight other characters or creatures as something "
        "players do: they attack, battle or duel them. false for armies, fleets or units attacking on a map, for "
        'raiding or conquering as a way to score, for figures of speech ("fight over resources", "battle for '
        'points"), for contests that are only called duels or battles, for a penalty the game calls an attack, for '
        'abstract captures as in chess, and for a genre label alone such as "dungeon crawler".'),
    "violence": (
        '"violence": <true or false>',
        "violence: true if the game is about war, raiding, pillaging, conquest, killing or other violence, or if "
        "characters or creatures fight each other. Battles between armies, fleets or units count. false for figures "
        "of speech, for a penalty the game calls an attack, and for a grim backstory."),
    "horror": (
        '"horror": <true or false>',
        "horror: true if the game is meant to frighten or disturb: it presents horror creatures (vampires, zombies, "
        "werewolves, Cthulhu-style monsters), threatening ghosts or hauntings, being hunted, or gore as something "
        "frightening. false for generic fantasy monsters and dungeons, harmless or helpful ghosts, undead or demons "
        "as enemies in heroic fantasy or comic games, cartoon spookiness in family or children's games, a horror "
        "word only in a licensed title, murder mysteries, and one horror character among many."),
    "timer": (
        '"timer": <true or false>',
        "timer: true if play involves racing a clock or a sand timer, a timed turn, or everyone playing at once as "
        "fast as they can. false for a countdown track that ends the game, for choosing actions at the same time "
        'without racing, for words about pace ("fast-paced"), for racing as a theme, and for an optional timer the '
        "rules don't require."),
    "elimination": (
        '"elimination": <true or false>',
        "elimination: true if a player can be knocked out and has to sit and watch while the others keep playing, "
        'for the rest of the game or of a round, including "last player standing" with three or more players. false '
        "for losing points, cards or pieces while still playing, for a cooperative team losing together, for a "
        "two-player game where knocking the other player out ends the game, and for a knocked-out player who keeps "
        "playing in another role."),
}


@step
def read_description(questions: DescriptionQuestions) -> DescriptionFacts:
    asked = [name for name in QUESTIONS if getattr(questions, "ask_" + name)]
    form = ", ".join(QUESTIONS[name][0] for name in asked)
    prompt = (READ_DESCRIPTION + "\n\nQuestions:\n" + "\n".join("- " + QUESTIONS[name][1] for name in asked)
              + "\n\nAnswer with JSON only, in this form, with the keys in this order:\n"
              + '{"evidence": "<the words from the description that you rely on, or none>", ' + form + "}"
              + f"\n\nGame: {questions.name}\nDescription:\n{questions.description.strip()}")
    try:
        facts = call_json(prompt, DescriptionFacts)
    except ValidationError:
        # The reply didn't fit DescriptionFacts. With every field empty, the open questions stay unanswered, so
        # answer() won't pick this game.
        return DescriptionFacts()
    # Keep only the answers to the questions we asked.
    keep = {"evidence"}
    for name in asked:
        keep.update({"players": {"min_players", "max_players"}, "minutes": {"minutes"}, "age": {"min_age"},
                     "rules": {"rules_quote", "rules"}}.get(name, {name}))
    facts = DescriptionFacts(**facts.model_dump(include=keep))
    if facts.rules in ("easy", "complex") and not quoted(facts.rules_quote, questions.description):
        # "easy" or "complex" needs words from the description to stand on. Without them, the rubric's answer is
        # "unclear", whatever the model guessed.
        facts.rules = "unclear"
    return facts


def quoted(quote: str, description: str) -> bool:
    """Is quote words from the description, ignoring case, spacing and the kind of quote marks? A quote of fewer
    than two words, such as "none", doesn't count: it could match almost any description."""
    def norm(text: str) -> str:
        text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
        return " ".join(text.lower().split())
    quote = norm(quote).strip(' "\'.')
    return len(quote.split()) >= 2 and quote in norm(description)


def apply_facts(req: Requirements, card: Card, checks: dict, facts: DescriptionFacts) -> dict:
    """Replace each "ask" in checks with the result from the description's facts."""
    done = dict(checks)
    if checks.get("players") == ASK:
        if facts.min_players is None or facts.max_players is None:
            done["players"] = CANT_TELL
        else:
            done["players"] = MEETS if facts.min_players <= req.players <= facts.max_players else BREAKS
    if checks.get("minutes") == ASK:
        done["minutes"] = CANT_TELL if facts.minutes is None else MEETS if facts.minutes <= req.max_minutes else BREAKS
    if checks.get("age") == ASK:
        done["age"] = CANT_TELL if facts.min_age is None else MEETS if facts.min_age <= req.child_age else BREAKS
    if checks.get("rules") == ASK:
        done["rules"] = CANT_TELL if facts.rules is None else check_complexity(req.complexity, card, facts.rules)
    for feature in TAGS:
        if checks.get(feature) == ASK:
            has_it = getattr(facts, feature)
            done[feature] = CANT_TELL if has_it is None else BREAKS if has_it else MEETS
    return done


# ---- Step 4 (plain Python): decide ----------------------------------------------------------------------------------

NAMES = {"players": "the number of players", "minutes": "the play time", "age": "the minimum age",
         "mode": "cooperative or competitive", "rules": "the complexity", "fighting": "no fighting",
         "violence": "no violence", "horror": "nothing scary", "timer": "no timer", "elimination": "nobody knocked out"}


def pick(game: Candidate, checks: dict) -> Answer:
    met = ", ".join(NAMES[name] for name in checks) or "you gave no requirements"
    return Answer(pick=game.id, explanation=f"{game.name} meets every requirement in your request: {met}.")


def decline(reasons: list) -> Answer:
    return Answer(pick=None, explanation="No game clearly meets every requirement. " + " ".join(reasons))


def answer(request: Request) -> Answer:
    try:
        req = read_request(RequestText(text=request.request))
    except ValidationError:
        return decline(["I couldn't work out the requirements in the request."])
    reasons = []  # one sentence per game we can't pick
    open_games = []  # games the card hasn't ruled out, with questions for the description
    for game in request.candidates:
        checks = check_card(req, game.card)
        failed = [name for name, result in checks.items() if result in (BREAKS, CANT_TELL)]
        if failed:
            reasons.append(f"{game.id}: {checks[failed[0]]} for {NAMES[failed[0]]}.")
        elif ASK not in checks.values():
            return pick(game, checks)  # the card alone shows the game meets everything
        else:
            open_games.append((game, checks))
    for game, checks in open_games:
        asked = {"ask_" + name: True for name, result in checks.items() if result == ASK}
        facts = read_description(DescriptionQuestions(name=game.name, description=game.description, **asked))
        checks = apply_facts(req, game.card, checks, facts)
        failed = [name for name, result in checks.items() if result != MEETS]
        if not failed:
            return pick(game, checks)
        reasons.append(f"{game.id}: {checks[failed[0]]} for {NAMES[failed[0]]}.")
    return decline(sorted(reasons))
