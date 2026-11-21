
import shutil
import subprocess


class WorkflowError(Exception):
    def __init__(self, message, **details):
        super().__init__(message)
        self.details = details


def run(argv, *, timeout=30, stdin=None):
    executable = shutil.which(argv[0])
    if not executable:
        raise WorkflowError(f"{argv[0]} is missing. Run doctor or see the installation guide.")
    if executable.lower().endswith((".cmd", ".bat")):
        raise WorkflowError(f"Use the native {argv[0]} executable instead of a batch wrapper.")
    try:
        result = subprocess.run(
            [executable, *argv[1:]], input=stdin, capture_output=True,
            timeout=timeout, check=False, shell=False,
        )
    except subprocess.TimeoutExpired:
        raise WorkflowError(f"{argv[0]} exceeded {timeout}s. Inspect the target before retrying.") from None
    output = {
        "stdout": result.stdout.decode("utf-8", errors="replace").lstrip("\ufeff").strip("\r"),
        "stderr": result.stderr.decode("utf-8", errors="replace").lstrip("\ufeff"),
        "returncode": result.returncode,
    }
    if result.returncode:
        reason = output["stderr"].strip() or output["stdout"].strip()
        raise WorkflowError(f"{argv[0]} exited {result.returncode}: {reason}", **output)
    return output
