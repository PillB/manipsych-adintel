"""Tests for the hierarchical taxonomy (adintel-taxonomy-v2).

These tests were written first (Red phase) and encode the spec's requirements
explicitly: hierarchy, multi-label mapping, leaf vs family, v1 -> v2 mapping
completeness, and hard-negative behaviour.
"""

from __future__ import annotations

import unittest

from adintel import taxonomy as tx


class TaxonomyStructureTests(unittest.TestCase):
    def test_top_level_families_present(self):
        """The spec requires at minimum: copywriting, rhetoric, behavioural,
        sales/objection-handling. We also add visual and multimodal."""
        families = {n.id for n in tx.family_roots()}
        for required in (
            "copywriting_composition",
            "persuasive_rhetoric",
            "behavioural_science",
            "sales_objection_handling",
            "visual_persuasion",
            "multimodal_combination",
        ):
            self.assertIn(required, families, f"Missing required family: {required}")

    def test_every_non_root_has_a_parent_that_exists(self):
        for node in tx.all_nodes():
            if node.parent is not None:
                self.assertIn(node.parent, {n.id for n in tx.all_nodes()})

    def test_every_leaf_has_a_family_ancestor(self):
        for leaf in tx.leaf_nodes():
            anc = tx.ancestors(leaf.id)
            self.assertTrue(len(anc) > 0, f"Leaf {leaf.id} has no ancestors")
            self.assertEqual(tx.family_of(leaf.id), anc[-1])

    def test_leaf_count_is_reasonable(self):
        # The spec calls for a "hierarchical multi-label taxonomy". We expect
        # somewhere in the range 20-40 leaves: big enough to be useful, small
        # enough to annotate reliably.
        leaves = tx.leaf_nodes()
        self.assertGreaterEqual(len(leaves), 15)
        self.assertLessEqual(len(leaves), 50)

    def test_node_ids_are_unique(self):
        ids = [n.id for n in tx.all_nodes()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_family_roots_are_level_zero(self):
        for root in tx.family_roots():
            self.assertEqual(root.level, 0)


class V1ToV2MappingTests(unittest.TestCase):
    """The existing 20-label pilot schema must round-trip into v2."""

    V1_LABELS = [
        "reciprocity_obligation",
        "conditional_financial_support",
        "transactional_ambiguity",
        "platform_migration",
        "privacy_or_secrecy_pressure",
        "scarcity_or_urgency",
        "commitment_escalation",
        "foot_in_the_door",
        "authority_or_status_appeal",
        "social_proof",
        "exclusivity_or_special_treatment",
        "guilt_or_shame_pressure",
        "fear_or_threat",
        "deceptive_assurance",
        "sexualized_appearance_condition",
        "age_or_youth_targeting",
        "education_or_student_targeting",
        "economic_vulnerability_targeting",
        "family_obligation_targeting",
        "repetition_or_campaign_escalation",
    ]

    def test_every_v1_label_maps_to_at_least_one_v2_leaf(self):
        unmapped = tx.unmapped_v1_labels(self.V1_LABELS)
        self.assertEqual(unmapped, [], f"Unmapped v1 labels: {unmapped}")

    def test_v1_reciprocity_obligation_splits_into_copy_and_behavioural(self):
        """v1 overloaded `reciprocity_obligation`. v2 must split it into a
        copywriting frame and a behavioural lever."""
        v2 = tx.v1_to_v2("reciprocity_obligation")
        self.assertIn("cc_reciprocity_frame", v2)
        self.assertIn("bs_reciprocity_obligation", v2)
        # And both should be leaves
        for leaf in v2:
            self.assertTrue(tx.is_leaf(leaf), f"{leaf} should be a leaf")

    def test_v1_targeting_labels_map_into_audience_targeting_subtree(self):
        """v1 conflated targeting with technique; v2 reframes targeting as a
        behavioural-context subtree (bs_audience_targeting.*)."""
        for v1 in (
            "age_or_youth_targeting",
            "education_or_student_targeting",
            "economic_vulnerability_targeting",
            "family_obligation_targeting",
            "sexualized_appearance_condition",
        ):
            for v2 in tx.v1_to_v2(v1):
                self.assertTrue(
                    v2.startswith("bs_audience_targeting."),
                    f"{v1} -> {v2} should be under bs_audience_targeting",
                )


class MultiLabelBehaviourTests(unittest.TestCase):
    def test_a_text_can_be_assigned_multiple_labels_from_different_families(self):
        """Multi-label across families is the explicit requirement."""
        labels = ["cc_call_to_action", "pr_scarcity_urgency", "bs_audience_targeting.age_youth", "so_conditional_support"]
        families = {tx.family_of(l) for l in labels}
        self.assertEqual(len(families), 4)


class HardNegativeTests(unittest.TestCase):
    """A clean neutral sentence should not match any leaf by definition."""

    def test_neutral_definition_text_does_not_match_its_own_hard_negative(self):
        for leaf in tx.leaf_nodes():
            for neg in leaf.hard_negatives:
                # The hard negative should not be a substring of the definition
                self.assertNotIn(neg.lower(), leaf.definition.lower())


class SerialisationTests(unittest.TestCase):
    def test_to_dict_round_trips(self):
        d = tx.to_dict()
        self.assertEqual(d["taxonomy_version"], tx.TAXONOMY_VERSION)
        self.assertEqual(len(d["nodes"]), len(tx.all_nodes()))
        self.assertEqual(d["leaf_count"], len(tx.leaf_nodes()))
        self.assertGreater(len(d["v1_to_v2"]), 0)


if __name__ == "__main__":
    unittest.main()
