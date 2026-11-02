from coherence.library import ASPECTS, load_library


def test_the_library_holds_the_procedure_the_method_and_design_guidance():
    lib = load_library()
    assert lib.procedure.startswith("CoherenceMCP procedure")
    assert "The seven questions, in this order" in lib.procedure
    assert "9. Run it in CoherenceMCP" in lib.method and "Taskmaster" not in lib.method
    assert sorted(lib.design_steps) == list(range(11))
    assert lib.guidance("typography").startswith("5. Select and set typography")
    assert lib.guidance("none") == ""
    assert "Taskmaster" not in lib.design


def test_references_resolve_or_name_nothing():
    lib = load_library()
    assert "design/<aspect>" in lib.read("")
    assert lib.read("design/order").startswith("2. Order the information")
    assert lib.read("procedure") == lib.procedure
    assert lib.read("design/nope") is None and lib.read("elsewhere") is None
    assert set(ASPECTS) >= {"components", "layout", "verify"}
