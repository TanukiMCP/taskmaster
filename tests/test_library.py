from taskmaster.library import SCOPE_LABELS, SCOPES, SITUATIONS, VERIFY_STEP, load_library


def test_procedure_has_all_steps_in_order():
    lib = load_library()
    assert sorted(lib.procedure.steps) == list(range(0, VERIFY_STEP + 1))
    assert lib.procedure.steps[3].name == "Name the jobs and port components from real products"
    assert "The chain" in lib.procedure.sections
    assert lib.procedure.steps[10].text.startswith("10. Verify and correct")
    assert "Remaining limits" in lib.procedure.limits
    assert "Keeping is a stated decision" in lib.procedure.working_rules
    assert "Before each SOP step" in lib.procedure.working_rules


def test_step_two_asks_whether_regions_should_exist():
    step = load_library().procedure.steps[2]
    assert "should exist at all" in step.text
    assert step.paragraph("Keep:").startswith("Keep:")


def test_every_situation_has_an_sop_with_a_verify_step():
    lib = load_library()
    assert set(lib.situations) == set(SITUATIONS)
    for sop in lib.situations.values():
        assert sop.brief and sop.may_change and sop.must_preserve and sop.completion
        assert [s.number for s in sop.steps] == list(range(1, len(sop.steps) + 1))
        assert any(s.kind == "verify" for s in sop.steps)
        assert sop.steps[0].resolve(None) == [0]


def test_every_scope_sheet_covers_every_label():
    lib = load_library()
    assert set(lib.scopes) == set(SCOPES)
    for sheet in lib.scopes.values():
        assert set(sheet.at_scope) == set(SCOPE_LABELS)
        assert sheet.fields["Boundary"] and sheet.fields["Parent"] and sheet.expansion
    assert [label for label, _ in lib.scopes["page"].lines_for([5])] == ["Foundations"]


def test_fix_resolves_the_responsible_step():
    fix = load_library().situations["fix"]
    correct, carry = fix.steps[3], fix.steps[4]
    assert correct.resolve(3) == [3]
    assert carry.resolve(7) == [8, 9]
    assert carry.modifier == "keep"
    assert fix.steps[2].kind == "trace"
