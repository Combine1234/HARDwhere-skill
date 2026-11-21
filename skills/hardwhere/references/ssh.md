
# Raspberry Pi and SSH

Reuse the user's existing OpenSSH alias when possible. Obtain the user-provided hostname or address, user name and port for a new alias. Run `hardwhere ssh config --alias <alias> --host <host> --user <user>` to show a stanza. Add `--apply` when the user wants it added to their config. Existing aliases can use the user's established jump host, key selection and agent.

For an unknown SSH host key, ask the user to obtain its fingerprint from a trusted console on the Pi, then compare it during their first OpenSSH connection. For a changed key, stop and check with the user whether the machine was reimaged or replaced. Resume after the verified key is in `known_hosts`. Keep private keys and passwords with the user and use their SSH agent or interactive terminal for login setup.

Use `hardwhere ssh probe --alias <alias>` for a read-only Linux and model check. For Pi 4B, `hardwhere ssh onboard --alias <alias> --apply` creates a private skill after the check. Use `--skills-dir` for another agent's private skill directory. Keep the skill outside a public project. It contains the alias and instructions to reuse the local SSH config. The same alias must exist on any other computer that uses it.

Review a test script before running it. Use `hardwhere ssh run --alias <alias> --script <file.py> --apply` to run it as the configured user with Python 3 over stdin. Add `--expect <regex>` for a full output line check. Record whether the Pi, an application, or a peripheral was actually verified. Use documented distro and device steps for user-authorized package setup, persistent deployment or alternate SBCs.
