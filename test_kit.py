"""Offline tests. No real miner, pool, node or service is used."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import mainnet_kit as kit


def public_address(version=0):
    payload = bytes([version]) + b'\x11' * 20
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    number = int.from_bytes(raw, 'big')
    text = ''
    while number:
        number, index = divmod(number, 58)
        text = kit.BASE58[index] + text
    return '1' * (len(raw) - len(raw.lstrip(b'\0'))) + text


def settings(**overrides):
    return dict(kit.DEFAULTS, address=public_address(), **overrides)


class AddressTests(unittest.TestCase):
    def test_base58_mainnet_versions_and_checksum(self):
        for version in [0, 5]:
            address = public_address(version)
            self.assertEqual(kit.validate_address(address), address)
            with self.assertRaises(kit.KitError):
                kit.validate_address(address[:-1] + ('2' if address[-1] != '2' else '3'))

    def test_reject_testnet_private_key_and_seed(self):
        for address in [public_address(111), public_address(196), 'xprv' + 'a' * 107, 'K' + '1' * 51, 'word ' * 12, 'tb1qabc', '', ' 1abc']:
            with self.subTest(address_type=len(address)), self.assertRaises(kit.KitError):
                kit.validate_address(address)

    def test_official_bip350_valid_mainnet_vectors(self):
        # Public reference vectors, not kit payout defaults.
        for address in ['BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4',
                        'bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0',
                        'BC1SW50QGDZ25J', 'bc1zw508d6qejxtdg4y5r3zarvaryvaxxpcs']:
            self.assertEqual(kit.validate_address(address), address.lower())

    def test_official_bip350_invalid_vectors(self):
        for address in ['bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqh2y7hd',
                        'bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kemeawh', 'bc1pw5dgrnzv',
                        'BC1QR508D6QEJXTDG4Y5R3ZARVARYV98GJ9P', 'bc1gmk9yu',
                        'bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7v07qwwzcrf']:
            with self.subTest(length=len(address)), self.assertRaises(kit.KitError):
                kit.validate_address(address)

    def test_mixed_case_and_testnet_bech32_rejected(self):
        for address in ['bC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4', 'tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q0sl5k7']:
            with self.assertRaises(kit.KitError):
                kit.validate_address(address)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = kit.Kit(Path(self.temp.name) / 'state', system='windows')

    def test_settings_updates_back_up_and_restore(self):
        self.assertIsNone(self.app.save(settings()))
        saved = self.app.save(settings(gpu_threads=2))
        self.assertEqual(self.app.load()['gpu_threads'], 2)
        original = json.loads(saved.read_text())
        self.app.save(original)
        self.assertEqual(self.app.load()['gpu_threads'], 1)
        self.assertEqual(len(self.app.backups()), 2)

    def test_invalid_settings_do_not_replace_previous(self):
        self.app.save(settings())
        before = self.app.settings_file.read_bytes()
        bad = [dict(settings(), network='test'), settings(gpu_threads=0), settings(gpu_threads=True),
               settings(gpu_ids=[0, 0]), settings(gpu_ids=[]), settings(gpu_ids=[32]),
               settings(worker='rig; --algo quantus'), settings(temperature_limit=90),
               settings(temperature_resume=80), settings(gpu_intensity=33), settings(pool='quantus')]
        for value in bad:
            with self.subTest(field=value), self.assertRaises(kit.KitError):
                self.app.save(value)
            self.assertEqual(self.app.settings_file.read_bytes(), before)

    def test_settings_cannot_change_while_own_miner_running(self):
        self.app.process = Mock()
        self.app.process.poll.return_value = None
        with self.assertRaises(kit.KitError):
            self.app.save(settings())
        self.assertFalse(self.app.settings_file.exists())

    def test_check_is_read_only_and_never_starts_anything(self):
        with patch.object(kit, 'default_state_dir', return_value=self.app.folder), patch.object(kit, 'host_platform', return_value='windows'), patch('subprocess.Popen') as popen, patch('urllib.request.OpenerDirector.open') as network, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(kit.main(['--check']), 1)
        self.assertFalse(self.app.folder.exists())
        popen.assert_not_called()
        network.assert_not_called()

    def test_q_from_menu_does_not_start_miner(self):
        with patch('builtins.input', return_value='q'), patch('subprocess.Popen') as popen, contextlib.redirect_stdout(io.StringIO()):
            kit.menu(self.app)
        popen.assert_not_called()

    def test_start_requires_exact_confirmation(self):
        self.app.save(settings())
        with patch.object(self.app, 'verified_binary', return_value=Path('unused')), patch.object(self.app, 'start') as start, patch('builtins.input', side_effect=['5', 'yes', 'q']), contextlib.redirect_stdout(io.StringIO()):
            kit.menu(self.app)
        start.assert_not_called()

    def test_command_pins_mainnet_qhash_and_safe_flags(self):
        for pool in kit.POOLS:
            cmd = self.app.command(settings(pool=pool, gpu_ids=[0, 2], gpu_threads=2), binary=Path('miner with spaces.exe'))
            self.assertEqual(cmd[0], 'miner with spaces.exe')
            self.assertEqual(cmd[cmd.index('--algo') + 1], 'qhash')
            self.assertEqual(cmd[cmd.index('--gpu-list') + 1], '0,2')
            self.assertEqual(cmd[cmd.index('--gpu-threads') + 1], '2')
            self.assertNotIn('--api-port', cmd)
            self.assertFalse(any(word in ' '.join(cmd) for word in ['systemctl', 'qubitcoin-cli', 'deqode', '--execute', '--gpu-reset-oc']))

    def test_log_preview_masks_payout_and_terminal_controls(self):
        self.app.save(settings())
        (self.app.folder / 'miner.log').write_text('\x1b[31mwallet ' + public_address() + '\nAccepted share\x00')
        text = self.app.logs()
        self.assertNotIn(public_address(), text)
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\x00', text)
        self.assertIn('Accepted share', text)

    def test_process_stop_never_targets_unrelated_process(self):
        # Real harmless child processes test process ownership, not a real miner.
        survivor = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])
        self.addCleanup(lambda: survivor.poll() is None and survivor.terminate())
        self.addCleanup(lambda: survivor.poll() is None and survivor.wait(timeout=5))
        self.app.save(settings())
        self.app.binary_path().parent.mkdir(parents=True)
        with patch.object(self.app, 'command', return_value=[sys.executable, '-u', '-c', 'import time;print("kit test child",flush=True);time.sleep(30)']):
            self.app.start()
        self.assertTrue(self.app.running())
        self.app.stop()
        self.assertFalse(self.app.running())
        self.assertIsNone(survivor.poll())
        survivor.terminate()
        survivor.wait(timeout=5)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = kit.Kit(self.root / 'state', system='windows')
        self.archive = self.root / 'official-test.zip'
        self.binary = b'FAKE EXECUTABLE FOR ARCHIVE TESTS ONLY\0' * 100

    def prepare(self, extra=None):
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('wildrig.exe', self.binary)
            z.writestr('start.bat', 'foreign payout address; do not install')
            if extra:
                z.writestr(*extra)
        if extra and '\\' in extra[0]:
            # ZipInfo on Windows normalizes separators while writing; construct
            # the original raw member name to exercise the import boundary.
            self.archive.write_bytes(self.archive.read_bytes().replace(extra[0].replace('\\', '/').encode(), extra[0].encode()))
        self.release = dict(kit.RELEASES['windows'], sha256=kit.digest(self.archive))
        return patch.dict(kit.RELEASES, windows=self.release)

    def test_only_executable_installed_and_original_archive_retained(self):
        with self.prepare():
            path = self.app.install_archive(self.archive)
            self.assertEqual(path.read_bytes(), self.binary)
            self.assertFalse((path.parent / 'start.bat').exists())
            self.assertEqual(kit.digest(self.app.archive_path()), self.release['sha256'])
            self.assertEqual(self.app.verified_binary(), path)

    def test_wrong_archive_hash_writes_nothing(self):
        self.archive.write_bytes(b'bad archive')
        with self.assertRaises(kit.KitError):
            self.app.install_archive(self.archive)
        self.assertFalse(self.app.folder.exists())

    def test_tampered_installed_binary_rejected(self):
        with self.prepare():
            path = self.app.install_archive(self.archive)
            path.write_bytes(self.binary + b'changed')
            with self.assertRaises(kit.KitError):
                self.app.verified_binary()

    def test_unsafe_paths_rejected_even_in_checksum_matched_archive(self):
        for member in ['../escape.exe', '/absolute.exe', 'C:/evil.exe', 'folder\\evil.exe']:
            with self.subTest(member=member), self.prepare((member, b'bad')):
                with self.assertRaises(kit.KitError):
                    self.app.install_archive(self.archive)
                self.assertFalse(self.app.folder.exists())

    def test_symlinks_rejected(self):
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('wildrig.exe', self.binary)
            link = zipfile.ZipInfo('link')
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            z.writestr(link, '../elsewhere')
        with patch.dict(kit.RELEASES, windows=dict(kit.RELEASES['windows'], sha256=kit.digest(self.archive))), self.assertRaises(kit.KitError):
            self.app.inspect_archive(self.archive)

    def test_linux_tar_installs_only_binary(self):
        self.app.system = 'linux'
        archive = self.root / 'official-test.tar.gz'
        with tarfile.open(archive, 'w:gz') as t:
            for name, data in [('wildrig-multi', self.binary), ('start.sh', b'not installed')]:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                t.addfile(member, io.BytesIO(data))
        with patch.dict(kit.RELEASES, linux=dict(kit.RELEASES['linux'], sha256=kit.digest(archive))):
            path = self.app.install_archive(archive)
            self.assertEqual(path.read_bytes(), self.binary)
            self.assertFalse((path.parent / 'start.sh').exists())

    def test_redirects_require_original_download_hosts_and_https(self):
        handler = kit.OfficialRedirect()
        request = kit.urllib.request.Request('https://github.com/original')
        for url in ['http://github.com/downgrade', 'https://evil.invalid/miner.zip']:
            with self.assertRaises(kit.KitError):
                handler.redirect_request(request, None, 302, 'Found', {}, url)


if __name__ == '__main__':
    unittest.main()
