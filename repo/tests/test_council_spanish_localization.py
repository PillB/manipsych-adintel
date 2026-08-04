from tools.run_council_annotation_pass import annotate_text


def labels_and_texts(text: str) -> list[tuple[str, str]]:
    spans, _ = annotate_text(text, {}, "subagent_r4_a", 4, deliberated_second_pass=True)
    return [(span["label"], span["exact_text"]) for span in spans]


def test_gender_mismatch_financial_support_is_annotated_with_original_offsets():
    items = labels_and_texts("Brindó apoyo económica a señorita por compañía")

    assert ("reciprocity_obligation", "Brindó apoyo económica") in items
    assert ("conditional_financial_support", "por compañía") in items


def test_common_economic_typo_is_annotated_as_same_expression():
    items = labels_and_texts("brindo apoyo economomico discreto")

    assert ("reciprocity_obligation", "brindo apoyo economomico") in items
    assert ("privacy_or_secrecy_pressure", "discreto") in items
