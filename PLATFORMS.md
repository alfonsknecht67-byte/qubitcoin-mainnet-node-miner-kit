# Choose your platform: one Mainnet kit

Use one source ZIP. It contains START.cmd for Windows and start.sh for Linux.
The kit does not require Windows 11 specifically.

## Windows

Run the GPU pool miner directly in 64-bit Windows, with 64-bit Python 3.10+ and
a GPU/driver combination supported by the original miner. Windows 10 or Windows
11 must meet those software and driver requirements; the kit does not bypass
unsupported drivers or operating-system restrictions.

1. Extract the current source ZIP into a new folder on a local drive.
2. Install Python from https://www.python.org/downloads/ if needed.
3. Double-click START.cmd and choose Miner only, Node only or Node + Miner.
4. Follow the numbered setup, GPU inventory, configuration and explicit Start
   steps in [README.md](README.md).

### Optional node on Windows

Only the optional verification node uses Ubuntu through recent WSL2. Use a
separately named QTC-Mainnet-Kit distribution; never select an existing Testnet
or mainnet distribution. Ubuntu's WSL guide specifies Windows 10 21H2 or newer
or Windows 11. Named-distribution installation also requires a sufficiently
recent WSL version. Follow [NODE-GUIDE.md](NODE-GUIDE.md).

Windows 11 is not a substitute for these checks. If WSL lacks the required
features, stop at that step; the kit never shuts down or repurposes another
WSL environment.

## Ubuntu Linux

Use 64-bit x86-64 Linux with Python 3.10+ and a compatible GPU driver for mining.
The optional node source-build helper specifically targets native Ubuntu 24.04
or 26.04 and needs no Windows or WSL.

1. Extract the same source ZIP into a new folder.
2. Open a terminal in that folder and run:

    bash start.sh

3. Select your participation mode and follow the numbered menu.

GPU mining and the optional verification node are separate components. A local
node is not required for pool mining. Node-only operation needs no mining GPU
or payout address.

## Shared controls and limits

Both entry points use the same program files, configuration checks, backup
format and explicit start/stop controls. Do not install separate Windows 10
and Windows 11 copies. macOS, ARM and WSL GPU mining are outside this kit's
current paths.

These are platform prerequisites, not a certification of every Windows build,
GPU driver or a complete clean-machine installation. Practical node builds,
synchronization and accepted-share tests remain separate from automated checks.

Sources:
- https://documentation.ubuntu.com/wsl/latest/guides/install-ubuntu-wsl2/
- https://learn.microsoft.com/windows/wsl/install
- https://github.com/andru-kun/wildrig-multi
