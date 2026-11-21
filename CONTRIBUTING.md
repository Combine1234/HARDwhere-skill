
# Add a board

A board profile covers exact hardware and a documented vendor workflow. Start by recording the revision, visible markings, vendor schematic, firmware format, programming mode and host dependencies. USB IDs are identification hints. Confirm where they overlap with a bridge or bootloader used by other models.

For an Arduino-compatible board, add a `Profile` in [profiles.py](src/hardwhere/profiles.py) with a unique ID, official FQBN, official core index if needed, sources, and known USB identities. Reuse the existing Arduino compile and serial upload path if the package supports those commands. A different transport or artifact format needs implementation support for its capabilities. Advertise only the operations wired into the CLI. Avoid adding a generic shell string to board records.

Add fixtures for the identification and writer behavior specific to the board. Include absent and ambiguous targets, changes between application and bootloader mode, and any driver prerequisite. Add a compile-only job using the vendor's toolchain and a minimal sketch if possible. Run `python -m unittest discover -s tests -v` after installing the local package.

## Record a bench run

Submit one row per operation actually checked. Useful fields are board and PCB revision, host OS and architecture, programmer or driver version, core and library versions, operation, result, and a short redacted evidence excerpt. Include the physical target confirmation method and expected observed result for a flash test. A physical verification entry should include how a change at the sensor or output changed what you observed.

For example, a fixture that simulates two matching USB devices establishes that target selection rejects ambiguity under these inputs. A vendor build establishes that the sketch compiles. A physical BME280 run can establish that the board flashed, booted and reported readings that respond to warming the sensor. Keep credentials, private hostname details and serial numbers out of public contributions.
