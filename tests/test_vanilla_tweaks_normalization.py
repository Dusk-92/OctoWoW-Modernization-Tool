import os
import struct
import tempfile
import unittest
from unittest import mock

import setup_tool_dynamic
from setup_tool import WowSetupTool
from setup_tool_dynamic import ModernWowSetupTool


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class VanillaTweaksNormalizationTests(unittest.TestCase):
    def _tool(
        self,
        *,
        fov,
        sound,
        quickloot,
        background,
        farclip=777,
        frill=300,
        nameplate=41,
        maxcam=100,
        laa=True,
        camera=True,
        custom_glues=True,
        crossfaction=False,
        bluemoon=False,
    ):
        tool = ModernWowSetupTool.__new__(ModernWowSetupTool)
        tool.vt_fov = FakeVar(fov)
        tool.vt_soundchan = FakeVar(sound)
        tool.vt_quickloot = FakeVar(quickloot)
        tool.vt_bg_sound = FakeVar(background)
        tool.vt_farclip = FakeVar(farclip)
        tool.vt_frill = FakeVar(frill)
        tool.vt_nameplate = FakeVar(nameplate)
        tool.vt_maxcam = FakeVar(maxcam)
        tool.vt_laa = FakeVar(laa)
        tool.vt_cam_fix = FakeVar(camera)
        tool.vt_crossfaction_res = FakeVar(crossfaction)
        tool.vt_custom_glues = FakeVar(custom_glues)
        tool.vt_bluemoon = FakeVar(bluemoon)
        tool.core_plugins = {"SuperWoWhook.dll": FakeVar(True)}
        return tool

    def _write_exe(
        self,
        root,
        quick1,
        quick2,
        background,
        fov,
        sound,
        *,
        farclip=777.0,
        frill=70.0,
        nameplate=20.0,
        maxcam=50.0,
        laa_patched=False,
        camera_patched=False,
        custom_patched=False,
        crossfaction_byte=0x01,
        bluemoon_bytes=None,
        filename="WoW_Modernized.exe",
    ):
        data = bytearray(0x46795C + 16)

        # Use a minimal but structurally valid PE32 header. The selected PE
        # offset deliberately places COFF Characteristics at 0x126, matching
        # the real client's Large Address Aware patch location.
        pe_offset = 0x110
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, pe_offset)
        data[pe_offset:pe_offset + 4] = b"PE\x00\x00"
        struct.pack_into("<H", data, pe_offset + 4, 0x014C)
        struct.pack_into("<H", data, pe_offset + 6, 3)
        struct.pack_into("<H", data, pe_offset + 20, 0x00E0)
        struct.pack_into("<H", data, pe_offset + 24, 0x010B)

        data[
            setup_tool_dynamic._CLIENT_BUILD_OFFSET:
            setup_tool_dynamic._CLIENT_BUILD_OFFSET
            + len(setup_tool_dynamic._CLIENT_BUILD)
        ] = setup_tool_dynamic._CLIENT_BUILD
        data[
            setup_tool_dynamic._CLIENT_VERSION_OFFSET:
            setup_tool_dynamic._CLIENT_VERSION_OFFSET
            + len(setup_tool_dynamic._CLIENT_VERSION)
        ] = setup_tool_dynamic._CLIENT_VERSION

        data[0x0C1ECF:0x0C1ED1] = quick1
        data[0x0C2B25:0x0C2B27] = quick2
        data[0x3A4869] = background
        data[0x126:0x128] = b"\x2F\x01" if laa_patched else b"\x0F\x01"

        for offset, original, patched in setup_tool_dynamic._CAMERA_REGIONS:
            selected = patched if camera_patched else original
            data[offset:offset + len(selected)] = selected

        for offset, original, patched in setup_tool_dynamic._CUSTOM_GLUES_SITES:
            data[offset] = patched if custom_patched else original

        struct.pack_into("<f", data, 0x4089B4, fov)
        struct.pack_into("<f", data, 0x40FED8, farclip)
        struct.pack_into("<f", data, 0x467958, frill)
        struct.pack_into("<f", data, 0x40C448, nameplate)
        struct.pack_into("<f", data, 0x4089A4, maxcam)
        data[0x435D38:0x435D3C] = sound

        data[0x2067DE] = crossfaction_byte
        if bluemoon_bytes is None:
            bluemoon_bytes = bytes(range(1, 14))
        data[0x3E5B83:0x3E5B83 + len(bluemoon_bytes)] = bluemoon_bytes

        # Unrelated data must survive normalization byte-for-byte.
        data[0x123456:0x12345E] = b"KEEPTHIS"

        path = os.path.join(root, filename)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    @staticmethod
    def _read_float(data, offset):
        return struct.unpack("<f", data[offset:offset + 4])[0]

    @staticmethod
    def _write_custom_state(path, values):
        with open(path, "r+b") as handle:
            for value, (offset, _original, _patched) in zip(
                values,
                setup_tool_dynamic._CUSTOM_GLUES_SITES,
            ):
                handle.seek(offset)
                handle.write(bytes((value,)))

    @staticmethod
    def _read_custom_state(data):
        return tuple(
            data[offset]
            for offset, _original, _patched in setup_tool_dynamic._CUSTOM_GLUES_SITES
        )

    def test_disabled_selections_restore_inherited_patches(self):
        tool = self._tool(
            fov=1.5708,
            sound=12,
            quickloot=False,
            background=False,
            farclip=777,
            frill=70,
            nameplate=20,
            maxcam=50,
            laa=False,
            camera=False,
            custom_glues=False,
        )

        with tempfile.TemporaryDirectory() as root:
            path = self._write_exe(
                root,
                b"\x75\x10",
                b"\x75\x0B",
                0x27,
                1.919862,
                b"64\x00\x00",
                farclip=3000.0,
                frill=300.0,
                nameplate=41.0,
                maxcam=100.0,
                laa_patched=True,
                camera_patched=True,
                custom_patched=True,
            )
            tool._normalize_selected_vanilla_tweaks_output(path)
            with open(path, "rb") as handle:
                result = handle.read()

        self.assertEqual(result[0x0C1ECF:0x0C1ED1], b"\x74\x10")
        self.assertEqual(result[0x0C2B25:0x0C2B27], b"\x74\x0B")
        self.assertEqual(result[0x3A4869], 0x14)
        self.assertEqual(result[0x126:0x128], b"\x0F\x01")
        self.assertAlmostEqual(self._read_float(result, 0x4089B4), 1.5708, places=4)
        self.assertEqual(self._read_float(result, 0x40FED8), 3000.0)
        self.assertEqual(self._read_float(result, 0x467958), 70.0)
        self.assertEqual(self._read_float(result, 0x40C448), 20.0)
        self.assertEqual(self._read_float(result, 0x4089A4), 50.0)
        self.assertEqual(result[0x435D38:0x435D3C], b"12\x00\x00")
        for offset, original, _patched in setup_tool_dynamic._CAMERA_REGIONS:
            self.assertEqual(result[offset:offset + len(original)], original)
        for offset, original, _patched in setup_tool_dynamic._CUSTOM_GLUES_SITES:
            self.assertEqual(result[offset], original)
        self.assertEqual(result[0x123456:0x12345E], b"KEEPTHIS")

    def test_enabled_selections_override_vanilla_input(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
            farclip=1500,
            frill=300,
            nameplate=41,
            maxcam=100,
            laa=True,
            camera=True,
            custom_glues=True,
        )

        with tempfile.TemporaryDirectory() as root:
            path = self._write_exe(
                root,
                b"\x90\x90",
                b"\x90\x90",
                0x14,
                1.5707963705,
                b"12\x00\x00",
            )
            tool._normalize_selected_vanilla_tweaks_output(path)
            with open(path, "rb") as handle:
                result = handle.read()

        self.assertEqual(result[0x0C1ECF:0x0C1ED1], b"\x75\x10")
        self.assertEqual(result[0x0C2B25:0x0C2B27], b"\x75\x0B")
        self.assertEqual(result[0x3A4869], 0x27)
        self.assertEqual(result[0x126:0x128], b"\x2F\x01")
        self.assertAlmostEqual(self._read_float(result, 0x4089B4), 1.9199, places=4)
        self.assertEqual(self._read_float(result, 0x40FED8), 3000.0)
        self.assertEqual(self._read_float(result, 0x467958), 300.0)
        self.assertEqual(self._read_float(result, 0x40C448), 41.0)
        self.assertEqual(self._read_float(result, 0x4089A4), 100.0)
        self.assertEqual(result[0x435D38:0x435D3C], b"64\x00\x00")
        for offset, _original, patched in setup_tool_dynamic._CAMERA_REGIONS:
            self.assertEqual(result[offset:offset + len(patched)], patched)
        for offset, _original, patched in setup_tool_dynamic._CUSTOM_GLUES_SITES:
            self.assertEqual(result[offset], patched)
        self.assertEqual(result[0x123456:0x12345E], b"KEEPTHIS")

    def test_unknown_quickloot_bytes_fail_safe(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
        )

        with tempfile.TemporaryDirectory() as root:
            path = self._write_exe(
                root,
                b"\xEB\x10",
                b"\x74\x0B",
                0x14,
                1.5708,
                b"12\x00\x00",
            )
            with self.assertRaisesRegex(RuntimeError, "Unexpected QuickLoot bytes"):
                tool._normalize_selected_vanilla_tweaks_output(path)

    def test_unknown_custom_glues_bytes_fail_safe_without_source_proof(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
            custom_glues=False,
        )

        with tempfile.TemporaryDirectory() as root:
            path = self._write_exe(
                root,
                b"\x74\x10",
                b"\x74\x0B",
                0x14,
                1.5708,
                b"12\x00\x00",
            )
            with open(path, "r+b") as handle:
                handle.seek(0x2F113A)
                handle.write(b"\xAA")

            with self.assertRaisesRegex(RuntimeError, "Unexpected Custom GlueXML bytes"):
                tool._normalize_selected_vanilla_tweaks_output(path)

    def test_source_preflight_accepts_and_records_foreign_custom_glues(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
            custom_glues=True,
        )
        foreign = (0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xF1)

        with tempfile.TemporaryDirectory() as root:
            source = self._write_exe(
                root,
                b"\x75\x10",
                b"\x75\x0B",
                0x27,
                1.919862,
                b"12\x00\x00",
                farclip=3000.0,
                frill=300.0,
                nameplate=41.0,
                maxcam=50.0,
                laa_patched=True,
                camera_patched=True,
                filename="WoW.exe",
            )
            self._write_custom_state(source, foreign)

            preserved = tool._preflight_vanilla_tweaks_source(root)

        self.assertEqual(preserved, foreign)
        self.assertEqual(tool._vt_preserved_custom_glues, foreign)

    def test_blue_moon_and_crossfaction_keep_legacy_output(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
            crossfaction=True,
            bluemoon=True,
        )
        blue_bytes = bytes.fromhex("a1 a2 a3 a4 a5 a6 a7 a8 a9 aa ab ac ad")

        with tempfile.TemporaryDirectory() as root:
            path = self._write_exe(
                root,
                b"\x74\x10",
                b"\x74\x0B",
                0x14,
                1.5708,
                b"12\x00\x00",
                crossfaction_byte=0x7A,
                bluemoon_bytes=blue_bytes,
            )
            tool._normalize_selected_vanilla_tweaks_output(path)
            with open(path, "rb") as handle:
                result = handle.read()

        self.assertEqual(result[0x2067DE], 0x7A)
        self.assertEqual(
            result[0x3E5B83:0x3E5B83 + len(blue_bytes)],
            blue_bytes,
        )

    def test_source_preflight_rejects_unknown_quickloot_before_patcher(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
        )

        with tempfile.TemporaryDirectory() as root:
            self._write_exe(
                root,
                b"\xEB\x10",
                b"\x74\x0B",
                0x14,
                1.5708,
                b"12\x00\x00",
                filename="WoW.exe",
            )
            output_exe = os.path.join(root, "WoW_Modernized.exe")
            previous_output = b"known-good existing modernized executable"
            with open(output_exe, "wb") as handle:
                handle.write(previous_output)

            patcher = mock.Mock()
            with mock.patch.object(WowSetupTool, "run_vanilla_tweaks", new=patcher):
                with self.assertRaisesRegex(RuntimeError, "Unexpected QuickLoot bytes"):
                    tool._run_vanilla_tweaks_transactional(
                        root,
                        tweaks_exe="fake-vanilla-tweaks.exe",
                        modern_cli=True,
                    )

            patcher.assert_not_called()
            with open(output_exe, "rb") as handle:
                self.assertEqual(handle.read(), previous_output)
            self.assertFalse(os.path.exists(output_exe + ".modernization-new"))
            self.assertFalse(
                any(name.startswith(".modernization-vt-") for name in os.listdir(root))
            )

    def test_transaction_keeps_existing_output_when_normalization_fails(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
        )

        with tempfile.TemporaryDirectory() as root:
            self._write_exe(
                root,
                b"\x74\x10",
                b"\x74\x0B",
                0x14,
                1.5708,
                b"12\x00\x00",
                filename="WoW.exe",
            )

            output_exe = os.path.join(root, "WoW_Modernized.exe")
            previous_output = b"known-good existing modernized executable"
            with open(output_exe, "wb") as handle:
                handle.write(previous_output)

            def fake_run(_tool, staging_target, tweaks_exe=None, modern_cli=False):
                return self._write_exe(
                    staging_target,
                    b"\xEB\x10",
                    b"\x74\x0B",
                    0x14,
                    1.5708,
                    b"12\x00\x00",
                )

            with mock.patch.object(WowSetupTool, "run_vanilla_tweaks", new=fake_run):
                with self.assertRaisesRegex(RuntimeError, "Unexpected QuickLoot bytes"):
                    tool._run_vanilla_tweaks_transactional(
                        root,
                        tweaks_exe="fake-vanilla-tweaks.exe",
                        modern_cli=True,
                    )

            with open(output_exe, "rb") as handle:
                self.assertEqual(handle.read(), previous_output)
            self.assertFalse(os.path.exists(output_exe + ".modernization-new"))
            self.assertFalse(
                any(name.startswith(".modernization-vt-") for name in os.listdir(root))
            )

    def test_transaction_restores_foreign_custom_glues_after_patcher(self):
        tool = self._tool(
            fov=1.5708,
            sound=12,
            quickloot=False,
            background=False,
            farclip=777,
            frill=70,
            nameplate=20,
            maxcam=50,
            laa=False,
            camera=False,
            custom_glues=True,
        )
        foreign = (0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xF1)

        with tempfile.TemporaryDirectory() as root:
            source = self._write_exe(
                root,
                b"\x75\x10",
                b"\x75\x0B",
                0x27,
                1.919862,
                b"64\x00\x00",
                farclip=3000.0,
                frill=300.0,
                nameplate=41.0,
                maxcam=100.0,
                laa_patched=True,
                camera_patched=True,
                filename="WoW.exe",
            )
            self._write_custom_state(source, foreign)

            output_exe = os.path.join(root, "WoW_Modernized.exe")
            with open(output_exe, "wb") as handle:
                handle.write(b"previous output")

            def fake_run(_tool, staging_target, tweaks_exe=None, modern_cli=False):
                return self._write_exe(
                    staging_target,
                    b"\x75\x10",
                    b"\x75\x0B",
                    0x27,
                    1.919862,
                    b"64\x00\x00",
                    farclip=3000.0,
                    frill=300.0,
                    nameplate=41.0,
                    maxcam=100.0,
                    laa_patched=True,
                    camera_patched=True,
                    custom_patched=True,
                )

            with mock.patch.object(WowSetupTool, "run_vanilla_tweaks", new=fake_run):
                tool._run_vanilla_tweaks_transactional(
                    root,
                    tweaks_exe="fake-vanilla-tweaks.exe",
                    modern_cli=True,
                )

            with open(output_exe, "rb") as handle:
                result = handle.read()

        self.assertEqual(self._read_custom_state(result), foreign)
        self.assertEqual(result[0x0C1ECF:0x0C1ED1], b"\x74\x10")
        self.assertEqual(result[0x0C2B25:0x0C2B27], b"\x74\x0B")
        self.assertEqual(result[0x3A4869], 0x14)
        self.assertEqual(result[0x126:0x128], b"\x0F\x01")

    def test_transaction_commits_total_normalized_output_after_validation(self):
        tool = self._tool(
            fov=1.5708,
            sound=12,
            quickloot=False,
            background=False,
            farclip=777,
            frill=70,
            nameplate=20,
            maxcam=50,
            laa=False,
            camera=False,
            custom_glues=False,
        )

        with tempfile.TemporaryDirectory() as root:
            self._write_exe(
                root,
                b"\x74\x10",
                b"\x74\x0B",
                0x14,
                1.5708,
                b"12\x00\x00",
                filename="WoW.exe",
            )

            output_exe = os.path.join(root, "WoW_Modernized.exe")
            with open(output_exe, "wb") as handle:
                handle.write(b"previous output")

            def fake_run(_tool, staging_target, tweaks_exe=None, modern_cli=False):
                return self._write_exe(
                    staging_target,
                    b"\x75\x10",
                    b"\x75\x0B",
                    0x27,
                    1.5708,
                    b"12\x00\x00",
                    farclip=777.0,
                    frill=70.0,
                    nameplate=20.0,
                    maxcam=50.0,
                    laa_patched=True,
                    camera_patched=True,
                    custom_patched=True,
                )

            with mock.patch.object(WowSetupTool, "run_vanilla_tweaks", new=fake_run):
                result_path = tool._run_vanilla_tweaks_transactional(
                    root,
                    tweaks_exe="fake-vanilla-tweaks.exe",
                    modern_cli=True,
                )

            self.assertEqual(result_path, output_exe)
            with open(output_exe, "rb") as handle:
                result = handle.read()

            self.assertEqual(result[0x0C1ECF:0x0C1ED1], b"\x74\x10")
            self.assertEqual(result[0x0C2B25:0x0C2B27], b"\x74\x0B")
            self.assertEqual(result[0x3A4869], 0x14)
            self.assertEqual(result[0x126:0x128], b"\x0F\x01")
            self.assertAlmostEqual(self._read_float(result, 0x4089B4), 1.5708, places=4)
            self.assertEqual(self._read_float(result, 0x40FED8), 3000.0)
            self.assertEqual(self._read_float(result, 0x467958), 70.0)
            self.assertEqual(self._read_float(result, 0x40C448), 20.0)
            self.assertEqual(self._read_float(result, 0x4089A4), 50.0)
            self.assertEqual(result[0x435D38:0x435D3C], b"12\x00\x00")
            for offset, original, _patched in setup_tool_dynamic._CAMERA_REGIONS:
                self.assertEqual(result[offset:offset + len(original)], original)
            for offset, original, _patched in setup_tool_dynamic._CUSTOM_GLUES_SITES:
                self.assertEqual(result[offset], original)
            self.assertFalse(os.path.exists(output_exe + ".modernization-new"))
            self.assertFalse(
                any(name.startswith(".modernization-vt-") for name in os.listdir(root))
            )

    def test_validation_gate_runs_source_preflight(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
        )
        tool.wow_dir = FakeVar("C:/game")
        tool.optional_plugins = {"no1600x1200.dll": FakeVar(False)}
        tool.vmmfix_enabled = FakeVar(False)

        with mock.patch.object(
            tool,
            "_preflight_vanilla_tweaks_source",
            return_value=None,
        ) as preflight:
            self.assertTrue(tool.validate_plugin_conflicts())

        preflight.assert_called_once_with("C:/game")

    def test_normalization_policy_forces_one_marker_refresh(self):
        tool = self._tool(
            fov=1.9199,
            sound=64,
            quickloot=True,
            background=True,
        )

        old_signature = WowSetupTool._vanilla_tweaks_signature(tool)
        new_signature = tool._vanilla_tweaks_signature()

        self.assertNotIn("selected_patch_normalization", old_signature)
        self.assertEqual(new_signature["selected_patch_normalization"], 4)

        tool.core_plugins["SuperWoWhook.dll"].set(False)
        self.assertEqual(new_signature, tool._vanilla_tweaks_signature())


if __name__ == "__main__":
    unittest.main()
