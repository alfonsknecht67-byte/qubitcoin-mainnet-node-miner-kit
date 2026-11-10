#!/usr/bin/env python3
"""Independent Qubitcoin MAINNET GPU pool kit. Standard library only."""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import urllib.request
import zipfile
from node_support import NodeController, NodeError

VERSION = '0.1.0'
MINER_VERSION = '0.52.1'
BUNDLE = Path(__file__).resolve().parent
MAX_ARCHIVE = 40_000_000
MAX_EXPANDED = 150_000_000
BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
BECH32 = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
RELEASE_ROOT = 'https://github.com/andru-kun/wildrig-multi/releases/download/0.52.1/'
RELEASES = {
    'windows': {'name': 'wildrig-multi-windows-0.52.1.zip',
                'sha256': '60f015dc1eeb20aafe43bbedaa51675063f497585fc881fc5ca5eb18a29f17e6',
                'binary': 'wildrig.exe'},
    'linux': {'name': 'wildrig-multi-linux-0.52.1.tar.gz',
              'sha256': '33587b9968b1d631b1574db8ea9c5cc50ef966e653fec4bcbb3001a6ad9dfdc0',
              'binary': 'wildrig-multi'},
}
POOLS = {
    'herominers-de': {'name': 'HeroMiners / Germany', 'url': 'stratum+ssl://de.qubitcoin.herominers.com:1195',
                       'terms': 'https://qubitcoin.herominers.com/how-to-mine-qubitcoin-qtc/',
                       'fees': 'Pool: provider reports 0%; check current terms. Miner: 2%.'},
    'veinpool': {'name': 'VeinPool / Europe', 'url': 'stratum+ssl://veinpool.fr:13210',
                 'terms': 'https://veinpool.fr/en/coin/qubit',
                 'fees': 'Pool: provider reports 1% PPLNS; check current terms. Miner: 2%.'},
    'luckypool': {'name': 'LuckyPool / published miner example', 'url': 'stratum+tcp://ru.luckypool.io:8611',
                  'terms': 'https://qtc.luckypool.io/',
                  'fees': 'Pool: provider reports 1% PPLNS; check current terms. Miner: 2%. TCP is unencrypted.'},
}
DEFAULTS = {'schema': 1, 'network': 'qubitcoin-mainnet', 'pool': 'herominers-de',
            'address': '', 'worker': 'rig01', 'gpu_ids': [0], 'gpu_threads': 1,
            'gpu_intensity': None, 'temperature_limit': 75, 'temperature_resume': 60}


class KitError(Exception):
    """An actionable, credential-free error for the user."""


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate_address(value):
    """Validate QTC mainnet encoding, not ownership or which chain a wallet uses."""
    if not isinstance(value, str) or value != value.strip() or not 14 <= len(value) <= 90:
        raise KitError('Enter one public Qubitcoin MAINNET receiving address, without spaces.')
    if value.lower().startswith('bc1'):
        if value.lower() != value and value.upper() != value:
            raise KitError('Mixed-case receiving address; copy it again from your QTC wallet.')
        lower = value.lower()
        try:
            data = [BECH32.index(c) for c in lower[3:]]
        except ValueError:
            raise KitError('Invalid receiving-address characters.') from None
        if len(data) < 7 or data[0] > 16:
            raise KitError('Invalid witness receiving address.')
        chk = 1
        for v in [3, 3, 0, 2, 3] + data:  # hrp_expand('bc')
            top, chk = chk >> 25, ((chk & 0x1ffffff) << 5) ^ v
            for i, g in enumerate((0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)):
                if top >> i & 1:
                    chk ^= g
        if chk != (1 if data[0] == 0 else 0x2bc830a3):
            raise KitError('Receiving-address checksum failed; copy it again from your QTC wallet.')
        acc = bits = 0
        program = []
        for v in data[1:-6]:
            acc = (acc << 5) | v
            bits += 5
            while bits >= 8:
                bits -= 8
                program.append((acc >> bits) & 255)
        if bits >= 5 or ((acc << (8 - bits)) & 255) or not 2 <= len(program) <= 40:
            raise KitError('Invalid witness-program padding or length.')
        if data[0] == 0 and len(program) not in (20, 32):
            raise KitError('Invalid version-0 receiving address.')
        return lower
    try:
        number = 0
        for char in value:
            number = number * 58 + BASE58.index(char)
        raw = b'\0' * (len(value) - len(value.lstrip('1'))) + number.to_bytes((number.bit_length() + 7) // 8, 'big')
    except (ValueError, OverflowError):
        raise KitError('Use a public Qubitcoin mainnet address, not a key, seed or testnet address.') from None
    if len(raw) != 25 or raw[0] not in (0, 5) or hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] != raw[-4:]:
        raise KitError('Mainnet address version or checksum failed. Never enter a private key or seed.')
    return value


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise KitError('Settings have an unsupported format. Restore a kit backup or run setup again.')
    if type(value['schema']) is not int or value['schema'] != 1 or value['network'] != 'qubitcoin-mainnet':
        raise KitError('These settings do not describe Qubitcoin MAINNET.')
    if value['pool'] not in POOLS or not isinstance(value['worker'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,23}', value['worker']):
        raise KitError('Choose a listed Qubitcoin pool and a 1-24 character worker name: letters, numbers, _ or -.')
    result = dict(value)
    result['address'] = validate_address(value['address'])
    ids = value['gpu_ids']
    if not isinstance(ids, list) or not ids or len(ids) > 32 or len(set(ids)) != len(ids) or any(type(i) is not int or not 0 <= i <= 31 for i in ids):
        raise KitError('GPU IDs must be distinct numbers from 0 to 31, for example 0 or 0,1.')
    if type(value['gpu_threads']) is not int or not 1 <= value['gpu_threads'] <= 4:
        raise KitError('Choose 1-4 mining threads per GPU; start with 1.')
    intensity = value['gpu_intensity']
    if intensity is not None and (type(intensity) is not int or not 1 <= intensity <= 32):
        raise KitError('GPU intensity must be auto or an integer from 1 to 32.')
    limit, resume = value['temperature_limit'], value['temperature_resume']
    if type(limit) is not int or type(resume) is not int or not 55 <= limit <= 85 or not 40 <= resume < limit:
        raise KitError('Temperature limit must be 55-85 C; resume must be at least 40 C and below the limit.')
    return result


def host_platform():
    if struct.calcsize('P') != 8 or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise KitError('Version 1 supports 64-bit x86 Windows and Linux. ARM is not supported.')
    if 'microsoft' in platform.release().lower():
        raise KitError('Open the kit in Windows, outside WSL. Your Testnet WSL installation is separate.')
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform.startswith('linux'):
        return 'linux'
    raise KitError('Version 1 supports native Windows or Linux; macOS is not supported.')


def default_state_dir():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'QTCCommunity/MainnetKit'
    return Path.home() / '.local/share/qtc-mainnet-kit'


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise KitError('Refusing to replace a symbolic-link settings file.')
    handle, name = tempfile.mkstemp(prefix='.qtc-', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def safe_text(text):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return ''.join(c for c in text if c in '\n\t' or c.isprintable())


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urlsplit(newurl)
        if p.scheme != 'https' or p.hostname not in {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com', 'github-releases.githubusercontent.com'}:
            raise KitError('The official download redirected outside the allowed HTTPS hosts.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextlib.contextmanager
def session_lock(folder):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / 'session.lock').open('a+b') as stream:
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        locked = False
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            yield
        except (BlockingIOError, PermissionError):
            raise KitError('Another Mainnet Kit window is open. Use or close that window first.') from None
        finally:
            if locked and os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


class Kit:
    def __init__(self, folder=None, system=None):
        self.folder = Path(folder) if folder is not None else default_state_dir()
        self.system = system
        self.process = None
        self.log_handle = None
        self.started = None
        self.mode = 'miner'
        self.node = None

    @property
    def settings_file(self):
        return self.folder / 'settings.json'

    def release(self):
        return RELEASES[self.system or host_platform()]

    def archive_path(self):
        return self.folder / 'downloads' / self.release()['name']

    def binary_path(self):
        return self.folder / 'vendor' / MINER_VERSION / self.release()['binary']

    def load(self):
        try:
            return validate_settings(json.loads(self.settings_file.read_text(encoding='utf8')))
        except FileNotFoundError:
            raise KitError('No mining settings yet. Choose 2: Set up wallet and pool.') from None
        except (ValueError, TypeError):
            raise KitError('Settings could not be read. Restore a backup or run setup again.') from None

    def running(self):
        return self.process is not None and self.process.poll() is None

    def save(self, settings):
        if self.running():
            raise KitError('Stop this kit miner before changing its settings.')
        checked = validate_settings(settings)
        backup = None
        if self.settings_file.is_file():
            backup = self.folder / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
            atomic_write(backup, self.settings_file.read_bytes())
        atomic_write(self.settings_file, (json.dumps(checked, indent=2) + '\n').encode())
        return backup

    def inspect_archive(self, path):
        path = Path(path)
        if not path.is_file() or path.stat().st_size > MAX_ARCHIVE or digest(path) != self.release()['sha256']:
            raise KitError('Archive checksum does not match the pinned official release. Nothing installed.')
        binary_name = self.release()['binary']
        if path.suffix == '.zip':
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 200 or sum(n.file_size for n in entries) > MAX_EXPANDED:
                    raise KitError('Archive size limits exceeded.')
                for n in entries:
                    name = n.orig_filename
                    if '\x00' in name or name.startswith(('/', '\\')) or '\\' in name or ':' in name or '..' in Path(name).parts or stat.S_ISLNK(n.external_attr >> 16):
                        raise KitError('Unsafe archive member; nothing installed.')
                if sum(n.filename == binary_name for n in entries) != 1:
                    raise KitError('Expected miner executable missing or duplicated.')
                binary = archive.read(binary_name)
        else:
            with tarfile.open(path, 'r:gz') as archive:
                entries = archive.getmembers()
                if len(entries) > 200 or sum(n.size for n in entries) > MAX_EXPANDED:
                    raise KitError('Archive size limits exceeded.')
                for n in entries:
                    if n.name.startswith(('/', '\\')) or '\\' in n.name or ':' in n.name or '..' in Path(n.name).parts or not (n.isfile() or n.isdir()):
                        raise KitError('Unsafe archive member; nothing installed.')
                if sum(n.name == binary_name for n in entries) != 1:
                    raise KitError('Expected miner executable missing or duplicated.')
                binary = archive.extractfile(binary_name).read()
        if len(binary) < 1000:
            raise KitError('Miner executable is unexpectedly small.')
        return binary

    def install_archive(self, path):
        if self.running():
            raise KitError('Stop this kit miner before installing its software.')
        binary = self.inspect_archive(path)
        archive = self.archive_path()
        if Path(path).resolve() != archive.resolve():
            atomic_write(archive, Path(path).read_bytes())
        target = self.binary_path()
        atomic_write(target, binary)
        target.chmod(0o700)
        # The vendor's example launch scripts contain third-party payout addresses.
        # Extract only the exact executable. Never install or run those scripts.
        return target

    def download(self):
        self.release()  # Reject unsupported platform before touching disk/network.
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix='.download-', dir=self.folder) as temp:
            path = Path(temp) / self.release()['name']
            opener = urllib.request.build_opener(OfficialRedirect())
            request = urllib.request.Request(RELEASE_ROOT + self.release()['name'], headers={'User-Agent':'QTC-Mainnet-Community-Kit/' + VERSION})
            try:
                with opener.open(request, timeout=40) as response, path.open('xb') as stream:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_ARCHIVE:
                            raise KitError('Download exceeded the archive size limit.')
                        stream.write(chunk)
            except OSError:
                raise KitError('Official download failed. Check your connection or use Import archive. No miner was started.') from None
            return self.install_archive(path)

    def verified_binary(self):
        target = self.binary_path()
        if target.is_symlink() or not target.is_file() or target.parent.is_symlink():
            raise KitError('Verified miner missing. Choose 1: Download or import the official miner.')
        expected = self.inspect_archive(self.archive_path())
        if hashlib.sha256(expected).hexdigest() != digest(target):
            raise KitError('Installed miner changed after verification. Reinstall the official archive; nothing started.')
        return target

    def command(self, settings=None, binary=None):
        s = validate_settings(settings if settings is not None else self.load())
        exe = Path(binary) if binary is not None else self.verified_binary()
        command = [str(exe), '--algo', 'qhash', '--url', POOLS[s['pool']]['url'],
                   '--user', s['address'] + '.' + s['worker'], '--pass', 'x',
                   '--gpu-list', ','.join(map(str, s['gpu_ids'])), '--gpu-threads', str(s['gpu_threads']),
                   '--gpu-temp-limit', str(s['temperature_limit']), '--gpu-temp-resume', str(s['temperature_resume']),
                   '--no-color', '--print-time', '10']
        if s['gpu_intensity'] is not None:
            command += ['--gpu-intensity', str(s['gpu_intensity'])]
        return command

    def start(self):
        if self.running():
            raise KitError('This kit miner is already running.')
        command = self.command()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        log = self.folder / 'miner.log'
        if log.is_symlink():
            raise KitError('Refusing a symbolic-link log file.')
        self.log_handle = log.open('ab')
        log.chmod(0o600)
        self.log_handle.write(('\n--- Kit mining session ' + datetime.now(timezone.utc).isoformat() + ' ---\n').encode())
        self.log_handle.flush()
        options = {'cwd': str(self.binary_path().parent), 'stdin': subprocess.DEVNULL,
                   'stdout': self.log_handle, 'stderr': subprocess.STDOUT, 'shell': False}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW
        try:
            self.process = subprocess.Popen(command, **options)
            self.started = time.time()
        except OSError:
            self.close_log()
            raise KitError('Miner could not start. Check drivers and security-software notifications. No protection was changed.') from None
        return self.process.pid

    def close_log(self):
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None

    def stop(self):
        # Only the exact child handle owned by this kit window. No PID file,
        # process-name kill, service manager, node CLI or RPC is ever used.
        if self.running():
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        self.close_log()

    def list_devices(self):
        binary = self.verified_binary()
        options = {'capture_output': True, 'text': True, 'errors': 'replace', 'timeout': 30,
                   'cwd': str(binary.parent), 'shell': False}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW
        try:
            result = subprocess.run([str(binary), '--print-devices', '--no-color'], **options)
        except (OSError, subprocess.TimeoutExpired):
            raise KitError('GPU inventory failed. Check your GPU driver; no mining was requested.') from None
        return safe_text(result.stdout + result.stderr)[-16000:]

    def logs(self):
        log = self.folder / 'miner.log'
        if not log.is_file():
            return 'No miner log yet.'
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 16000))
            text = stream.read().decode('utf8', 'replace')
        try:
            text = text.replace(self.load()['address'], '[QTC payout address]')
        except KitError:
            pass
        return safe_text('\n'.join(text.splitlines()[-24:]))

    def backups(self):
        folder = self.folder / 'backups'
        return sorted(p for p in folder.glob('*.json') if p.is_file() and not p.is_symlink())


def ask(prompt, default=None):
    text = input(prompt + (f' [{default}]' if default is not None else '') + ': ').strip()
    return text if text else default


def confirm(word, prompt):
    return input(prompt + f' Type {word}: ').strip() == word


def setup(kit):
    if kit.running():
        raise KitError('Stop this kit miner before changing its settings.')
    try:
        old = kit.load()
    except KitError:
        old = dict(DEFAULTS)
    print('\nQubitcoin MAINNET / QHash. You need a receiving address from your Qubitcoin wallet.')
    print('No seed, private key, exchange password or node credentials are needed.')
    ids = list(POOLS)
    for i, key in enumerate(ids, 1):
        print(f"  {i}. {POOLS[key]['name']}\n     {POOLS[key]['fees']}\n     {POOLS[key]['terms']}")
    choice = int(ask('Pool number', str(ids.index(old['pool']) + 1)))
    if not 1 <= choice <= len(ids):
        raise KitError('Choose a pool number from the list.')
    value = dict(old, pool=ids[choice - 1])
    value['address'] = ask('Public QTC mainnet receiving address', old['address'] or None)
    value['worker'] = ask('Worker name (a label for this rig)', old['worker'])
    print('GPU IDs come from menu 3. Start with one GPU. CPU Testnet worker settings are separate.')
    value['gpu_ids'] = [int(v.strip()) for v in ask('GPU IDs, separated by commas', ','.join(map(str, old['gpu_ids']))).split(',')]
    value['gpu_threads'] = int(ask('Mining threads per GPU (1-4)', str(old['gpu_threads'])))
    intensity = ask('GPU intensity: auto, or 1-32', 'auto' if old['gpu_intensity'] is None else str(old['gpu_intensity']))
    value['gpu_intensity'] = None if intensity == 'auto' else int(intensity)
    value['temperature_limit'] = int(ask('Pause mining at GPU temperature C', str(old['temperature_limit'])))
    value['temperature_resume'] = int(ask('Resume below GPU temperature C', str(old['temperature_resume'])))
    value = validate_settings(value)
    preview(value)
    print('QTC uses Bitcoin-style address encodings. A valid checksum cannot identify the wallet chain or prove ownership.')
    if confirm('QUBITCOIN', 'Confirm this address is from your Qubitcoin MAINNET wallet.'):
        backup = kit.save(value)
        print('Settings saved. Mining has not started.' + (' Previous settings backed up.' if backup else ''))


def preview(settings):
    s = validate_settings(settings)
    print('\nNetwork: Qubitcoin MAINNET | Algorithm: QHash | Mode: Pool mining')
    print('Pool:', POOLS[s['pool']]['name'], '|', POOLS[s['pool']]['url'])
    print('Payout address:', s['address'], '| Worker:', s['worker'])
    print('GPU IDs:', ','.join(map(str, s['gpu_ids'])), '| Threads per GPU:', s['gpu_threads'], '| Intensity:', s['gpu_intensity'] or 'auto')
    print(f"Temperature pause/resume: {s['temperature_limit']}/{s['temperature_resume']} C (miner sensor support required).")
    print(POOLS[s['pool']]['fees'])


def choose_mode(kit):
    print('\nHOW WOULD YOU LIKE TO PARTICIPATE?')
    print('[1] Miner only      GPU pool mining; no local node required')
    print('[2] Node only       Independently verify the Qubitcoin blockchain')
    print('[3] Node + Miner    Independent node plus GPU pool mining')
    print('[Q] Quit')
    choices = {'1': 'miner', '2': 'node', '3': 'both'}
    while True:
        choice = input('Choose 1, 2, 3 or Q: ').strip().lower()
        if choice == 'q':
            return False
        if choice in choices:
            kit.mode = choices[choice]
            return True
        print('Choose a listed option.')


def menu(kit):
    print('\nQUBITCOIN MAINNET NODE & MINER KIT / ' + VERSION)
    print('Independent community kit. Every download, build and start is your explicit choice.')
    while True:
        mining = kit.mode in ('miner', 'both')
        node = kit.mode in ('node', 'both')
        state = 'RUNNING (this kit window)' if kit.running() else 'STOPPED (this kit window)'
        if kit.process is not None and kit.process.poll() is not None:
            state += f' | Last miner exit: {kit.process.returncode}'
        print('\nMODE:', {'miner':'MINER ONLY', 'node':'NODE ONLY', 'both':'NODE + MINER'}[kit.mode])
        if mining:
            print('Miner:', state)
            print('[1] Get / verify miner  [2] Wallet, pool & GPU settings  [3] List GPU IDs')
        if node:
            print('Node:', 'RUNNING (kit session)' if kit.node and kit.node.running() else 'STOPPED (kit session)')
            print('[9] Prepare optional node (separate folder; source build)')
        print('[4] Preview / check     [5] Start selected components  [6] Stop selected components')
        print('[7] Status & log' + ('        [8] Restore miner settings' if mining else ''))
        print('[M] Change mode         [Q] Quit')
        choice = input('Choose: ').strip().lower()
        try:
            if choice == '1':
                if not mining:
                    raise KitError('Choose Miner or Node + Miner mode to prepare mining software.')
                print('WildRig Multi ' + MINER_VERSION + ' | QHash developer fee: 2%.')
                print('Original release and terms: https://github.com/andru-kun/wildrig-multi/releases/tag/' + MINER_VERSION)
                print('[D] Download from original GitHub release  [I] Import an already downloaded official archive')
                action = input('Choose D or I (Enter cancels): ').strip().lower()
                if action == 'd' and confirm('DOWNLOAD', 'Download and verify the official archive? It will not be executed.'):
                    kit.download()
                    print('Official archive and executable verified. No miner was started.')
                elif action == 'i':
                    path = ask('Full path of official ZIP / tar.gz archive')
                    if path and confirm('INSTALL', 'Verify and install this archive for the kit? It will not be executed.'):
                        kit.install_archive(Path(path.strip('"')))
                        print('Archive verified. Only the miner executable was installed; example scripts were excluded.')
            elif choice == '2':
                if not mining:
                    raise KitError('Node-only mode needs no payout address or mining settings.')
                setup(kit)
            elif choice == '3':
                if not mining:
                    raise KitError('GPU inventory belongs to Miner mode; a verification node does not need a GPU.')
                print('This runs only the verified miner GPU inventory, without a pool or mining command.')
                if confirm('LIST', 'Run GPU inventory?'):
                    print(kit.list_devices())
            elif choice == '4':
                if mining:
                    preview(kit.load())
                    kit.verified_binary()
                if node:
                    kit.node.check()
                    print('Node build checked. Wallet disabled; local RPC; separate pruned blockchain folder.')
                print('Selected setup checks passed. No mining or node was started.')
            elif choice == '5':
                if mining:
                    preview(kit.load())
                    kit.verified_binary()
                    print('The pool receives your public payout address, worker label and connection IP.')
                if node:
                    kit.node.check()
                    print('The separate node downloads and verifies the Qubitcoin mainnet. No wallet or solo mining.')
                    print('Pool mining uses the pool independently of this node and its synchronization.')
                print('Running components consume computing resources, electricity and network traffic.')
                word = 'START QTC' if kit.mode == 'miner' else 'START NODE' if kit.mode == 'node' else 'START BOTH'
                if confirm(word, 'Start the selected kit components?'):
                    if node:
                        kit.node.start()
                    if mining:
                        kit.start()
                    print('Selected components launched. Use 7 for status. A running miner does not prove accepted shares.')
            elif choice == '6':
                if (kit.running() or kit.node and kit.node.running()) and confirm('STOP', 'Stop only the components started by this kit window?'):
                    kit.stop()
                    if kit.node:
                        kit.node.stop()
                    print('Kit components stopped. Other applications and nodes were not addressed.')
                elif not kit.running() and not (kit.node and kit.node.running()):
                    print('This kit window has no running components.')
            elif choice == '7':
                if mining:
                    print(state + '\n' + kit.logs())
                if node:
                    print(json.dumps(kit.node.status(), indent=2))
            elif choice == '8':
                if not mining:
                    raise KitError('Node-only mode has no mining settings to restore.')
                backups = kit.backups()
                if not backups:
                    print('No previous settings backup yet.')
                    continue
                for i, p in enumerate(backups, 1):
                    print(f'{i}. {p.stem}')
                index = int(ask('Backup number to preview', str(len(backups))))
                if not 1 <= index <= len(backups):
                    raise KitError('Choose an existing backup number.')
                restored = validate_settings(json.loads(backups[index - 1].read_text(encoding='utf8')))
                preview(restored)
                if confirm('RESTORE', 'Restore these settings? Current settings will also be backed up.'):
                    kit.save(restored)
                    print('Settings restored. Mining has not started.')
            elif choice == '9':
                if not node:
                    raise KitError('Choose Node or Node + Miner mode to prepare the optional node.')
                kit.node.prepare()
            elif choice == 'm':
                if kit.running() or kit.node and kit.node.running():
                    raise KitError('Stop this kit\'s components before changing mode.')
                if not choose_mode(kit):
                    return
            elif choice == 'q':
                if kit.running() or kit.node and kit.node.running():
                    if not confirm('STOP', 'Closing this kit will safely stop its own components. Continue?'):
                        continue
                    kit.stop()
                    if kit.node:
                        kit.node.stop()
                return
            elif choice:
                print('Choose a listed number or Q.')
        except (KitError, NodeError, ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile, tarfile.TarError) as error:
            print('Check:', str(error) if isinstance(error, (KitError, NodeError)) else 'Could not complete this step. Check your entry, file permissions or archive and try again.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--check', action='store_true', help='Read-only check: no mining, downloads or pool connection.')
    args = parser.parse_args(argv)
    os.umask(0o077)
    kit = Kit()
    try:
        system = host_platform()
        kit.system = system
        kit.node = NodeController(system, kit.folder)
        if args.check:
            print('Platform:', system, '| Kit:', VERSION)
            preview(kit.load())
            kit.verified_binary()
            print('Read-only checks passed. No miner was executed or pool contacted.')
            return 0
        with session_lock(kit.folder):
            try:
                if choose_mode(kit):
                    menu(kit)
            finally:
                kit.stop()
                kit.node.stop()
        return 0
    except (EOFError, KeyboardInterrupt):
        print('\nClosing kit; stopping only its own child miner if running.')
        return 0
    except KitError as error:
        print('Check:', error)
        return 1
    finally:
        kit.stop()
        if kit.node:
            kit.node.stop()


if __name__ == '__main__':
    raise SystemExit(main())
