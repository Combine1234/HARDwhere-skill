
# Reconnect to a Raspberry Pi 4B over LAN

Start with a Raspberry Pi 4 Model B running Linux with SSH enabled, connected to your LAN. Use the username created during OS setup. Find the hostname or address through the Pi console or your router's device list. The included script uses Python 3 on the Pi. [Raspberry Pi remote access](https://www.raspberrypi.com/documentation/computers/remote-access.html)

Use your existing alias or create one. Replace `raspberrypi.local` and `student` with your host and user. Omit `--apply` to preview the config entry.

```sh
hardwhere ssh config --alias workshop-pi --host raspberrypi.local --user student --apply
```

For the initial key enrollment, read the host fingerprint from a trusted Pi console. This command shows the default ED25519 host key fingerprint.

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

On your workstation run `ssh workshop-pi` and compare the corresponding fingerprint before accepting. Set up your user key and load it into your SSH agent if needed. The CLI uses non-interactive SSH with strict host verification.

```sh
hardwhere ssh probe --alias workshop-pi
hardwhere ssh onboard --alias workshop-pi --apply
hardwhere ssh run --alias workshop-pi --script examples/pi-lan/probe.py --expect "HARDWHERE_OK pi4" --apply
```

The test runs on the Pi and returns a marker after reading its model. Results verify the connection and remote Python execution. In a fresh chat invoke the generated `ssh-workshop-pi` skill or ask your agent to probe the existing alias. The example hostname and username are placeholders. The private skill and OpenSSH configuration live on your computer.
