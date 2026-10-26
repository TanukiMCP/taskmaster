from taskmaster.library import SCOPES, SITUATIONS, VERIFY_STEP, load_library


def test_procedure_has_all_steps_in_order():
    lib = load_library()
    assert sorted(lib.procedure.steps) == list(range(0, VERIFY_STEP + 1))
    assert lib.procedure.steps[3].name == "Name the jobs and adapt components from real products"
    assert "The chain" in lib.procedure.preamble
    assert lib.procedure.steps[10].text.startswith("10. Verify and correct")
    assert "Remaining limits" in lib.procedure.limits


def test_every_situation_and_scope_loads():
    lib = load_library()
    assert set(lib.situations) == set(SITUATIONS)
    assert set(lib.scopes) == set(SCOPES)
    for scope in lib.scopes.values():
        assert sorted(scope.limits) == list(range(0, VERIFY_STEP + 1))
        assert scope.expansion


def test_linear_situations_have_a_rule_for_every_step():
    lib = load_library()
    for key in ("create", "extend", "review"):
        assert sorted(lib.situations[key].rules) == list(range(0, VERIFY_STEP + 1)), key


def test_diagnosing_situations_rule_by_responsible_step():
    lib = load_library()
    improve, fix = lib.situations["improve"], lib.situations["fix"]
    assert improve.diagnosis and fix.diagnosis
    assert improve.rule_for(5, k=3) == improve.rule_for(3, k=3)
    assert fix.rule_for(5, k=3).startswith("Decide only where")
    assert fix.rule_for(3, k=3).startswith("Decide. Correct the cause")
    assert fix.rule_for(10, k=3).startswith("Decide. Confirm")
