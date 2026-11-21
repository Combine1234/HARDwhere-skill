
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class CommandTest(unittest.TestCase):
    def cli(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        return subprocess.run(
            [sys.executable, "-m", "hardwhere", *map(str, args)],
            capture_output=True, text=True, encoding="utf-8", env=env, check=False,
        )

    def test_profiles_publish_capabilities(self):
        result = self.cli("profiles", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        profiles = {p["id"]: p for p in json.loads(result.stdout)["profiles"]}
        self.assertIn("flash", profiles["esp32-devkitc-v4"]["capabilities"])
        self.assertIn("ssh-run", profiles["raspberry-pi-4b"]["capabilities"])
        self.assertNotIn("flash", profiles["raspberry-pi-4b"]["capabilities"])

    def test_wiring_renders_both_views_with_same_pins(self):
        result = self.cli("wiring", ROOT / "examples/esp32-bme280/wiring.json", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        for label in ("IO21", "GPIO21", "SDI", "SDA"):
            self.assertIn(label, output["table"])
            self.assertIn(label, output["mermaid"])

    def test_wiring_stops_when_voltage_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wiring.json"
            path.write_text(json.dumps({"wires": [{
                "from": ["ESP32", "IO21"], "to": ["BME280", "SDI"], "signal": "SDA"
            }]}), encoding="utf-8")
            result = self.cli("wiring", path, "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("voltage_v", json.loads(result.stdout)["error"])

    def test_context_round_trip_preserves_debug_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            source = workspace / "checkpoint.json"
            source.write_text(json.dumps({
                "board": "ESP32-DevKitC V4",
                "next_step": "Check I2C after a verified upload",
                "checks": [{"step": "flash", "status": "passed", "evidence": "fixture"}]
            }), encoding="utf-8")
            saved = self.cli("context", "save", source, "--project", workspace, "--json")
            self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
            resumed = self.cli("context", "show", "--project", workspace, "--json")
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertEqual(json.loads(resumed.stdout)["next_step"], "Check I2C after a verified upload")

    def test_flash_requires_apply_before_tool_access(self):
        result = self.cli("flash", "--board", "arduino-uno-r3", "--target", "unknown",
                          "--artifact", "does-not-exist", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--apply", json.loads(result.stdout)["error"])


class HardwareTest(unittest.TestCase):
    def test_same_serial_identity_resolves_changed_port(self):
        from hardwhere.hardware import Device, resolve_target
        from hardwhere.profiles import PROFILES

        old = Device("COM3", 0x2341, 0x0043, serial="UNO123")
        moved = Device("COM8", 0x2341, 0x0043, serial="UNO123")
        self.assertEqual(resolve_target(PROFILES["arduino-uno-r3"], old.target, [moved]), moved)

    def test_duplicate_serial_requires_physical_disambiguation(self):
        from hardwhere.hardware import Device, resolve_target
        from hardwhere.profiles import PROFILES
        from hardwhere.runner import WorkflowError

        one = Device("COM3", 0x10C4, 0xEA60, serial="0001", location="a")
        two = Device("COM4", 0x10C4, 0xEA60, serial="0001", location="b")
        with self.assertRaisesRegex(WorkflowError, "ambiguous"):
            resolve_target(PROFILES["esp32-devkitc-v4"], one.target, [one, two])

    def test_teensy_bootloader_cannot_choose_between_distinct_devices(self):
        from hardwhere.hardware import Device, resolve_target
        from hardwhere.profiles import PROFILES
        from hardwhere.runner import WorkflowError

        boot_a = Device("hid-a", 0x16C0, 0x0478, location="first", transport="hid")
        boot_b = Device("hid-b", 0x16C0, 0x0478, location="second", transport="hid")
        with self.assertRaisesRegex(WorkflowError, "ambiguous"):
            resolve_target(PROFILES["teensy-4-1"], boot_a.target, [boot_a, boot_b], flash=True)

    def test_missing_windows_driver_is_found_without_a_serial_port(self):
        from hardwhere.hardware import windows_driver_state
        from hardwhere.profiles import PROFILES

        devices = [{"PNPDeviceID": r"USB\VID_10C4&PID_EA60\123", "ConfigManagerErrorCode": 28}]
        self.assertEqual(windows_driver_state(PROFILES["esp32-devkitc-v4"], devices), "missing")

    @patch("hardwhere.hardware.windows_usb")
    @patch("hardwhere.hardware.discover_devices", return_value=[])
    @patch("hardwhere.hardware.shutil.which", return_value=None)
    @patch("hardwhere.hardware.platform.system", return_value="Windows")
    def test_doctor_preserves_usb_report_when_wmi_cannot_be_read(self, os_name, which, discover, usb):
        from hardwhere.hardware import doctor
        from hardwhere.profiles import PROFILES
        from hardwhere.runner import WorkflowError

        usb.side_effect = WorkflowError("CIM access denied")
        result = doctor(PROFILES["esp32-devkitc-v4"])
        self.assertEqual(result["devices"], [])
        self.assertEqual(result["host_driver"], "unavailable")
        self.assertIn("CIM access denied", result["diagnostics"]["host_driver"])

    def test_manifest_refuses_modified_firmware(self):
        from hardwhere.firmware import write_manifest, check_manifest
        from hardwhere.profiles import PROFILES
        from hardwhere.runner import WorkflowError

        profile = PROFILES["arduino-uno-r3"]
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)
            (artifact / "blink.ino.hex").write_bytes(b"first")
            write_manifest(artifact, profile)
            (artifact / "blink.ino.hex").write_bytes(b"modified")
            with self.assertRaisesRegex(WorkflowError, "changed"):
                check_manifest(artifact, profile)

    @patch("hardwhere.firmware.run")
    @patch("hardwhere.firmware.discover_devices")
    def test_flash_of_moved_uno_artifact_passes_resolved_port(self, discover, execute):
        from hardwhere.firmware import flash, write_manifest
        from hardwhere.hardware import Device
        from hardwhere.profiles import PROFILES

        device = Device("COM8", 0x2341, 0x0043, serial="UNO123")
        discover.return_value = [device]
        execute.return_value = {"stdout": "", "stderr": "", "returncode": 0}
        profile = PROFILES["arduino-uno-r3"]
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)
            (artifact / "blink.ino.hex").write_bytes(b"hex data")
            write_manifest(artifact, profile, sketch=Path("old-checkout/blink"))
            result = flash(profile, device.target, artifact)
            self.assertEqual(result["stage"], "uploaded")
            execute.assert_called_once_with([
                "arduino-cli", "upload", "--fqbn", "arduino:avr:uno", "--protocol", "serial",
                "--port", "COM8", "--input-dir", str(artifact.resolve()), "--verify",
            ], timeout=180)

    def test_verify_requires_complete_expected_line(self):
        from hardwhere.hardware import verify_output
        from hardwhere.runner import WorkflowError

        verify_output("BOOT\nHARDWHERE_OK temp_c=24.51\n", r"HARDWHERE_OK temp_c=-?\d+\.\d+")
        for output in ("BOOT\n", "HARDWHERE_OK temp_c=24.51", "ERR HARDWHERE_OK temp_c=24.51\n"):
            with self.subTest(output=output), self.assertRaises(WorkflowError):
                verify_output(output, r"HARDWHERE_OK temp_c=-?\d+\.\d+")


class SSHTest(unittest.TestCase):
    def test_scope_text_cannot_insert_ssh_directives(self):
        from hardwhere import ssh
        from hardwhere.runner import WorkflowError

        with self.assertRaises(WorkflowError):
            ssh.config_for("bench-pi", "fe80::1%zone\n    Port 44", "student", 22)

    @patch("hardwhere.ssh.run")
    def test_pending_alias_write_cannot_overwrite_config(self, execute):
        from hardwhere import ssh
        from hardwhere.runner import WorkflowError

        execute.return_value = {"stdout": "hostname bench-pi\n"}
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            config.write_text("# existing", encoding="utf-8")
            (config.parent / "config.hardwhere.lock").touch()
            settings = ssh.config_for("bench-pi", "bench.local", "student", 22)
            settings["config_path"] = str(config)
            with self.assertRaisesRegex(WorkflowError, "another HARDwhere"):
                ssh.apply_config("bench-pi", settings)
            self.assertEqual(config.read_text(encoding="utf-8"), "# existing")

    @patch("hardwhere.ssh.run")
    def test_add_alias_preserves_existing_ssh_config(self, execute):
        from hardwhere import ssh

        execute.return_value = {"stdout": "hostname bench-pi\n"}
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            previous = "Host other\n    HostName other.local\n"
            config.write_text(previous, encoding="utf-8")
            settings = ssh.config_for("bench-pi", "bench.local", "student", 22)
            settings["config_path"] = str(config)
            ssh.apply_config("bench-pi", settings)
            written = config.read_text(encoding="utf-8")
            self.assertTrue(written.startswith("Host bench-pi\n    HostName bench.local\n"))
            self.assertTrue(written.endswith(previous))

    @patch("hardwhere.ssh.run")
    def test_changed_host_key_creates_no_skill(self, execute):
        from hardwhere import ssh
        from hardwhere.runner import WorkflowError

        execute.side_effect = WorkflowError("REMOTE HOST IDENTIFICATION HAS CHANGED")
        with tempfile.TemporaryDirectory() as directory:
            skills = Path(directory) / "skills"
            with self.assertRaisesRegex(WorkflowError, "HOST IDENTIFICATION"):
                ssh.onboard("bench-pi", skills_dir=skills)
            self.assertFalse(skills.exists())
        argv = execute.call_args.args[0]
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("BatchMode=yes", argv)

    @patch("hardwhere.ssh.run")
    def test_successful_probe_writes_alias_only_skill(self, execute):
        from hardwhere import ssh

        execute.return_value = {"stdout": "Raspberry Pi 4 Model B Rev 1.5\nLinux aarch64\n"}
        with tempfile.TemporaryDirectory() as directory:
            skills = Path(directory) / "skills"
            result = ssh.onboard("bench-pi", skills_dir=skills)
            path = Path(result["skill"])
            self.assertEqual(path.parent.parent, skills.resolve())
            self.assertIn("bench-pi", path.read_text(encoding="utf-8"))
            self.assertNotIn("Rev 1.5", path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(OSError, "exist"):
                ssh.onboard("bench-pi", skills_dir=skills)
