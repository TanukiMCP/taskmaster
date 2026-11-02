import flow
from coherence import record as rec
from coherence.library import load_library
from coherence.record import Answer, Opening, Source
from coherence.views import derive_packet, walk_packet


def wide_record(siblings: int):
    """A record whose root has many settled children, so packets carry many sibling briefs."""
    r = rec.begin(flow.REQUEST, "idea", flow.QUESTIONS)
    root = flow.root()
    root.opens = [Opening(id=f"moment-{i}", kind="situation", question=f"What happens at moment {i}?") for i in range(siblings)]
    root.opens.append(Opening(id="last", kind="situation", question="What happens at the end?"))
    rec.settle(r, "root", "decide", root)
    rec.settle(r, "q1", "decide", flow.question())
    for i in range(siblings):
        rec.settle(r, f"moment-{i}", "decide", Answer(
            serves="It is one moment of the player's time.",
            situation=f"At moment {i} the player sees the board change and decides whether the rule still holds for them.",
            average="A cutscene that explains the change. " + "Filler words that make the brief long. " * 20,
            decision=f"Moment {i} shows the change on the board itself. " + "More detail about the decision. " * 20,
            excludes=["cutscenes"], reason="Seeing is reasoning.", sources=[Source(kind="derived", ref="root")],
            wrong_if="Players miss the change."))
    return r


def test_without_a_budget_packets_are_unchanged(monkeypatch):
    monkeypatch.delenv("COHERENCE_PACKET_TOKENS", raising=False)
    r = wide_record(12)
    packet = derive_packet(load_library(), r, r.points["last"])
    assert packet.count("[moment-") == 12 and "Left out" not in packet


def test_a_budget_keeps_what_the_step_depends_on_and_names_what_it_drops(monkeypatch):
    r = wide_record(40)
    monkeypatch.setenv("COHERENCE_PACKET_TOKENS", "1000")
    packet = derive_packet(load_library(), r, r.points["last"])
    assert len(packet) <= 1000 * 4
    assert "Question: What happens at the end?" in packet and "## The root" in packet and "Call settle with point='last'" in packet
    assert flow.REQUEST in packet
    assert "Left out to fit the packet budget" in packet
    assert "[moment-39]" in packet  # the most recent siblings are kept first


def test_the_walk_packet_keeps_the_names_it_must_pass_through(monkeypatch):
    r = wide_record(40)
    last = flow.situation()
    last.opens = []
    rec.settle(r, "last", "decide", last)
    monkeypatch.setenv("COHERENCE_PACKET_TOKENS", "1000")
    packet = walk_packet(r)
    assert len(packet) <= 1000 * 4 + len(packet.split("## The experience walk must name")[1])
    assert all(f"[moment-{i}]" in packet.split("## The experience walk must name")[1] for i in range(40))
