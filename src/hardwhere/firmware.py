
import hashlib
import json
from pathlib import Path
import re

from .hardware import discover_devices, resolve_target
from .runner import WorkflowError, run


MANIFEST = "hardwhere-build.json"


def install(profile, version, libraries, core_only=False):
    if version and not re.fullmatch(r"[0-9][a-zA-Z0-9.+-]*", version):
        raise WorkflowError("Invalid core version.")
    if any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9 ._@+-]*", name) for name in libraries):
        raise WorkflowError("Use exact Arduino library manager names and optional @versions.")
    results = []
    if core_only or not libraries or version:
        spec = profile.core + (f"@{version}" if version else "")
        results.append(run(profile.arduino("core", "update-index"), timeout=300))
        results.append(run(profile.arduino("core", "install", spec), timeout=1200))
    if libraries:
        results.append(run(profile.arduino("lib", "update-index"), timeout=300))
        results.append(run(profile.arduino("lib", "install", *libraries), timeout=600))
    return {"profile": profile.id, "operations": results}


def file_hashes(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise WorkflowError("The artifact directory contains a symbolic link.")
        if path.name != MANIFEST and path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(block)
            result[path.relative_to(directory).as_posix()] = digest.hexdigest()
    return result


def write_manifest(directory, profile, *, sketch=None, toolchain=None):
    data = {
        "schema": 1, "profile": profile.id, "fqbn": profile.fqbn,
        "sketch": sketch.name if sketch else None, "toolchain": toolchain,
        "files": file_hashes(directory),
    }
    if not data["files"]:
        raise WorkflowError("The compiler did not export any files.")
    with (directory / MANIFEST).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
    return data


def check_manifest(directory, profile):
    data = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("schema") != 1 or data.get("profile") != profile.id
            or data.get("fqbn") != profile.fqbn):
        raise WorkflowError("This build artifact belongs to another board profile or manifest version.")
    if not data.get("files") or file_hashes(directory) != data["files"]:
        raise WorkflowError("Build files changed after compilation. Build into a new directory.")
    return data


def build(profile, sketch, output):
    sketch = sketch.resolve()
    if not sketch.is_dir() or not (sketch / f"{sketch.name}.ino").is_file():
        raise WorkflowError("Pass a sketch directory containing a matching .ino file.")
    output = output.resolve()
    if sketch == output or sketch in output.parents:
        raise WorkflowError("Use an artifact directory outside the sketch tree.")
    output.mkdir(parents=True, exist_ok=False)
    version = run(profile.arduino("version"))["stdout"].strip()
    cores = run(profile.arduino("core", "list"))["stdout"].strip()
    logs = run(profile.arduino(
        "compile", "--fqbn", profile.fqbn, "--output-dir", str(output), str(sketch)
    ), timeout=600)
    data = write_manifest(output, profile, sketch=sketch, toolchain={"cli": version, "cores": cores})
    return {"profile": profile.id, "artifact": str(output), "build": data, **logs}


def flash(profile, target, artifact):
    artifact = artifact.resolve()
    data = check_manifest(artifact, profile)
    device = resolve_target(profile, target, discover_devices(), flash=True)
    if profile.mcu:
        filename = f'{data.get("sketch")}.ino.hex'
        image = artifact / filename
        if filename not in data["files"] or image.parent != artifact or not image.is_file():
            raise WorkflowError("The Teensy sketch HEX is missing from the build.")
        # The loader writes to the first HalfKay device. Never wait for a later device.
        command = ["teensy_loader_cli", f"--mcu={profile.mcu}", "-v", str(image)]
    else:
        command = profile.arduino(
            "upload", "--fqbn", profile.fqbn, "--protocol", "serial", "--port", device.address,
            "--input-dir", str(artifact), "--verify",
        )
    return {"profile": profile.id, "target": device.public(), "stage": "uploaded",
            **run(command, timeout=180)}
