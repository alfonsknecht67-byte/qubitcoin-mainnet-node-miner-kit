"""Verify canonical UTF-8/LF text sources; tolerate Git's documented CMD CRLF."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCLUDED = {'SHA256SUMS.txt', '__pycache__', '.git'}

def canonical(path):
    text = path.read_bytes().decode('utf8')
    return text.replace('\r\n', '\n').encode('utf8')

def check():
    expected = {}
    for line in (ROOT / 'SHA256SUMS.txt').read_text().splitlines():
        value, name = line.split('  ', 1)
        assert name not in expected and '..' not in Path(name).parts and not Path(name).is_absolute()
        expected[name] = value
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and not any(part in EXCLUDED for part in p.relative_to(ROOT).parts)}
    assert actual == set(expected), 'Unexpected or missing source-package file'
    for name, wanted in expected.items():
        data = canonical(ROOT / name)
        assert hashlib.sha256(data).hexdigest() == wanted, 'Checksum mismatch: ' + name
        if name.endswith('.py'):
            ast.parse(data.decode('utf8'))
    data = json.loads((ROOT / 'SOURCES.json').read_text())
    assert data['network'] == 'Qubitcoin mainnet' and not data['miner']['bundled_in_kit']
    assert not any(p.endswith(('.exe', '.dll', '.so', '.zip', '.tar.gz', '.log')) for p in actual)
    print('Verified', len(expected), 'canonical source files; no binaries, credentials or runtime data bundled.')

if __name__ == '__main__':
    check()
