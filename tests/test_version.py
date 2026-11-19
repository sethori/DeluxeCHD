import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packaging"))

import version  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_rollover(self):
        self.assertEqual(version.bump((1, 0, 1)), (1, 0, 2))
        self.assertEqual(version.bump((1, 0, 9)), (1, 1, 0))
        self.assertEqual(version.bump((1, 9, 9)), (2, 0, 0))

    def test_next_from_tags(self):
        self.assertEqual(version.next_version([]), (1, 0, 1))
        self.assertEqual(version.next_version(["v1.0"]), (1, 0, 1))
        self.assertEqual(version.next_version(["v1.0", "v1.0.1", "v1.0.9", "junk"]), (1, 1, 0))


if __name__ == "__main__":
    unittest.main()
