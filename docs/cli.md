# CLI reference

Use `hardwhere <command> --help` for the full interface. Add `--json` to receive an object with `ok`, evidence, or error details. Exit codes are 0 for success, 1 for workflow failure, and 2 for invalid usage.

| Task | Invocation |
| :--- | :--- |
| Identify available workflows | `hardwhere profiles --json` |
| Inspect local hardware | `hardwhere discover --json` lists USB candidates and target IDs. `hardwhere doctor --board <id> --json` inspects tooling and applicable driver evidence. Match the candidate to the physical model. |
| Install dependencies | `hardwhere install --board <id> --apply` installs a board core. Add `--version` to pin a core, `--library "<name>"` to install a library, or `--core` when installing the core and libraries together. |
| Build firmware | `hardwhere build --board <id> --sketch <dir> --output <new-dir>` writes the artifact and a manifest with the board profile and file hashes. |
| Upload firmware | `hardwhere flash --board <id> --target <target-id> --artifact <dir> --apply` checks the manifest and resolves the device again before invoking the vendor uploader. |
| Check behavior | `monitor` captures bounded serial output. `verify` additionally requires a complete line to match `--expect <regex>`. Both take `--board`, `--target`, and optional `--baud` and `--seconds`. |
| Document and resume | `wiring <file.json>` renders a table and Mermaid diagram. `context save <file.json>` and `context show` work with the local `.hardwhere/context.json` checkpoint. |
| Use a Pi through SSH | `ssh config`, `ssh probe`, `ssh onboard` and `ssh run` use a selected OpenSSH alias and a verified host key. See the [Pi example](../examples/pi-lan/README.md). |

## Windows CP210x driver

For an ESP32 with the supported CP210x bridge and PnP problem code 28, download and extract the official [Silicon Labs driver package](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers). In an Administrator terminal, replace `PATH_TO_INF` with the path to `silabser.inf`.

```sh
hardwhere install --board esp32-devkitc-v4 --driver-inf "PATH_TO_INF" --apply
```

The CLI checks that Windows reports the bridge ready and exposes a matching serial port after installation. On Linux, follow the USB permission instructions for your board and its vendor tools.
