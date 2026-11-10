import unittest
from unittest.mock import patch

from hexagons_update import _check_illegit_defects


class _FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = []

    def delete(self):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, values))
        return self

    def execute(self):
        self.client.deletes.append((self.table_name, self.filters))


class _FakeSupabase:
    def __init__(self):
        self.deletes = []

    def table(self, table_name):
        return _FakeQuery(self, table_name)


class IllegitCleanupTests(unittest.TestCase):
    @patch("hexagons_update.ledger_illegit_penalty")
    def test_deletes_linked_imu_events_when_defect_is_deleted(self, _penalty):
        supabase = _FakeSupabase()
        defects = {
            "defect": {
                "id": 17,
                "rd_trip_ids": ["discovering-session"],
                "event_id": [101, 102],
                "confirmed": False,
                "confidence": 0,
                "discovery_reward": 1.0,
                "discovery_n": 1,
            }
        }

        _check_illegit_defects(
            supabase,
            defects,
            ["discovering-session"],
            ["discoverer"],
            "h3-index",
            0,
            {},
            1.0,
        )

        self.assertIn(
            ("hexagons", [("eq", "id", 17)]),
            supabase.deletes,
        )
        self.assertIn(
            ("imu_events", [("in", "imu_events_id", [101, 102])]),
            supabase.deletes,
        )


if __name__ == "__main__":
    unittest.main()
