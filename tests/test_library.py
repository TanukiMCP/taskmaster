from taskmaster.library import SCOPE_LABELS, SCOPES, SITUATIONS, VERIFY_STEP, load_library


def test_method_is_the_working_method():
    method = load_library().method
    assert method.startswith("Dependency-ordered cognitive composition")
    assert "5. Preserve the original source of value" in method
    assert "9. Run it in Taskmaster" in method


def test_procedure_has_all_steps_in_order():
    lib = load_library()
    assert sorted(lib.procedure.steps) == list(range(0, VERIFY_STEP + 1))
    assert lib.procedure.steps[3].name == "Name the jobs and adapt components from real products"
    assert "The chain" in lib.procedure.sections
    assert lib.procedure.steps[10].text.startswith("10. Verify and correct")
    assert "Remaining limits" in lib.procedure.limits
    assert "Keeping is a stated decision" in lib.procedure.working_rules
    assert "Before each operation" in lib.procedure.working_rules


def test_every_situation_is_a_composition():
    lib = load_library()
    assert set(lib.situations) == set(SITUATIONS)
    for sop in lib.situations.values():
        assert sop.brief and sop.may_change and sop.must_preserve and sop.completion
        assert [s.number for s in sop.steps] == list(range(1, len(sop.steps) + 1))
        assert all(s.produces and s.instruction for s in sop.steps)
        assert not sop.steps[0].needs and sop.steps[0].steps == [0]
        earlier: set[str] = set()
        for step in sop.steps:
            assert set(step.needs) <= earlier
            earlier.add(step.id)


def test_a_step_working_in_one_procedure_step_produces_what_that_step_produces():
    lib = load_library()
    typography = lib.situations["create"].step("typography")
    assert typography.produces == lib.procedure.steps[5].paragraph("Produces:").removeprefix("Produces:").strip()
    assert lib.situations["redesign"].step("evidence").produces.startswith("Before captures")


def test_review_records_and_sets_its_standard_independently():
    review = load_library().situations["review"]
    assert review.step("standard").needs == ("question",)
    assert review.step("record").needs == ("question",)
    assert review.step("walk").needs == ("standard", "record")


def test_every_scope_sheet_covers_every_label():
    lib = load_library()
    assert set(lib.scopes) == set(SCOPES)
    for sheet in lib.scopes.values():
        assert set(sheet.at_scope) == set(SCOPE_LABELS)
        assert sheet.fields["Boundary"] and sheet.fields["Parent"] and sheet.expansion
    assert [label for label, _ in lib.scopes["page"].lines_for([5])] == ["Foundations"]


def test_references_resolve_or_name_nothing():
    lib = load_library()
    assert "design/<situation>/<scope>" in lib.read("")
    assert lib.read("method") == lib.method
    assert "Prompt selector" in lib.read("design")
    assert lib.read("design/process/8").startswith("8. Construct layout")
    for ref in ("design/process/11", "design/nope/page", "design/fix/nope", "design/fix/page#nope", "elsewhere"):
        assert lib.read(ref) is None


def test_an_entry_reads_as_its_sop_scope_and_ready_composition():
    entry = load_library().read("design/redesign/section")
    assert "## Situation SOP: Redesign" in entry and "## Scope: Section" in entry
    assert '{"id":"evidence","needs":["question"],"does":""' in entry
    assert '"guide":"design/redesign/section#verify"' in entry


def test_a_guide_carries_the_sop_step_scope_and_procedure():
    lib = load_library()
    order = lib.read("design/create/page#order")
    assert "Create × Page or view, SOP step 3 of 11" in order
    assert "### Procedure step 2: Order the information (verbatim)" in order and "should exist at all" in order
    assert "Content and order:" in order and "### Working rules" in order
    assert "### Completion" not in order
    assert "### Completion" in lib.read("design/create/page#verify")

    foundations = lib.read("design/extend/component#foundations")
    assert foundations.count("Keep rule (library('design/process/") == 4

    assert "### Design working method" in lib.read("design/create/page#question")
    assert "permission to select from memory" in lib.read("design/create/page#question")
    assert "### Design working method" not in order

    correct = lib.read("design/fix/element#correct")
    assert "Works in procedure step: the step the trace named" in correct
    assert "### Procedure step" not in correct
