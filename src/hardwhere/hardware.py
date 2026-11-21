
from dataclasses import dataclass
from hashlib import sha256
from importlib.util import find_spec
import json
import platform
import re
import shutil
from time import monotonic

from .profiles import PROFILES
from .runner import WorkflowError, run


DRIVER_QUERY = (
    "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
    "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
    "$devices=@(Get-CimInstance Win32_PnPEntity | Where-Object { $_.Present -eq $true -and "
    "$_.PNPDeviceID -like 'USB\\VID_*' } | "
    "Select-Object PNPDeviceID,ConfigManagerErrorCode); "
    "ConvertTo-Json -InputObject $devices -Compress"
)


@dataclass(frozen=True)
class Device:
    address: str
    vid: int | None
    pid: int | None
    serial: str | None = None
    location: str | None = None
    transport: str = "serial"
    label: str = ""

    @property
    def target(self):
        if self.vid is None or self.pid is None:
            return None
        identity = ("serial", self.serial) if self.serial else ("location", self.location)
        if not identity[1]:
            return None
        key = f"{self.transport}:{self.vid:04x}:{self.pid:04x}:{identity[0]}:{identity[1]}"
        return sha256(key.encode()).hexdigest()[:20]

    @property
    def usb_id(self):
        return self.vid, self.pid

    def public(self):
        candidates = [
            p.id for p in PROFILES.values()
            if self.usb_id in p.serial_ids or self.usb_id == p.boot_id
        ]
        return {
            "target": self.target, "address": self.address, "transport": self.transport,
            "usb_id": f"{self.vid:04x}:{self.pid:04x}" if None not in self.usb_id else None,
            "suggested_profiles": candidates, "description": self.label,
        }


def discover_devices():
    from serial.tools import list_ports

    ports = [
        Device(p.device, p.vid, p.pid, p.serial_number, p.location, label=p.description or "")
        for p in list_ports.comports()
    ]
    try:
        import hid
    except ImportError:
        return ports
    # PJRC bootloader VID/PID is shared by multiple Teensy models.
    for item in hid.enumerate(0x16C0, 0x0478):
        path = item["path"].hex()
        ports.append(Device(
            f"hid:{path}", item["vendor_id"], item["product_id"],
            serial=item.get("serial_number") or None, location=path, transport="hid",
            label="Teensy HalfKay bootloader",
        ))
    return ports


def resolve_target(profile, target, devices, *, flash=False):
    hid_flash = flash and profile.boot_id is not None
    candidates = [
        item for item in devices
        if ((item.transport == "hid" and item.usb_id == profile.boot_id) if hid_flash
            else (item.transport == "serial" and item.usb_id in profile.serial_ids))
    ]
    matches = [item for item in candidates if item.target == target]
    if len(matches) > 1 or (hid_flash and len(candidates) > 1):
        raise WorkflowError("USB target is ambiguous. Disconnect the other boards and discover again.")
    if not matches:
        hint = ("Press the Program button on the confirmed Teensy 4.1 and discover its HID target."
                if hid_flash else "Check the USB data cable and board, then discover again.")
        raise WorkflowError(f"Target {target} is absent or incompatible with {profile.id}. {hint}")
    return matches[0]


def windows_driver_state(profile, devices):
    entries = [f"USB\\VID_{vid:04X}&PID_{pid:04X}" for vid, pid in profile.serial_ids]
    codes = [
        item.get("ConfigManagerErrorCode") for item in devices
        if any(item.get("PNPDeviceID", "").upper().startswith(entry) for entry in entries)
    ]
    if 28 in codes:
        return "missing"
    if codes:
        return "ready" if all(code == 0 for code in codes) else "device-error"
    return "usb-not-seen"


def windows_usb():
    result = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", DRIVER_QUERY])
    return json.loads(result["stdout"] or "[]")


def doctor(profile):
    tools = ["arduino-cli"] if profile.fqbn else ["ssh"]
    if profile.mcu:
        tools.append("teensy_loader_cli")
    installed = {tool: bool(shutil.which(tool)) for tool in tools}
    result = {"os": platform.system(), "profile": profile.id, "tools": installed}
    diagnostics = {}
    if profile.mcu:
        result["tools"]["hidapi"] = find_spec("hid") is not None
    if installed.get("arduino-cli"):
        result["arduino_version"] = run(profile.arduino("version"))["stdout"].strip()
        try:
            result["cores"] = run(profile.arduino("core", "list"))["stdout"].strip()
        except WorkflowError as exc:
            diagnostics["cores"] = str(exc)
    if profile.fqbn:
        ids = (*profile.serial_ids, profile.boot_id)
        result["devices"] = [d.public() for d in discover_devices() if d.usb_id in ids]
    if platform.system() == "Windows" and profile.windows_inf:
        try:
            result["host_driver"] = windows_driver_state(profile, windows_usb())
        except (WorkflowError, ValueError) as exc:
            result["host_driver"] = "unavailable"
            diagnostics["host_driver"] = str(exc)
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def install_driver(profile, inf_path):
    if platform.system() != "Windows":
        raise WorkflowError("This driver operation requires Windows. See the bridge vendor instructions for this OS.")
    if inf_path.name.lower() != profile.windows_inf or not inf_path.is_file():
        raise WorkflowError(f"Provide the extracted vendor package's {profile.windows_inf} file.")
    state = windows_driver_state(profile, windows_usb())
    if state != "missing":
        raise WorkflowError(f"Expected the supported bridge with a missing driver (PnP code 28). Detected {state}.")
    result = run(["pnputil.exe", "/add-driver", str(inf_path.resolve()), "/install"], timeout=120)
    ports = [d.public() for d in discover_devices() if d.usb_id in profile.serial_ids]
    if not ports or windows_driver_state(profile, windows_usb()) != "ready":
        raise WorkflowError("Driver command finished, but the matching bridge is not ready as a serial port.",
                            driver_command=result, devices=ports)
    return {"profile": profile.id, "driver_command": result, "devices": ports}


def capture(profile, target, baud, seconds):
    import serial

    device = resolve_target(profile, target, discover_devices())
    chunks = bytearray()
    with serial.Serial(baudrate=baud, timeout=0.25) as port:
        port.dtr = False
        port.rts = False
        port.port = device.address
        port.open()
        # USB CDC firmware can require DTR before it emits serial output.
        if profile.mcu:
            port.dtr = True
        deadline = monotonic() + seconds
        while monotonic() < deadline and len(chunks) < 262144:
            remaining = 262144 - len(chunks)
            chunks.extend(port.read(min(remaining, 4096, port.in_waiting or 1)))
    return {"device": device.public(), "output": chunks.decode("utf-8", errors="replace")}


def verify_output(output, expected):
    pattern = re.compile(expected)
    complete_lines = output.split("\n")[:-1]
    for line in complete_lines:
        line = line.removesuffix("\r")
        if pattern.fullmatch(line):
            return line
    raise WorkflowError("No complete output line matched the expected behavior.", output=output)
