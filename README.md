# Qubitcoin Mainnet Node & Miner Kit

**Independent community kit · 0.1.0 · Qubitcoin MAINNET / QHash**

Choose **Miner only**, **Node only**, or **Node + Miner** from one menu.
The GPU miner uses a Qubitcoin pool. The optional node independently verifies the
blockchain; pool mining works independently of that node and its synchronization.

Every download, source build and start is an explicit choice. Existing nodes and
Testnet installations are never selected. The optional node has no wallet.

## Start here

1. Download and extract this repository's source ZIP into a new folder.
2. Install **64-bit Python 3.10 or newer** from [python.org](https://www.python.org/downloads/)
   if you do not already have it. No extra Python packages are needed.
3. On **Windows**, double-click **START.cmd**. On **native Linux**, run
   `bash start.sh` inside the extracted folder. Windows users should run this
   kit directly in Windows, outside their Testnet WSL terminal.
4. Choose 1: Miner only, 2: Node only, or 3: Node + Miner. Follow the numbered menu. The complete illustrated browser guide is
   **[OPEN-GUIDE.html](OPEN-GUIDE.html)**, which also opens without Python.

## Miner setup: six short steps

1. **Menu 1 — Get / verify miner.** Choose `D`, review the original release,
   then type `DOWNLOAD`. The kit downloads the pinned original archive, checks
   SHA-256 and installs only its executable. It does not run it. Alternatively,
   choose `I` to import the exact original archive you downloaded yourself.
2. **Menu 3 — List GPU IDs.** Type `LIST` to run the verified miner's device
   inventory only. Note the ID of the graphics card you want to use.
3. **Menu 2 — Wallet, pool & GPU settings.** Choose a pool and paste a public
   **Qubitcoin MAINNET receiving address from a wallet you control**. Keep the
   neutral worker name `rig01` or choose your own label. Enter the GPU ID and
   start with **1 mining thread per GPU**, automatic intensity, 75/60 C
   pause/resume thresholds. Type `QUBITCOIN` after reviewing the summary.
4. **Menu 4 — Preview / check.** Check the full payout address, QHash algorithm,
   pool, GPU IDs and settings. No pool connection or mining occurs in this step.
5. **Menu 5 — Start mining.** Review again and type **`START QTC`**. Keep the kit
   window open. Menu 7 shows the miner's output: check for accepted shares and
   look up your public address on the selected pool's own dashboard.
6. **Menu 6 — Stop kit miner.** Type `STOP`. This stops only the exact child
   process started by this kit window. `Q` asks to stop it before closing.

An open process, a displayed rate or a valid address does not prove accepted work
or a payout. The kit does not calculate or promise earnings.

## Optional node

Choose **Node only** or **Node + Miner**, then **9: Prepare optional node**.
Windows uses a separate Ubuntu WSL distribution named **QTC-Mainnet-Kit**;
native Ubuntu uses a dedicated user directory. See **NODE-GUIDE.md**.

The helper fetches pinned Qubitcoin source and applies the community CPU-validation
patch already used by the community Testnet kit. It builds without wallet or GUI,
so validation needs no CUDA. This is a community build, not an official signed binary.
Build tools require sudo after an explicit BUILD MAINNET NODE confirmation.
No service, autostart or firewall rule is created. Preparing starts nothing.

After preparation, choose Check, then Start and confirm START NODE or START BOTH.
The node uses its own pruned chain directory, localhost RPC and outbound peers.
Pruning targets 2048 MiB of block files, plus chainstate/index/build overhead.
Initial synchronization still downloads and verifies history and can take
substantial time, CPU, disk and network traffic.

A node alone earns no mining rewards and does not increase GPU mining speed.
Node + Miner uses a pool, not local solo mining. Stop requests graceful shutdown
of only the kit-owned components; no writing RPC or forced node kill is used.

## Change mining threads, GPU selection or pool later

1. Stop this kit's miner with **6 → STOP**.
2. Choose **2**. Press Enter to keep each current value; change only the field
   you want. For example, set mining threads per GPU from `1` to `2`.
3. Review the summary and type **QUBITCOIN** to save. Previous settings are
   automatically backed up; saving does not start mining.
4. Choose **5 → START QTC** when you want to use the new settings.

**Worker name** is the pool label for your rig. **Mining threads per GPU** is
the number of GPU mining threads requested from WildRig. These are separate
from CPU Testnet worker counts. More threads are not a guaranteed improvement.
GPU temperature protection depends on the miner and working hardware sensors.

## Supported scope

| Item | Initial supported path |
| --- | --- |
| Operating system | Native x86-64 Windows or Linux, 64-bit Python 3.10+ |
| Hardware | QHash-capable AMD, NVIDIA or Intel GPU supported by the original miner and installed driver |
| Mining engine | Original **WildRig Multi 0.52.1**, QHash developer fee **2%** |
| Pools | HeroMiners Germany (TLS), VeinPool PPLNS (TLS), LuckyPool example endpoint (plain TCP) |
| Node | Optional source build: native Ubuntu 24.04/26.04 or a separate Windows WSL environment |
| Excluded from this version | CPU mining, local solo mining, deqode, dual mining, macOS, ARM and WSL GPU mining |

Pool identity and endpoint sources were reviewed on **10 November 2026**.
TLS encrypts the pool connection; it does not establish provider solvency,
availability or payout reliability. Review the provider's current fees and
terms before starting. Pool and miner fees are separate.

## Address and privacy checks

The kit accepts mainnet Base58Check and Bech32/Bech32m address encodings. It
rejects detected testnet encodings, invalid checksums and private-key formats.
Qubitcoin uses Bitcoin-style mainnet encodings: a valid address alone cannot
distinguish a Bitcoin wallet from a Qubitcoin wallet or establish ownership.
Verify the chain in your Qubitcoin wallet before confirming.

Never enter a seed phrase, private key, wallet password or RPC credentials.
The pool sees your connection IP, public payout address and worker label during
mining. The kit has no analytics or Telegram integration. Miner output can
contain public account details; the menu masks your configured payout address
in its log preview. Inspect raw logs before sharing them.

Runtime files are stored outside the downloaded source:

- Windows: `%LOCALAPPDATA%\QTCCommunity\MainnetKit`
- Linux: `~/.local/share/qtc-mainnet-kit`

`settings.json` contains the public payout address and mining settings.
`downloads/` retains the checksum-verified vendor archive, `vendor/` contains
the miner executable, `backups/` holds prior settings and `miner.log` holds
miner output. Windows uses the user profile's existing access permissions;
Linux files are created with restrictive modes. No wallet is created or stored. Optional node data stays under ~/.local/share/qtc-mainnet-node inside its Ubuntu environment. Optional node data stays under ~/.local/share/qtc-mainnet-node inside its Ubuntu environment.

## Updates and recovery

Replace only this kit's source folder with a newer reviewed source ZIP, then
open the new START.cmd/start.sh. Runtime settings remain in your user profile.
A new pinned miner version would require a separate explicit download/import.
The kit does not silently follow the vendor's latest version.

Use **8** to preview a previous settings backup, then type `RESTORE`. Current
settings are backed up first. Restoring does not start mining. To uninstall,
stop this kit and remove its source folder; you can keep its runtime folder
for recovery. No service needs removing. Keep optional node data for later synchronization; see NODE-GUIDE.md before removing files.

## If something does not work

- **Python is missing:** install 64-bit Python from the original site, reopen
  START.cmd, or use `py -3 mainnet_kit.py` from this kit's folder.
- **Unsupported platform / WSL:** use native Windows or native x86-64 Linux.
  Do not move or reinstall your existing Testnet node.
- **Checksum mismatch:** stop and get the exact pinned archive from the original
  release. A different version is intentionally rejected.
- **Security software blocks the miner:** stop and review the official source
  and the security product's findings. This kit does not turn off protection,
  create exclusions or ask for administrator rights.
- **No supported GPU / driver error:** check menu 3 and the original miner's
  support list. This kit does not install drivers or change GPU clocks.
- **Rejected shares / no payout:** stop and check address, QHash pool endpoint,
  GPU support and the pool's own help. Do not substitute a Quantus endpoint.
- **Another kit window is open:** use or close that window first. The kit
  deliberately prevents simultaneous sessions for the same runtime folder.

## Sources and verification

- [Original miner and QHash support/fees](https://github.com/andru-kun/wildrig-multi)
- [Pinned release 0.52.1](https://github.com/andru-kun/wildrig-multi/releases/tag/0.52.1)
- [HeroMiners Qubitcoin guide](https://qubitcoin.herominers.com/how-to-mine-qubitcoin-qtc/)
- [VeinPool Qubitcoin guide](https://veinpool.fr/en/coin/qubit)
- [LuckyPool Qubitcoin](https://qtc.luckypool.io/) and the pinned original
  archive's `start-Qubitcoin-luckypool.io` example (endpoint reference only;
  its third-party payout address and launch script are never installed).
- [Qubitcoin mainnet address parameters](https://github.com/super-quantum/qubitcoin/blob/master/src/kernel/chainparams.cpp)
- [BIP 350 reference address vectors](https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki)

Exact vendor archive SHA-256 values and review scope are in
[SOURCES.json](SOURCES.json). Revalidate endpoints, terms and supported hardware
when updating. The wrapper is MIT-licensed; the proprietary vendor software
remains under its own terms and is not redistributed in the kit.

## Developer checks

```text
python -m unittest discover -p "test_*.py" -v
python verify_source.py
python mainnet_kit.py --check
```

Tests use temporary directories, public reference address vectors and harmless
local Python child processes. They never execute a real miner or connect to a
pool/node. `--check` is read-only and does not download or execute mining software;
it requires an existing local setup. Missing settings are reported without
creating them. The GitHub workflow repeats the offline checks on Windows/Linux.

## Validation scope

Offline checks cover the three modes, addresses, archive verification, settings
backups, isolated node arguments, read-only RPC allowlisting, Qubitcoin mainnet
genesis identity and process ownership/shutdown. Original miner archives were
downloaded and matched to pinned SHA-256 values. No real miner, node or WSL
environment was started by the tests.

Fresh node compilation, mainnet synchronization, GPU driver compatibility,
accepted pool shares and payouts remain separate practical checks.
No performance or earnings claim is made.
