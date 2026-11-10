"""Isolated optional Qubitcoin mainnet node. Never attaches to existing nodes."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

NODE_REV = '6c4f95a4c9b8975526fc7cb2eb32c721ab178cde'
PATCH_SHA256 = '760cba89fd0dbe1d2072bd48b4f4210912eca8f9d6d2680ed428f654dd013e22'
GENESIS = '00000021cce0cd4553ffc5545f38c6ec2696783f87a1252818f07c52bf9b362b'
DISTRO = 'QTC-Mainnet-Kit'
RPC_PORT = 19542
P2P_PORT = 19543
READ_ONLY = frozenset({'getblockchaininfo', 'getnetworkinfo', 'getblockhash'})
BUNDLE = Path(__file__).resolve().parent


class NodeError(Exception):
    pass


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, name = tempfile.mkstemp(prefix='.qtc-node-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        Path(name).chmod(0o600)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def node_base():
    return Path.home() / '.local/share/qtc-mainnet-node'


class NodeRuntime:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder is not None else node_base()

    def verify(self):
        try:
            meta = json.loads((self.folder / 'build.json').read_text())
            if meta['source_commit'] != NODE_REV or meta['cpu_patch_sha256'] != PATCH_SHA256 or meta['network'] != 'Qubitcoin mainnet':
                raise NodeError('Node provenance differs from this kit. Nothing started.')
            for name in ['qubitcoind', 'qubitcoin-cli']:
                binary = self.folder / 'bin' / name
                if binary.is_symlink() or not binary.is_file() or sha(binary) != meta['binaries'][name]:
                    raise NodeError('Node executable missing or changed. Nothing started.')
            conf = self.folder / 'data/qubitcoin.conf'
            if conf.is_symlink() or conf.read_text() != 'chain=main\nserver=1\n':
                raise NodeError('Kit node configuration differs. Review it before continuing.')
            return meta
        except (OSError, ValueError, KeyError, TypeError):
            raise NodeError('Optional node is not prepared. Choose Prepare node first.') from None

    def args(self, executable):
        return [str(self.folder / 'bin' / executable), '-chain=main',
                '-datadir=' + str(self.folder / 'data'), '-conf=' + str(self.folder / 'data/qubitcoin.conf'),
                '-rpcport=' + str(RPC_PORT)]

    def command(self):
        self.verify()
        return self.args('qubitcoind') + ['-daemon=0', '-server=1', '-listen=0', '-discover=0',
                '-rpcbind=127.0.0.1', '-rpcallowip=127.0.0.1',
                '-port=' + str(P2P_PORT), '-addnode=54.158.147.24:42069',
                '-prune=2048', '-dbcache=256', '-printtoconsole=1']

    def rpc(self, method, params=()):
        if method not in READ_ONLY:
            raise NodeError('Only read-only node status calls are allowed.')
        self.verify()
        try:
            result = subprocess.run(self.args('qubitcoin-cli') + [method, *map(str, params)],
                                    capture_output=True, text=True, timeout=12, shell=False)
            if result.returncode:
                raise NodeError('Kit node is starting, synchronizing or not reachable yet.')
            return result.stdout.strip() if method == 'getblockhash' else json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise NodeError('Kit node status is unavailable; backend details suppressed.') from None

    def status(self):
        info = self.rpc('getblockchaininfo')
        if info.get('chain') != 'main' or self.rpc('getblockhash', [0]) != GENESIS:
            raise NodeError('Node identity is not the expected Qubitcoin mainnet.')
        net = self.rpc('getnetworkinfo')
        return {'network': 'Qubitcoin mainnet', 'blocks': info['blocks'], 'headers': info['headers'],
                'synchronized': info['blocks'] == info['headers'] and info['initialblockdownload'] is False,
                'peers': net.get('connections', 0), 'pruned': info.get('pruned', False),
                'wallet_enabled': False, 'rpc_scope': 'localhost only'}

    def stop_request(self, session):
        if not re.fullmatch(r'[a-f0-9]{32}', session):
            raise NodeError('Invalid kit session identifier.')
        try:
            current = json.loads((self.folder / 'session.json').read_text())
        except FileNotFoundError:
            self.verify()
            # A close immediately after Start can precede supervisor readiness.
            # Its fresh session request must survive until the supervisor sees it.
            write_json(self.folder / ('stop-' + session + '.json'), {'session': session})
            return True
        except (OSError, ValueError):
            return False
        if current.get('session') != session:
            raise NodeError('This window does not own the running kit node session.')
        write_json(self.folder / ('stop-' + session + '.json'), {'session': session})
        return True

    def supervise(self, session, popen=None):
        if not re.fullmatch(r'[a-f0-9]{32}', session):
            raise NodeError('Invalid kit session identifier.')
        command = self.command()
        import fcntl
        with (self.folder / 'node.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise NodeError('Another kit node session is already active.') from None
            with socket.socket() as sock:
                try:
                    sock.bind(('127.0.0.1', RPC_PORT))
                except OSError:
                    raise NodeError('The kit RPC port is already occupied. No existing process was stopped.') from None
            stop_file = self.folder / ('stop-' + session + '.json')
            previous_handlers = {}
            interrupted = [False]
            for sig in [signal.SIGINT, signal.SIGTERM]:
                previous_handlers[sig] = signal.signal(sig, lambda *_: interrupted.__setitem__(0, True))
            parent = os.getppid()
            child = None
            try:
                with (self.folder / 'node.log').open('ab') as log:
                    child = (popen or subprocess.Popen)(command, stdin=subprocess.DEVNULL, stdout=log,
                                                        stderr=subprocess.STDOUT, shell=False)
                    write_json(self.folder / 'session.json', {'session': session})
                    print('Qubitcoin mainnet node launched in its dedicated kit folder.', flush=True)
                    while child.poll() is None:
                        if interrupted[0] or stop_file.exists() or os.getppid() != parent:
                            child.send_signal(signal.SIGINT)
                            print('Waiting for this kit node to flush and exit safely.', flush=True)
                            # Never force-kill a node or use a writing RPC.
                            while child.poll() is None:
                                time.sleep(0.5)
                            break
                        time.sleep(0.5)
                    return child.returncode or 0
            finally:
                if child is not None and child.poll() is None:
                    child.send_signal(signal.SIGINT)
                    child.wait()
                for sig, handler in previous_handlers.items():
                    signal.signal(sig, handler)
                stop_file.unlink(missing_ok=True)
                session_file = self.folder / 'session.json'
                try:
                    if json.loads(session_file.read_text()).get('session') == session:
                        session_file.unlink()
                except (OSError, ValueError):
                    pass


class NodeController:
    """Host-side owner of one optional node session, including dedicated WSL."""
    def __init__(self, system, log_folder, bundle=None):
        self.system = system
        self.log_folder = Path(log_folder)
        self.bundle = Path(bundle) if bundle is not None else BUNDLE
        self.session = None
        self.process = None
        self.log_handle = None

    def wsl_bundle(self, file):
        path = str((self.bundle / file).resolve())
        if not re.match(r'^[A-Za-z]:[\\/]', path):
            raise NodeError('For Windows node support, extract the kit onto a local drive such as C:.')
        return '/mnt/' + path[0].lower() + '/' + path[3:].replace('\\', '/')

    def command(self, file, *args):
        if self.system == 'windows':
            raw = subprocess.run(['wsl.exe', '--list', '--quiet'], capture_output=True, timeout=12, shell=False)
            names = raw.stdout.decode('utf-16le' if b'\x00' in raw.stdout else 'utf8', errors='replace').lstrip('\ufeff').splitlines()
            if raw.returncode or DISTRO not in [n.strip() for n in names]:
                raise NodeError('Prepare a separate WSL distribution named QTC-Mainnet-Kit first. See the Node guide. Existing distributions are never selected automatically.')
            return ['wsl.exe', '--distribution', DISTRO, '--exec', 'python3', self.wsl_bundle(file), *args]
        return [sys.executable, str(self.bundle / file), *args]

    def prepare(self):
        result = subprocess.run(self.command('setup_node.py'), shell=False)
        if result.returncode:
            raise NodeError('Node preparation did not finish. Read the displayed build step; existing nodes were not addressed.')

    def check(self):
        self.call('check')

    def call(self, action, *args):
        try:
            options = {'capture_output': True, 'text': True, 'timeout': 45, 'shell': False}
            if self.system == 'windows':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(self.command('node_runner.py', action, *args), **options)
            if result.returncode:
                raise NodeError('Kit node check is unavailable. Prepare the optional node or inspect its own log.')
            return json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise NodeError('Kit node helper is unavailable. No other node was addressed.') from None

    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if self.running():
            raise NodeError('This kit node session is already running.')
        self.check()
        self.session = uuid.uuid4().hex
        self.log_folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.log_handle = (self.log_folder / 'node-session.log').open('ab')
        options = {'stdin': subprocess.DEVNULL, 'stdout': self.log_handle, 'stderr': subprocess.STDOUT, 'shell': False}
        if self.system == 'windows':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW
        else:
            options['start_new_session'] = True
        self.process = subprocess.Popen(self.command('node_runner.py', 'run', '--session', self.session), **options)
        return self.process.pid

    def status(self):
        if not self.running():
            return {'state': 'not running from this kit window'}
        return self.call('status')

    def stop(self):
        if self.running() and self.session:
            self.call('request-stop', '--session', self.session)
            try:
                self.process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                raise NodeError('The kit node is still completing its safe shutdown. Leave this window open; no forced termination was attempted.') from None
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
