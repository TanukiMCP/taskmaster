"""A small but complete project, used to walk the record through every phase."""

from coherence.record import Answer, Custom, Entry, Opening, OrderInput, Source, Work

REQUEST = "Build me a puzzle game where players win by thinking, not luck. How do players progress?"
QUESTIONS = ["How do players progress?"]


def root() -> Answer:
    return Answer(
        situation="A player who likes thinking opens the game, sees a board with every rule visible, and wins only by reasoning about it.",
        average="A casual puzzle game with random drops, daily login rewards, and power-ups bought with coins.",
        decision="A deterministic puzzle game where every outcome follows from rules the player can see.",
        excludes=["random drops", "paid power-ups"],
        reason="The person asked for winning by thinking rather than luck.",
        sources=[Source(kind="user", quote="players win by thinking, not luck")],
        wrong_if="Players who lose say it was bad luck.",
        confidence="high",
        opens=[Opening(id="first-board", kind="situation", question="What happens on the first board a player meets?")],
    )


def question() -> Answer:
    return Answer(
        serves="It answers the person's own question about progression.",
        situation="After solving a board, the player sees the next board add one new rule to the rules they already know.",
        average="Levels unlock stars and a world map, with difficulty raised by move limits.",
        decision="Each board introduces one new rule; progress is the set of rules a player has mastered.",
        excludes=["star ratings", "move limits as difficulty"],
        reason="Progress measured in understood rules keeps winning about thinking.",
        sources=[Source(kind="derived", ref="root")],
        wrong_if="Players advance without using the new rule.",
    )


def situation() -> Answer:
    return Answer(
        serves="It is the first moment the purpose has to hold.",
        situation="A new player sees a five by five board, reads the one rule shown beside it, and moves a piece to test it.",
        average="A tutorial with arrows and pop-up text explaining controls before play.",
        decision="The first board teaches its one rule by letting the player try it, with the rule always visible.",
        excludes=["tutorial pop-ups", "hidden rules"],
        reason="A visible rule tested by moving is reasoning, not instruction.",
        sources=[Source(kind="derived", ref="root")],
        wrong_if="New players can't state the rule after the first board.",
        opens=[Opening(id="ui-kit", kind="family", question="Which interface kit carries the board and its text?"),
               Opening(id="board", kind="job", question="What has to be true for the board to show its rule and accept a move?")],
    )


def family() -> Answer:
    return Answer(
        serves="It carries every screen the first board needs.",
        situation="The player reads the rule panel and the board without anything competing with them on screen.",
        average="A generic mobile game UI kit with glossy buttons and coin counters.",
        decision="Kenney's flat UI pack, with its panels kept and its colors replaced by the project's.",
        excludes=["glossy buttons", "coin counters"],
        reason="Flat panels keep attention on the rules.",
        sources=[Source(kind="work", ref="https://kenney.nl/assets/ui-pack")],
        work=Work(chosen="https://kenney.nl/assets/ui-pack", license="CC0", examined=["https://kenney.nl/assets/ui-pack", "https://opengameart.org"],
                  keep="Panel shapes, spacing, and states", change="Colors and text"),
        wrong_if="The panels draw the eye away from the board.",
        manifest=[Entry(id="kit.ui", kind="work", value="https://kenney.nl/assets/ui-pack", paths=["assets/kenney"]),
                  Entry(id="color.ink", kind="token", value="#1d2b53")],
    )


def job() -> Answer:
    return Answer(
        serves="It makes the first board's rule visible and testable.",
        situation="The board must show the rule text beside the grid and reveal a move's result after the player commits it.",
        average="A grid with instant animations and no explanation of results.",
        decision="The board shows the rule beside the grid and reveals each result after a short pause.",
        excludes=["instant results", "unexplained moves"],
        reason="A visible pause lets the player connect the move to the rule.",
        sources=[Source(kind="derived", ref="first-board")],
        custom=Custom(reason="No existing board renderer shows a rule beside its result", condition="The rule and result are visible together"),
        wrong_if="Players can't connect a result to the rule.",
        confidence="low",
        manifest=[Entry(id="copy.title", kind="content", value="Think, then move"),
                  Entry(id="timing.reveal", kind="deferred", note="Long enough for a new player to read the result before the next move")],
    )


EXPERIENCE = "A player opens the game and meets the first board [first-board], reads its rule, and wins by reasoning."
CONSTRUCTION = "The kit [ui-kit] carries the panels, and the board [board] shows the rule beside the grid."

ORDERS = [
    OrderInput(id="foundations", realizes=["ui-kit"], uses=["kit.ui", "color.ink"], touches=["styles/tokens.css"], checks="Tokens load"),
    OrderInput(id="board", realizes=["board"], uses=["copy.title", "timing.reveal", "color.ink"], after=["foundations"], touches=["src/board.js"],
               checks="The rule and the result are visible together"),
]
