# Optional Qubitcoin mainnet node

## Choose your operating system

Use one source package: [Windows guide (10/11)](PLATFORMS.md#windows) or [Ubuntu/Linux guide](PLATFORMS.md#ubuntu-linux). Windows 11 is not a hard requirement. GPU drivers, Python and optional WSL/node requirements still apply.


The node is optional. Pool mining works without it. Node only verifies the chain;
Node + Miner runs the independent node alongside GPU pool mining.

## Windows: prepare a separate Ubuntu environment once

Use recent Microsoft Store WSL with support for named distributions. In PowerShell:

    wsl --install Ubuntu-24.04 --name QTC-Mainnet-Kit

Complete Ubuntu's first-start username/password prompt as a normal user.
The name must be exactly QTC-Mainnet-Kit. The kit never selects Qubitcoin-Ubuntu,
a Testnet environment or the default WSL distribution.

If --name is unavailable, follow Microsoft's current WSL setup instructions first.
Do not repurpose or stop an existing node distribution. If Windows needs a WSL
installation or reboot, choose a suitable time yourself before continuing.
The kit never installs, updates, restarts, terminates or unregisters WSL.

Return to Windows and open START.cmd from the extracted kit on a local drive.
GPU mining runs in Windows; only the optional node runs in its dedicated Ubuntu
environment. Paths with spaces are passed as arguments, without shell assembly.

## Native Ubuntu

Ubuntu 24.04 or 26.04 x86-64 is the source-build target. Run bash start.sh as
your ordinary user, not root.

## Prepare, start and stop

1. Choose Node only or Node + Miner, then 9: Prepare optional node.
2. Review the source-build summary and type BUILD MAINNET NODE. This authorizes
   build tools through apt in that Ubuntu environment, followed by compilation.
   Ubuntu may ask for your sudo password; the kit does not save it.
3. Wait for the build, which uses two compilation jobs. Source, build log,
   binaries and data stay under ~/.local/share/qtc-mainnet-node.
4. Choose 4 to check, then 5 to start. Confirm START NODE or START BOTH.
   Preparation itself starts nothing.
5. Choose 7 for blocks, headers, synchronization and peer counts. Qubitcoin mainnet
   identity is checked against the pinned genesis hash.
6. Choose 6 and type STOP before closing. Leave the window open while this kit
   node flushes its data. No writing RPC, process-name kill, global service
   control or WSL termination is used.

## Source, privacy and resource use

The official source is pinned to commit 6c4f95a4c9b8975526fc7cb2eb32c721ab178cde.
The included community CPU-validation patch removes the CUDA requirement.
This is a community source build, not an official signed binary release.
The build disables GUI and wallet: no addresses, keys, seed or transactions.
Pool payouts use your own external Qubitcoin wallet receiving address.

The node has a separate data folder, localhost-only RPC port 19542, outbound
peers and no inbound listening. No firewall/port mapping, service or autostart
is added. Its initial mainnet peer comes from the pinned official source.
An occupied RPC port causes startup to stop; no other process is removed.

Pruning targets 2048 MiB of block files. Chainstate, indexes, source and compiled
objects need additional disk space. Initial synchronization still downloads and
validates history and can take substantial time. A node alone earns no rewards
and does not improve miner hashrate. Node + Miner is pool mining, not local solo.

## Recovery

Keep the optional node folder to preserve synchronization. If a build fails,
inspect its own build.log. Ambiguous partial folders are refused rather than
overwritten. Do not remove or migrate another node, wallet or Testnet directory.

The kit controls only the node session it started. After an abnormal computer
or kit exit, inspect the dedicated environment before another start. Existing
locks or occupied ports are reported rather than forcibly cleared.

## Primary sources

- https://github.com/super-quantum/qubitcoin
- https://github.com/super-quantum/qubitcoin/blob/6c4f95a4c9b8975526fc7cb2eb32c721ab178cde/doc/build-unix.md
- https://learn.microsoft.com/windows/wsl/reference
- https://learn.microsoft.com/windows/wsl/build-custom-distro
