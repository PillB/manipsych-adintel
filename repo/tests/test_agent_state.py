import unittest
from pathlib import Path

from tools.validate_agent_state import parse_items, validate_state


ROOT = Path(__file__).resolve().parents[1]


class AgentStateTests(unittest.TestCase):
    def test_agent_state_has_valid_checklist_conditions(self):
        self.assertEqual(validate_state(ROOT / "AGENT_STATE.md"), [])

    def test_every_checkbox_has_exactly_three_conditions(self):
        text = (ROOT / "AGENT_STATE.md").read_text(encoding="utf-8")
        items = parse_items(text)
        self.assertGreaterEqual(len(items), 8)
        self.assertTrue(all(len(item.conditions) == 3 for item in items))


if __name__ == "__main__":
    unittest.main()
