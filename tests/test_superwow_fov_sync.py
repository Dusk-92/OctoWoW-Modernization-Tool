import os
import stat
import tempfile
import unittest

import setup_tool_dynamic as dynamic


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class SuperWowFovSyncTests(unittest.TestCase):
    def _tool(self, *, superwow=True, fov=1.9199, farclip=777, script_memory=False):
        tool = object.__new__(dynamic.ModernWowSetupTool)
        tool.core_plugins = {
            "SuperWoWhook.dll": FakeVar(superwow),
        }
        tool.vt_fov = FakeVar(fov)
        tool.vt_farclip = FakeVar(farclip)
        tool.vt_script_memory = FakeVar(script_memory)
        return tool

    @staticmethod
    def _config_path(root):
        return os.path.join(root, "WTF", "Config.wtf")

    def test_superwow_enabled_updates_existing_fov(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._config_path(root)
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    'SET gxWindow "1"\n'
                    'SET FoV "1.5"\n'
                    'SET locale "enUS"\n'
                )

            self._tool().configure_script_memory(root)

            with open(path, "r", encoding="utf-8") as handle:
                result = handle.read()
            self.assertIn('SET FoV "1.9199"', result)
            self.assertIn('SET farclip "777"', result)
            self.assertIn('SET gxWindow "1"', result)
            self.assertIn('SET locale "enUS"', result)
            self.assertNotIn('SET FoV "1.5"', result)

    def test_superwow_enabled_creates_missing_fov_setting(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._config_path(root)

            self._tool(fov=2.1).configure_script_memory(root)

            with open(path, "r", encoding="utf-8") as handle:
                result = handle.read()
            self.assertEqual(
                result,
                'SET FoV "2.1"\nSET farclip "777"\n',
            )

    def test_superwow_disabled_leaves_existing_fov_untouched(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._config_path(root)
            os.makedirs(os.path.dirname(path))
            original = 'SET FoV "1.5"\nSET locale "frFR"\n'
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(original)

            self._tool(superwow=False).configure_script_memory(root)

            with open(path, "r", encoding="utf-8") as handle:
                result = handle.read()
            self.assertIn('SET FoV "1.5"', result)
            self.assertIn('SET locale "frFR"', result)
            self.assertIn('SET farclip "777"', result)
            self.assertNotIn('SET FoV "1.9199"', result)

    def test_script_memory_and_superwow_fov_are_both_applied(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._config_path(root)
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('SET locale "enUS"\n')

            self._tool(script_memory=True).configure_script_memory(root)

            with open(path, "r", encoding="utf-8") as handle:
                result = handle.read()
            self.assertIn('SET scriptMemory "0"', result)
            self.assertIn('SET FoV "1.9199"', result)
            self.assertIn('SET farclip "777"', result)

    def test_readonly_config_mode_is_restored(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._config_path(root)
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('SET FoV "1.5"\n')
            os.chmod(path, stat.S_IREAD)

            self._tool().configure_script_memory(root)

            mode = os.stat(path).st_mode
            self.assertFalse(mode & stat.S_IWRITE)
            with open(path, "r", encoding="utf-8") as handle:
                result = handle.read()
            self.assertIn('SET FoV "1.9199"', result)
            self.assertIn('SET farclip "777"', result)


if __name__ == "__main__":
    unittest.main()
