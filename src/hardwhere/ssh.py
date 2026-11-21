
import ipaddress
import os
from pathlib import Path
import re
import stat
import tempfile

from .hardware import verify_output
from .runner import WorkflowError, run


PROBE = "tr -d '\\000' </proc/device-tree/model && printf '\\n' && uname -sm"
PI4 = "Raspberry Pi 4 Model B"


def alias_name(alias):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", alias):
        raise WorkflowError("Use an SSH alias with 1–48 lowercase letters, digits, and hyphens.")
    return alias


def config_for(alias, host, user, port):
    alias_name(alias)
    if not re.fullmatch(r"[a-zA-Z0-9_.][a-zA-Z0-9_.-]{0,63}", user):
        raise WorkflowError("Invalid OpenSSH user name.")
    if not re.fullmatch(r"[a-zA-Z0-9.:_-]+", host):
        raise WorkflowError("Provide an unscoped IP address or hostname without SSH configuration syntax.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", host) or ".." in host:
            raise WorkflowError("Provide a hostname or IP address with no SSH configuration syntax.") from None
    if not 1 <= port <= 65535:
        raise WorkflowError("SSH port must be 1–65535.")
    return {
        "config_path": str(Path.home() / ".ssh" / "config"),
        "config": f"Host {alias}\n    HostName {host}\n    User {user}\n    Port {port}\n",
    }



def apply_config(alias, settings):
    path = Path(settings["config_path"])
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".hardwhere.lock")
    try:
        lock_path.touch(mode=0o600, exist_ok=False)
    except FileExistsError:
        raise WorkflowError("SSH config may be in use by another HARDwhere process.") from None
    try:
        update_config(alias, path, settings["config"])
    finally:
        lock_path.unlink(missing_ok=True)
    return {"alias": alias, "config_path": str(path), "next_step": (
        "If this is a new host key, compare its fingerprint with the Pi and enroll it using OpenSSH."
    )}


def update_config(alias, path, stanza):
    if path.is_symlink():
        raise WorkflowError("Preview the stanza and update your linked SSH config manually.")
    previous = path.read_bytes() if path.exists() else b""
    found = run(["ssh", "-G", alias_name(alias)])["stdout"]
    resolved = next((line.split(maxsplit=1)[1] for line in found.splitlines()
                     if line.startswith("hostname ")), None)
    explicit = any(
        alias in line.split("#", 1)[0].lower().split()[1:]
        for line in previous.decode("utf-8", errors="replace").splitlines()
        if line.strip().lower().startswith("host ")
    )
    if resolved != alias or explicit:
        raise WorkflowError("That SSH alias is already defined. Reuse it or choose a new alias.")
    prefix = (stanza + "\nHost *\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        staged = Path(stream.name)
        stream.write(prefix + previous)
    try:
        if path.exists():
            staged.chmod(stat.S_IMODE(path.stat().st_mode))
        current = path.read_bytes() if path.exists() else b""
        if current != previous:
            raise WorkflowError("SSH config changed during setup. Inspect it before retrying.")
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def ssh_argv(alias, command):
    return [
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "UpdateHostKeys=no", "-o", "ClearAllForwardings=yes",
        "-o", "ForwardAgent=no", "-o", "PermitLocalCommand=no", "-o", "ConnectTimeout=8", alias_name(alias), command,
    ]


def probe(alias):
    result = run(ssh_argv(alias, PROBE), timeout=20)
    lines = result["stdout"].splitlines()
    if len(lines) != 2 or not lines[0].startswith(PI4) or not lines[1].startswith("Linux "):
        raise WorkflowError("SSH connected, but the reported hardware and OS do not match the Pi 4B Linux profile.")
    return {"model": lines[0], "system": lines[1]}


def onboard(alias, *, skills_dir=None):
    device = probe(alias)
    codex_dir = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    parent = (skills_dir or codex_dir / "skills").resolve()
    skill_id = f"ssh-{alias}"
    path = parent / skill_id / "SKILL.md"
    if any((ancestor / ".git").exists() for ancestor in path.parents):
        raise WorkflowError("Place the SSH skill outside all Git worktrees.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(f"""---
name: {skill_id}
description: Reconnect to the user's Raspberry Pi through the local OpenSSH alias {alias}.
---

Use the existing OpenSSH alias {alias}. For a read-only model and OS check, run
    hardwhere ssh probe --alias {alias}

Use the user's existing SSH key or agent and known_hosts configuration.
Stop if host identity fails. Scope remote operations to the current user request.
For an approved Python test script, run
    hardwhere ssh run --alias {alias} --script <path-to-reviewed-script> --apply
""")
    return {**device, "skill": str(path)}


def run_script(alias, script, expected=None):
    if script.suffix != ".py" or not script.is_file():
        raise WorkflowError("Pass a local Python test script ending in .py.")
    if expected is not None:
        re.compile(expected)
    device = probe(alias)
    result = run(ssh_argv(alias, "python3 -u -"), timeout=60, stdin=script.read_bytes())
    if expected is not None:
        result["matched"] = verify_output(result["stdout"], expected)
    return {**device, **result}
