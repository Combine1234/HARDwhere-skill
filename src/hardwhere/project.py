
import html
import json
import math
import os
from pathlib import Path
import tempfile

from .runner import WorkflowError


def read_object(path):
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise WorkflowError("Expected a JSON object.")
    return obj


def context_path(project):
    if not project.is_dir():
        raise WorkflowError("Pass an existing project directory.")
    return project / ".hardwhere" / "context.json"


def save_context(project, source):
    data = read_object(source)
    allowed = {"board", "revision", "modules", "wiring", "sources", "tools", "checks", "next_step"}
    if set(data) - allowed:
        raise WorkflowError("Only hardware context fields are accepted. Keep SSH config, credentials, and raw logs local.")
    if not data.get("board"):
        raise WorkflowError("Context needs a board name.")
    path = context_path(project)
    path.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as stream:
        staged = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False, indent=2)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)
    return {"context": str(path)}


def label(value, field):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise WorkflowError(f"{field} must be a nonempty, single-line label.")
    return value


def endpoint(value, field):
    if not isinstance(value, list) or len(value) != 2:
        raise WorkflowError(f"{field} needs [component, pin label].")
    return " / ".join(label(part, field) for part in value)


def volts(wire, field):
    value = wire.get(field)
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        raise WorkflowError(f"Confirm {field} from the board or module documentation.")
    return value


def markdown(value):
    return html.escape(value).replace("|", "&#124;").replace(chr(96), "&#96;")


def mermaid(value):
    return "".join(f"#{ord(c)};" if c in '"#&<>[]|' or ord(c) == 96 else c for c in value)


def render_wiring(data):
    rows = data.get("wires")
    if not isinstance(rows, list) or not rows:
        raise WorkflowError("Provide a nonempty wires list.")
    table = ["| Board pin | Module pin | Signal | Voltage | Source |", "|---|---|---|---|---|"]
    diagram = ["flowchart LR"]
    lines = {}
    for row in rows:
        if not isinstance(row, dict):
            raise WorkflowError("Each wire must be an object.")
        voltage = volts(row, "voltage_v")
        limit = volts(row, "max_voltage_v")
        left = endpoint(row.get("from"), "from")
        right = endpoint(row.get("to"), "to")
        name = label(row.get("signal"), "signal")
        source = label(row.get("source"), "source")
        if voltage > limit:
            raise WorkflowError(f"{name}: {voltage:g} V exceeds the documented {limit:g} V limit. Check the interface.")
        values = (left, right, name, f"{voltage:g} V", source)
        table.append("| " + " | ".join(map(markdown, values)) + " |")
        for item in (left, right):
            if item not in lines:
                lines[item] = f"pin{len(lines)}"
                diagram.append(f'    {lines[item]}["{mermaid(item)}"]')
        diagram.append(f'    {lines[left]} ---|"{mermaid(f"{name} · {voltage:g} V")}"| {lines[right]}')
    return {"table": "\n".join(table), "mermaid": "\n".join(diagram)}
