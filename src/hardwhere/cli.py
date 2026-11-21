
import argparse
import json
from pathlib import Path
import re
import sys

from . import firmware, hardware, project, ssh
from .profiles import PROFILES, require
from .runner import WorkflowError


def parser():
    root = argparse.ArgumentParser(prog="hardwhere", description="Run embedded hardware workflows.")
    root.add_argument("--json", action="store_true", help="emit a JSON result (before or after the command)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("profiles", help="list known board profiles and supported operations")
    commands.add_parser("discover", help="list local USB serial and Teensy bootloader devices")

    def board_command(name, help_text):
        cmd = commands.add_parser(name, help=help_text)
        cmd.add_argument("--board", required=True, choices=PROFILES)
        return cmd

    board_command("doctor", "inspect board tools, ports and applicable host driver")
    install = board_command("install", "install a vendor core, libraries, or Windows bridge driver")
    install.add_argument("--core", action="store_true", help="install the board core even with --library")
    install.add_argument("--version", help="version of the board core")
    install.add_argument("--library", action="append", default=[], help="Arduino library name or name@version")
    install.add_argument("--driver-inf", type=Path, help="install only this supported vendor INF")
    install.add_argument("--apply", action="store_true")

    build = board_command("build", "compile an Arduino sketch into a new artifact directory")
    build.add_argument("--sketch", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    flash = board_command("flash", "upload a built artifact to the discovered target")
    flash.add_argument("--target", required=True)
    flash.add_argument("--artifact", required=True, type=Path)
    flash.add_argument("--apply", action="store_true")

    for command, hint in (("monitor", "capture serial output"), ("verify", "check a complete serial line")):
        serial = board_command(command, hint)
        serial.add_argument("--target", required=True)
        serial.add_argument("--baud", type=int, default=115200)
        serial.add_argument("--seconds", type=float, default=8)
        if command == "verify":
            serial.add_argument("--expect", required=True, help="regular expression matched to a full line")

    wiring = commands.add_parser("wiring", help="render wiring JSON as a table and Mermaid diagram")
    wiring.add_argument("input", type=Path)
    context = commands.add_parser("context", help="save or resume a local project checkpoint")
    context_cmds = context.add_subparsers(dest="action", required=True)
    for action in ("save", "show"):
        cmd = context_cmds.add_parser(action)
        cmd.add_argument("--project", type=Path, default=Path.cwd())
        if action == "save":
            cmd.add_argument("input", type=Path)

    remote = commands.add_parser("ssh", help="configure and use SSH for a Linux Raspberry Pi 4B")
    remote_cmds = remote.add_subparsers(dest="action", required=True)
    for action in ("config", "probe", "onboard", "run"):
        cmd = remote_cmds.add_parser(action)
        cmd.add_argument("--alias", required=True)
        if action == "config":
            cmd.add_argument("--host", required=True)
            cmd.add_argument("--user", required=True)
            cmd.add_argument("--port", type=int, default=22)
        if action == "onboard":
            cmd.add_argument("--skills-dir", type=Path)
        if action in ("config", "onboard", "run"):
            cmd.add_argument("--apply", action="store_true")
        if action == "run":
            cmd.add_argument("--script", required=True, type=Path)
            cmd.add_argument("--expect")
    return root


def applying(args):
    if not args.apply:
        raise WorkflowError("This action changes the host or target. Provide --apply after confirming the intended action.")


def remote_workflow(args):
    if args.action == "config":
        settings = ssh.config_for(args.alias, args.host, args.user, args.port)
        return ssh.apply_config(args.alias, settings) if args.apply else settings
    if args.action == "probe":
        return ssh.probe(args.alias)
    applying(args)
    if args.action == "onboard":
        return ssh.onboard(args.alias, skills_dir=args.skills_dir)
    return ssh.run_script(args.alias, args.script, args.expect)


def board_workflow(args):
    profile = PROFILES[args.board]
    require(profile, args.command)
    if args.command == "doctor":
        return hardware.doctor(profile)
    if args.command == "install":
        applying(args)
        if args.driver_inf:
            require(profile, "install-driver-windows")
            if args.core or args.version or args.library:
                raise WorkflowError("Install a driver separately from the board core and libraries.")
            return hardware.install_driver(profile, args.driver_inf)
        return firmware.install(profile, args.version, args.library, args.core)
    if args.command == "build":
        return firmware.build(profile, args.sketch, args.output)
    if args.command == "flash":
        applying(args)
        return firmware.flash(profile, args.target, args.artifact)
    if not 0.25 <= args.seconds <= 60 or not 1 <= args.baud <= 4000000:
        raise WorkflowError("Use a capture duration of 0.25–60 seconds and a baud rate of 1–4000000.")
    if args.command == "verify":
        re.compile(args.expect)
    result = hardware.capture(profile, args.target, args.baud, args.seconds)
    if args.command == "verify":
        result["matched"] = hardware.verify_output(result["output"], args.expect)
    return result


def execute(args):
    if args.command == "profiles":
        return {"profiles": [
            {key: getattr(p, key) for key in ("id", "name", "sources", "capabilities")}
            for p in PROFILES.values()
        ]}
    if args.command == "discover":
        return {"devices": [device.public() for device in hardware.discover_devices()]}
    if args.command == "ssh":
        return remote_workflow(args)
    if args.command == "wiring":
        return project.render_wiring(project.read_object(args.input))
    if args.command == "context":
        if args.action == "save":
            return project.save_context(args.project, args.input)
        return project.read_object(project.context_path(args.project))
    return board_workflow(args)


def human(result):
    if "table" in result and "mermaid" in result:
        fence = chr(96) * 3
        return f'{result["table"]}\n\n{fence}mermaid\n{result["mermaid"]}\n{fence}'
    lines = []
    for key, value in result.items():
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            lines.append(f"{key}:")
            for item in value:
                lines.append("  " + " | ".join(f"{name}={field}" for name, field in item.items()))
            if not value:
                lines.append("  none")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    result_json = "--json" in argv
    args = parser().parse_args([arg for arg in argv if arg != "--json"])
    try:
        result = {"ok": True, **execute(args)}
    except (WorkflowError, OSError, ImportError, ValueError, re.error) as exc:
        result = {"ok": False, "error": str(exc), **getattr(exc, "details", {})}
    if result_json:
        print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
    else:
        stream = sys.stdout if result["ok"] else sys.stderr
        print(human(result).encode(stream.encoding or "utf-8", errors="replace").decode(
            stream.encoding or "utf-8"
        ), file=stream)
    return 0 if result["ok"] else 1
