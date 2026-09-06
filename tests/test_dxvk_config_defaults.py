import os
import unittest


class DxvkConfigDefaultsTests(unittest.TestCase):
    def test_exclusive_fullscreen_is_disabled_by_default(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(repo_root, "Payload", "dxvk.conf")

        with open(config_path, "r", encoding="utf-8") as handle:
            active_settings = [
                line.strip()
                for line in handle
                if line.strip() and not line.lstrip().startswith("#")
            ]

        allow_fse_settings = [
            line for line in active_settings if line.lower().startswith("dxvk.allowfse")
        ]
        self.assertEqual(allow_fse_settings, ["dxvk.allowFse = False"])


if __name__ == "__main__":
    unittest.main()
