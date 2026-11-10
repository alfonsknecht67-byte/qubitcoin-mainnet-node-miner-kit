#!/usr/bin/env python3
"""Explicit source build of a new, isolated CPU-validating mainnet node."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from node_support import BUNDLE, NODE_REV, PATCH_SHA256, NodeError, NodeRuntime, node_base, sha, write_json

CONFIGURE = ['./configure', '--without-gui', '--disable-wallet', '--disable-tests', '--disable-bench',
             '--disable-fuzz-binary', '--disable-shared', '--with-pic']

def main():
    if '--plan' in sys.argv:
        print(json.dumps({'source': 'https://github.com/super-quantum/qubitcoin', 'commit': NODE_REV,
                         'cpu_patch_sha256': PATCH_SHA256, 'configure': CONFIGURE,
                         'build_jobs': 2, 'starts_node': False, 'creates_wallet': False,
                         'manages_services': False, 'existing_installations_accessed': False}, indent=2))
        return 0
    os.umask(0o077)
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64') or os.geteuid() == 0:
        raise NodeError('Build inside Ubuntu as your normal user, not root. Do not use an existing Testnet installation.')
    release = dict(line.strip().split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') not in ('24.04', '26.04'):
        raise NodeError('This source-build helper targets Ubuntu 24.04 or 26.04 x86-64.')
    base = node_base()
    if base.exists():
        NodeRuntime(base).verify()
        print('The dedicated kit node is already prepared. Nothing changed; return to Check or Start.')
        return 0
    patch = BUNDLE / 'cpu-node.patch'
    if sha(patch) != PATCH_SHA256:
        raise NodeError('Community CPU-node patch checksum mismatch.')
    print('Prepare a separate Qubitcoin MAINNET verification node from pinned upstream source.')
    print('A community CPU-validation patch removes the CUDA requirement. This is not an official binary release.')
    print('The node has no wallet. It uses a separate data folder, local RPC, outbound peers and pruning.')
    print('Build tools require sudo. No services, autostart, existing nodes or miners are changed.')
    print('Source build and first synchronization can take substantial time, CPU, disk space and network traffic.')
    if input('Type BUILD MAINNET NODE to install build tools and compile: ').strip() != 'BUILD MAINNET NODE':
        print('Cancelled. Nothing prepared.')
        return 0
    subprocess.run(['sudo', 'apt-get', 'update'], check=True)
    subprocess.run(['sudo', 'apt-get', 'install', '-y', 'build-essential', 'autoconf', 'automake', 'libtool',
                    'pkg-config', 'git', 'python3', 'libevent-dev', 'libboost-dev', 'libssl-dev', 'libgmp-dev'], check=True)
    base.mkdir(parents=True, mode=0o700)
    source = base / 'source'
    with (base / 'build.log').open('ab') as log:
        def run(args, cwd=None):
            subprocess.run(args, cwd=cwd, check=True, stdout=log, stderr=subprocess.STDOUT, shell=False)
        print('[1/4] Fetching the exact Qubitcoin source revision...', flush=True)
        run(['git', 'init', '-q', str(source)])
        run(['git', '-C', str(source), 'remote', 'add', 'origin', 'https://github.com/super-quantum/qubitcoin.git'])
        run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', NODE_REV])
        run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'])
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != NODE_REV:
            raise NodeError('Unexpected node source revision; build stopped.')
        run(['git', '-C', str(source), 'apply', '--check', str(patch)])
        run(['git', '-C', str(source), 'apply', str(patch)])
        print('[2/4] Configuring a CPU-verifying node without GUI or wallet...', flush=True)
        run(['./autogen.sh'], source)
        run(CONFIGURE, source)
        print('[3/4] Compiling with two build jobs. See the dedicated build log for progress...', flush=True)
        run(['make', '-j2'], source)
    (base / 'bin').mkdir(mode=0o700)
    (base / 'data').mkdir(mode=0o700)
    hashes = {}
    for name in ['qubitcoind', 'qubitcoin-cli']:
        target = base / 'bin' / name
        shutil.copy2(source / 'src' / name, target)
        target.chmod(0o700)
        hashes[name] = sha(target)
    (base / 'data/qubitcoin.conf').write_text('chain=main\nserver=1\n')
    (base / 'data/qubitcoin.conf').chmod(0o600)
    write_json(base / 'build.json', {'network': 'Qubitcoin mainnet', 'source_commit': NODE_REV,
               'cpu_patch_sha256': PATCH_SHA256, 'binaries': hashes, 'wallet_enabled': False})
    print('[4/4] Node prepared. Nothing started. Return to the kit menu to start it explicitly.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (NodeError, OSError, subprocess.CalledProcessError) as error:
        print('Node preparation stopped:', str(error) if isinstance(error, NodeError) else 'Check the dedicated build log or package-manager output. Do not remove any existing wallet/node folder.')
        raise SystemExit(1)
