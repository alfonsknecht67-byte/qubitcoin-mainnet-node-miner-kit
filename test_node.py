"""Node add-on tests: fake binaries/RPC only; never start WSL or a real node."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import mainnet_kit as kit
import node_support as node
import setup_node


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = node.NodeRuntime(self.root)
        (self.root / 'bin').mkdir()
        (self.root / 'data').mkdir()
        hashes = {}
        for name in ['qubitcoind', 'qubitcoin-cli']:
            p = self.root / 'bin' / name
            p.write_bytes(b'NOT AN EXECUTABLE - OFFLINE TEST FIXTURE')
            hashes[name] = node.sha(p)
        node.write_json(self.root / 'build.json', {'network':'Qubitcoin mainnet', 'source_commit':node.NODE_REV,
                       'cpu_patch_sha256':node.PATCH_SHA256, 'binaries':hashes})
        (self.root / 'data/qubitcoin.conf').write_text('chain=main\nserver=1\n')

    def test_verified_provenance_and_isolated_command(self):
        self.runtime.verify()
        args = self.runtime.command()
        self.assertIn('-chain=main', args)
        self.assertIn('-rpcbind=127.0.0.1', args)
        self.assertIn('-rpcport=19542', args)
        self.assertIn('-prune=2048', args)
        self.assertIn('-listen=0', args)
        self.assertIn('-addnode=54.158.147.24:42069', args)
        self.assertFalse(any('-testnet' in a or 'systemctl' in a for a in args))
        self.assertTrue(any(a == '-datadir=' + str(self.root / 'data') for a in args))

    def test_changed_node_or_configuration_refused(self):
        (self.root / 'bin/qubitcoind').write_bytes(b'changed')
        with self.assertRaises(node.NodeError):
            self.runtime.verify()

    def test_config_change_refused(self):
        (self.root / 'data/qubitcoin.conf').write_text('testnet=1\n')
        with self.assertRaises(node.NodeError):
            self.runtime.verify()

    def test_writing_rpc_refused_before_subprocess(self):
        with patch('subprocess.run') as run:
            for method in ['stop', 'sendtoaddress', 'createwallet', 'getnewaddress', 'setnetworkactive', 'submitblock']:
                with self.subTest(method=method), self.assertRaises(node.NodeError):
                    self.runtime.rpc(method)
            run.assert_not_called()

    def test_status_checks_qtc_genesis_and_chain(self):
        info = {'chain':'main', 'blocks':100, 'headers':100, 'initialblockdownload':False, 'pruned':True}
        with patch.object(self.runtime, 'rpc', side_effect=[info, node.GENESIS, {'connections':3}]):
            status = self.runtime.status()
        self.assertTrue(status['synchronized'])
        self.assertFalse(status['wallet_enabled'])
        self.assertEqual(status['peers'], 3)
        with patch.object(self.runtime, 'rpc', side_effect=[info, '0' * 64]), self.assertRaises(node.NodeError):
            self.runtime.status()

    def test_stop_request_cannot_target_different_session(self):
        node.write_json(self.root / 'session.json', {'session':'a' * 32})
        with self.assertRaises(node.NodeError):
            self.runtime.stop_request('b' * 32)
        self.assertFalse((self.root / ('stop-' + 'b' * 32 + '.json')).exists())

    def test_stop_request_survives_early_startup(self):
        self.assertTrue(self.runtime.stop_request('a' * 32))
        self.assertTrue((self.root / ('stop-' + 'a' * 32 + '.json')).exists())

    def test_supervisor_signals_only_its_own_child_and_preserves_early_stop(self):
        session = 'a' * 32
        self.runtime.stop_request(session)
        child = Mock(returncode=0)
        child.poll.side_effect = [None, None, 0, 0]
        fake_fcntl = types.SimpleNamespace(LOCK_EX=1, LOCK_NB=2, flock=Mock())
        popen = Mock(return_value=child)
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        with patch.dict(sys.modules, fcntl=fake_fcntl), patch('socket.socket', return_value=sock), patch('signal.signal', return_value=None), patch('time.sleep'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.runtime.supervise(session, popen=popen), 0)
        child.send_signal.assert_called_once_with(signal.SIGINT)
        child.kill.assert_not_called()
        self.assertFalse((self.root / 'session.json').exists())
        self.assertFalse((self.root / ('stop-' + session + '.json')).exists())
        self.assertEqual(popen.call_args.kwargs['shell'], False)


class ControllerTests(unittest.TestCase):
    def test_windows_only_selects_dedicated_distribution(self):
        controller = node.NodeController('windows', Path('unused'), bundle=Path('C:/QTC Kit'))
        listing = ('Qubitcoin-Ubuntu\nQTC-Mainnet-Kit\nUbuntu\n').encode('utf-16le')
        with patch('subprocess.run', return_value=Mock(returncode=0, stdout=listing)), patch.object(controller, 'wsl_bundle', return_value='/mnt/c/QTC Kit/node_runner.py'):
            cmd = controller.command('node_runner.py', 'check')
        self.assertEqual(cmd[:5], ['wsl.exe','--distribution','QTC-Mainnet-Kit','--exec','python3'])
        self.assertNotIn('Qubitcoin-Ubuntu', cmd)
        self.assertTrue(cmd[5].startswith('/mnt/c/'))

    def test_windows_path_conversion_preserves_spaces_without_shell(self):
        controller = node.NodeController('windows', Path('unused'), bundle=Path('unused'))
        with patch.object(Path, 'resolve', return_value='D:\\Community Tools\\node_runner.py'):
            self.assertEqual(controller.wsl_bundle('node_runner.py'), '/mnt/d/Community Tools/node_runner.py')

    def test_missing_dedicated_distribution_never_falls_back(self):
        controller = node.NodeController('windows', Path('unused'))
        with patch('subprocess.run', return_value=Mock(returncode=0, stdout=b'Qubitcoin-Ubuntu\n')) as run:
            with self.assertRaises(node.NodeError):
                controller.command('node_runner.py', 'run')
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ['wsl.exe','--list','--quiet'])

    def test_stop_timeout_never_kills_node_or_wsl(self):
        controller = node.NodeController('linux', Path('unused'))
        controller.session = 'a' * 32
        controller.process = Mock()
        controller.process.poll.return_value = None
        controller.process.wait.side_effect = subprocess.TimeoutExpired('safe shutdown', 180)
        with patch.object(controller, 'call') as call, self.assertRaises(node.NodeError):
            controller.stop()
        call.assert_called_once_with('request-stop', '--session', 'a' * 32)
        controller.process.kill.assert_not_called()
        controller.process.terminate.assert_not_called()

    def test_never_stops_components_not_owned_by_this_window(self):
        controller = node.NodeController('linux', Path('unused'))
        with patch.object(controller, 'call') as call:
            controller.stop()
        call.assert_not_called()


class ModeTests(unittest.TestCase):
    def test_participation_choices_only_select_and_never_start(self):
        for choice, wanted in [('1','miner'), ('2','node'), ('3','both')]:
            app = kit.Kit(Path('unused'), system='windows')
            with patch('builtins.input', return_value=choice), patch('subprocess.Popen') as start, contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(kit.choose_mode(app))
            self.assertEqual(app.mode, wanted)
            start.assert_not_called()

    def test_node_only_never_needs_wallet_or_miner(self):
        app = kit.Kit(Path('unused'), system='linux')
        app.mode = 'node'
        app.node = Mock()
        app.node.running.return_value = False
        with patch.object(app, 'load') as load, patch.object(app, 'verified_binary') as binary, patch('builtins.input', side_effect=['4','5','no','q']), contextlib.redirect_stdout(io.StringIO()):
            kit.menu(app)
        load.assert_not_called()
        binary.assert_not_called()
        app.node.start.assert_not_called()

    def test_build_plan_is_read_only_and_walletless(self):
        with patch('sys.argv', ['setup_node.py','--plan']), patch('subprocess.run') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(setup_node.main(), 0)
        value = json.loads(output.getvalue())
        self.assertFalse(value['starts_node'])
        self.assertFalse(value['creates_wallet'])
        self.assertFalse(value['manages_services'])
        self.assertIn('--disable-wallet', value['configure'])
        run.assert_not_called()

if __name__ == '__main__':
    unittest.main()
