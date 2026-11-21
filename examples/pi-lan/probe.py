
from pathlib import Path

model = Path("/proc/device-tree/model").read_bytes().rstrip(b"\0").decode()
assert model.startswith("Raspberry Pi 4 Model B"), model
print("HARDWHERE_OK pi4")
