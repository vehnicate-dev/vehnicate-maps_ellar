import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import map_matching


class CombinedRoadGraphTests(unittest.TestCase):
    def test_builds_connected_graph_from_multiple_extracts(self):
        class FakeInMemMap:
            def __init__(self, *_args, **_kwargs):
                self.nodes = {}
                self.edges = set()

            def add_node(self, node_id, coordinates):
                self.nodes[node_id] = coordinates

            def add_edge(self, start, end):
                self.edges.add((start, end))

            def purge(self):
                pass

            def node_coordinates(self, node_id):
                return self.nodes[node_id]

        first_extract = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="1" lat="13.0000" lon="80.0000"/>
  <node id="2" lat="13.0010" lon="80.0010"/>
  <way id="10">
    <nd ref="1"/><nd ref="2"/>
    <tag k="highway" v="primary"/>
  </way>
</osm>
"""
        second_extract = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="2" lat="13.0010" lon="80.0010"/>
  <node id="3" lat="13.0020" lon="80.0020"/>
  <way id="11">
    <nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="primary"/>
  </way>
</osm>
"""
        old_edge_to_way = map_matching._EDGE_TO_WAY

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                first_path = Path(temp_dir) / "first.osm"
                second_path = Path(temp_dir) / "second.osm"
                first_path.write_text(first_extract, encoding="utf-8")
                second_path.write_text(second_extract, encoding="utf-8")

                with patch.object(map_matching, "InMemMap", FakeInMemMap):
                    graph = map_matching._build_map_from_pbf([
                        str(first_path),
                        str(second_path),
                    ])

                self.assertEqual(graph.node_coordinates(1), (13.0, 80.0))
                self.assertEqual(graph.node_coordinates(2), (13.001, 80.001))
                self.assertEqual(graph.node_coordinates(3), (13.002, 80.002))
                self.assertEqual(
                    graph.edges,
                    {(1, 2), (2, 1), (2, 3), (3, 2)},
                )
                self.assertEqual(
                    set(map_matching._EDGE_TO_WAY),
                    {(1, 2), (2, 1), (2, 3), (3, 2)},
                )
        finally:
            map_matching._EDGE_TO_WAY = old_edge_to_way


if __name__ == "__main__":
    unittest.main()
