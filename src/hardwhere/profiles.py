
from dataclasses import dataclass

from .runner import WorkflowError


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    sources: tuple[str, ...]
    capabilities: tuple[str, ...]
    fqbn: str = ""
    core: str = ""
    index: str = ""
    serial_ids: tuple[tuple[int, int], ...] = ()
    boot_id: tuple[int, int] | None = None
    mcu: str = ""
    windows_inf: str = ""

    def arduino(self, *args):
        urls = ["--additional-urls", self.index] if self.index else []
        return ["arduino-cli", *urls, *args]


USB_WORKFLOW = ("discover", "doctor", "install", "build", "flash", "monitor", "verify")
PROFILES = {
    profile.id: profile
    for profile in (
        Profile(
            "arduino-uno-r3", "Arduino UNO R3 (official board)",
            ("https://docs.arduino.cc/hardware/uno-rev3/", "https://docs.arduino.cc/arduino-cli/"),
            USB_WORKFLOW, "arduino:avr:uno", "arduino:avr",
            serial_ids=((0x2341, 0x0043), (0x2A03, 0x0043)),
        ),
        Profile(
            "esp32-devkitc-v4", "ESP32-DevKitC V4 (ESP32-WROOM-32 series, CP210x)",
            (
                "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html",
                "https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html",
                "https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers",
            ),
            (*USB_WORKFLOW, "install-driver-windows"), "esp32:esp32:esp32", "esp32:esp32",
            "https://espressif.github.io/arduino-esp32/package_esp32_index.json",
            serial_ids=((0x10C4, 0xEA60),), windows_inf="silabser.inf",
        ),
        Profile(
            "teensy-4-1", "Teensy 4.1 (default USB Serial build)",
            ("https://www.pjrc.com/store/teensy41.html", "https://www.pjrc.com/teensy/loader_cli.html"),
            USB_WORKFLOW, "teensy:avr:teensy41", "teensy:avr",
            "https://www.pjrc.com/teensy/package_teensy_index.json",
            serial_ids=((0x16C0, 0x0483),), boot_id=(0x16C0, 0x0478), mcu="TEENSY41",
        ),
        Profile(
            "raspberry-pi-4b", "Raspberry Pi 4 Model B, Linux over SSH",
            ("https://www.raspberrypi.com/documentation/computers/remote-access.html",),
            ("doctor", "ssh-probe", "ssh-run", "ssh-onboard"),
        ),
    )
}


def require(profile, capability):
    if capability not in profile.capabilities:
        raise WorkflowError(f"{profile.id} does not support {capability}. Run profiles for supported operations.")
