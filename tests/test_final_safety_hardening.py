import math
import os
import struct
import tempfile
import unittest
from unittest import mock

import remote_packages
import setup_tool_dynamic as dynamic


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def _make_tool():
    tool = object.__new__(dynamic.ModernWowSetupTool)
    tool.vt_fov = _Var(1.9199)
    tool.vt_farclip = _Var(1500)
    tool.vt_frill = _Var(300)
    tool.vt_nameplate = _Var(41)
    tool.vt_maxcam = _Var(100)
    tool.vt_soundchan = _Var(64)
    tool.vt_quickloot = _Var(True)
    tool.vt_bg_sound = _Var(True)
    tool.vt_laa = _Var(True)
    tool.vt_cam_fix = _Var(True)
    tool.vt_custom_glues = _Var(True)
    return tool


def _base_client_data():
    data = bytearray(0x46795C)
    data[:2] = b"MZ"
    data[
        dynamic._CLIENT_BUILD_OFFSET:
        dynamic._CLIENT_BUILD_OFFSET + len(dynamic._CLIENT_BUILD)
    ] = dynamic._CLIENT_BUILD
    data[
        dynamic._CLIENT_VERSION_OFFSET:
        dynamic._CLIENT_VERSION_OFFSET + len(dynamic._CLIENT_VERSION)
    ] = dynamic._CLIENT_VERSION

    data[0x0C1ECF:0x0C1ED1] = b"\x74\x10"
    data[0x0C2B25:0x0C2B27] = b"\x74\x0B"
    data[0x3A4869] = 0x14
    data[0x126:0x128] = b"\x0F\x01"

    for offset, original, _patched in dynamic._CAMERA_REGIONS:
        data[offset:offset + len(original)] = original
    for offset, original, _patched in dynamic._CUSTOM_GLUES_SITES:
        data[offset] = original

    struct.pack_into("<f", data, 0x4089B4, math.pi / 2)
    struct.pack_into("<f", data, 0x40FED8, 777.0)
    struct.pack_into("<f", data, 0x467958, 70.0)
    struct.pack_into("<f", data, 0x40C448, 20.0)
    struct.pack_into("<f", data, 0x4089A4, 50.0)
    data[0x435D38:0x435D3C] = b"12\x00\x00"
    return data


def _write_valid_mpq(path):
    archive_size = 96
    header = b"MPQ\x1A" + struct.pack(
        "<IIHHIIII",
        32,
        archive_size,
        0,
        3,
        32,
        48,
        1,
        1,
    )
    data = bytearray(archive_size)
    data[:32] = header
    with open(path, "wb") as handle:
        handle.write(data)


class MpqValidationTests(unittest.TestCase):
    def test_strict_mpq_accepts_structurally_valid_classic_header(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "patch.mpq")
            _write_valid_mpq(path)
            dynamic._strict_verify_mpq(path)

    def test_strict_mpq_rejects_magic_only_or_truncated_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "patch.mpq")
            with open(path, "wb") as handle:
                handle.write(b"MPQ\x1A" + b"\x00" * 60)
            with self.assertRaises(remote_packages.RemotePackageError):
                dynamic._strict_verify_mpq(path)

    def test_visual_install_scopes_strict_hooks_and_restores_helpers(self):
        tool = object.__new__(dynamic.ModernWowSetupTool)
        original_verify = remote_packages._verify_mpq
        original_current = remote_packages.managed_mpq_is_current
        calls = []

        def fake_visual_install(_instance, target):
            calls.append(target)
            self.assertIs(remote_packages._verify_mpq, dynamic._strict_verify_mpq)
            self.assertIs(
                remote_packages.managed_mpq_is_current,
                dynamic._strict_managed_mpq_is_current,
            )
            return "done"

        with mock.patch.object(
            dynamic._ModernWowSetupToolCore,
            "configure_visual_audio",
            fake_visual_install,
        ):
            self.assertEqual(tool.configure_visual_audio("GAME"), "done")

        self.assertEqual(calls, ["GAME"])
        self.assertIs(remote_packages._verify_mpq, original_verify)
        self.assertIs(remote_packages.managed_mpq_is_current, original_current)

    def test_strict_current_mpq_check_uses_full_header_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = os.path.join(temp, "Data")
            os.makedirs(data_dir)
            path = os.path.join(data_dir, "patch-X.mpq")
            with open(path, "wb") as handle:
                handle.write(b"MPQ\x1A" + b"\x00" * 60)

            with mock.patch.object(
                remote_packages,
                "managed_mod_is_current",
                return_value=True,
            ), mock.patch.object(
                remote_packages,
                "_load_managed_manifest",
                return_value=[os.path.join("Data", "patch-X.mpq")],
            ):
                self.assertFalse(
                    dynamic._strict_managed_mpq_is_current(
                        temp,
                        "visual_test",
                        "1",
                    )
                )


class VanillaTweaksSourceValidationTests(unittest.TestCase):
    def test_community_numeric_values_remain_compatible(self):
        tool = _make_tool()
        data = _base_client_data()

        # Legitimate community launchers can already carry user-selected values.
        struct.pack_into("<f", data, 0x4089B4, math.radians(100))
        struct.pack_into("<f", data, 0x40FED8, 2500.0)
        struct.pack_into("<f", data, 0x467958, 120.0)
        struct.pack_into("<f", data, 0x40C448, 35.0)
        struct.pack_into("<f", data, 0x4089A4, 80.0)
        data[0x435D38:0x435D3C] = b"32\x00\x00"
        before = bytes(data)

        tool._validate_client_identity(data)
        tool._validate_vanilla_tweaks_state(
            data,
            allow_foreign_custom_glues=True,
        )
        tool._validate_source_numeric_values(data)
        self.assertEqual(bytes(data), before)

    def test_fixed_build_string_does_not_block_compatible_patch_sites(self):
        tool = _make_tool()
        data = _base_client_data()
        data[
            dynamic._CLIENT_BUILD_OFFSET:
            dynamic._CLIENT_BUILD_OFFSET + len(dynamic._CLIENT_BUILD)
        ] = b"9999"

        tool._validate_client_identity(data)
        tool._validate_vanilla_tweaks_state(
            data,
            allow_foreign_custom_glues=True,
        )

    def test_out_of_range_source_numeric_state_is_rejected(self):
        tool = _make_tool()
        data = _base_client_data()
        struct.pack_into("<f", data, 0x40FED8, 50000.0)
        with self.assertRaisesRegex(RuntimeError, "Farclip"):
            tool._validate_source_numeric_values(data)

    def test_normalization_overwrites_intermediate_numeric_values(self):
        tool = _make_tool()
        data = _base_client_data()

        # The upstream patcher may temporarily emit different numeric values.
        # They are not trusted as final output: the Tool overwrites them below.
        struct.pack_into("<f", data, 0x4089B4, 2.5)
        struct.pack_into("<f", data, 0x40FED8, 2345.0)
        struct.pack_into("<f", data, 0x467958, 444.0)
        struct.pack_into("<f", data, 0x40C448, 88.0)
        struct.pack_into("<f", data, 0x4089A4, 123.0)
        data[0x435D38:0x435D3C] = b"96\x00\x00"

        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "WoW_Modernized.exe")
            with open(path, "wb") as handle:
                handle.write(data)

            tool._normalize_selected_vanilla_tweaks_output(path)
            with open(path, "rb") as handle:
                result = handle.read()

        self.assertAlmostEqual(
            struct.unpack_from("<f", result, 0x4089B4)[0],
            1.9199,
            places=4,
        )
        self.assertEqual(struct.unpack_from("<f", result, 0x40FED8)[0], 3000.0)
        self.assertEqual(struct.unpack_from("<f", result, 0x467958)[0], 300.0)
        self.assertEqual(struct.unpack_from("<f", result, 0x40C448)[0], 41.0)
        self.assertEqual(struct.unpack_from("<f", result, 0x4089A4)[0], 100.0)
        self.assertEqual(result[0x435D38:0x435D3C], b"64\x00\x00")


class InstallationOrderingTests(unittest.TestCase):
    def test_vanilla_tweaks_runs_once_before_first_install_write(self):
        tool = object.__new__(dynamic.ModernWowSetupTool)
        events = []

        original_clean = lambda target: events.append(("clean", target))
        original_vt = lambda target: (
            events.append(("vanilla_tweaks", target))
            or os.path.join(target, "WoW_Modernized.exe")
        )
        tool.clean_unselected_files = original_clean
        tool.run_vanilla_tweaks = original_vt

        def fake_base_install(instance):
            events.append(("base", "validated"))
            instance.clean_unselected_files("GAME")
            events.append(("base", "after_clean"))
            instance.run_vanilla_tweaks("GAME")
            return "done"

        with mock.patch.object(
            dynamic._ModernWowSetupToolCore,
            "run_installation",
            fake_base_install,
        ):
            self.assertEqual(tool.run_installation(), "done")

        self.assertEqual(
            events,
            [
                ("base", "validated"),
                ("vanilla_tweaks", "GAME"),
                ("clean", "GAME"),
                ("base", "after_clean"),
            ],
        )
        self.assertIs(tool.clean_unselected_files, original_clean)
        self.assertIs(tool.run_vanilla_tweaks, original_vt)

    def test_vanilla_tweaks_failure_prevents_first_install_write(self):
        tool = object.__new__(dynamic.ModernWowSetupTool)
        events = []

        def original_clean(target):
            events.append(("clean", target))

        def original_vt(_target):
            events.append(("vanilla_tweaks", "failed"))
            raise RuntimeError("patcher failed")

        tool.clean_unselected_files = original_clean
        tool.run_vanilla_tweaks = original_vt

        def fake_base_install(instance):
            instance.clean_unselected_files("GAME")
            self.fail("clean_unselected_files should not complete after VT failure")

        with mock.patch.object(
            dynamic._ModernWowSetupToolCore,
            "run_installation",
            fake_base_install,
        ):
            with self.assertRaisesRegex(RuntimeError, "patcher failed"):
                tool.run_installation()

        self.assertEqual(events, [("vanilla_tweaks", "failed")])
        self.assertIs(tool.clean_unselected_files, original_clean)
        self.assertIs(tool.run_vanilla_tweaks, original_vt)


if __name__ == "__main__":
    unittest.main()
