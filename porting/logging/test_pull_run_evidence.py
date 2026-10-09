#!/usr/bin/env python3
"""Run the real collector against isolated adb transport fixtures; never a phone."""
import os
from pathlib import Path
import subprocess
import struct
import tempfile

COLLECTOR = Path(__file__).with_name('pull-run-evidence.sh').resolve()
TEXT = (b'DIAG: Android capture ready; handing PID 1 to Android init\n'
        b'6,0,1000,-;Linux version fixture-kernel\n'
        b'6,1,2000,-;snapshot43 scm_raw_enter pid=7 fn=0x30000006\n')


def main():
    with tempfile.TemporaryDirectory(prefix='ack-collector-test-') as tmp:
        root = Path(tmp)
        raw = root / 'raw'
        with raw.open('wb') as out:
            out.write(TEXT)
            out.truncate(67108864)
            out.seek(62914560)
            # Correct magic/console, corrupt metadata: not a valid snapshot.
            out.write(struct.pack('<QQQQ8I', 0x52414d4f, 1, 1, 1000,
                                  4, 1048576, 0x86800000, 0, 0, 0, 0, 0))
            out.seek(62914560 + 4096)
            out.write(b'DBGC')
            out.seek(63967232)
            out.write(struct.pack('<QQQQ8I', 0x52414d4f, 2, 2, 2000,
                                  4096, 1048576, 0x86800000, 1, 0, 0, 0, 0))
            out.seek(63967232 + 4096)
            out.write(b'DBGC')
        sd = root / 'sd'
        adb = root / 'adb'
        adb.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
with open(os.environ['ACTIONS'], 'a') as out: out.write(repr(sys.argv)+'\\n')
if sys.argv[-1] == 'features':
    print('cmd\\nshell_v2\\nls_v2')
    sys.exit(0)
raw = 'dd if=/dev/block/by-name/logdump' in sys.argv[-1]
sys.stdout.buffer.write(Path(os.environ['RAW' if raw else 'SD']).read_bytes())
status = int(os.environ.get('RAW_EXIT' if raw else 'SD_EXIT', '0'))
if 'exec-out' in sys.argv:
    # Legacy exec loses remote exit status and merges dd stderr into payload.
    if raw: sys.stdout.buffer.write(b'64+0 records in\\n64+0 records out\\n')
    sys.exit(0)
assert 'shell' in sys.argv and '-T' in sys.argv
if raw: sys.stderr.write('64+0 records in\\n64+0 records out\\n')
sys.exit(status)
''')
        adb.chmod(0o755)
        env = dict(os.environ, PATH=str(root)+os.pathsep+os.environ['PATH'],
                   RAW=str(raw), SD=str(sd), ACTIONS=str(root / 'actions'), TMPDIR=str(root))
        index = 0

        def capture(sd_data, **changes):
            nonlocal index
            index += 1
            folder = root / str(index) / 'snapshot43'
            folder.mkdir(parents=True)
            (folder / 'boot.img').write_bytes(b'fixture image')
            sd.write_bytes(sd_data)
            result = subprocess.run(['bash', str(COLLECTOR), '1', 'boot.img'],
                                    cwd=folder, env=dict(env, **changes), capture_output=True)
            return folder, result

        folder, result = capture(TEXT)
        assert result.returncode == 0, result.stderr.decode()
        assert (folder / 'run1-logdump.bin').stat().st_size == 67108864
        assert (folder / 'run1-logdump.log').read_bytes() == TEXT
        assert (folder / 'run1-sd.log').read_bytes() == TEXT
        assert {p.name for p in folder.iterdir()} == {'boot.img', 'run1-logdump.bin', 'run1-logdump.log', 'run1-sd.log'}
        assert b'valid=False' in next(line for line in result.stdout.splitlines() if line.startswith(b'slot0:'))
        assert b'valid=True' in next(line for line in result.stdout.splitlines() if line.startswith(b'slot1:'))
        actions = (root / 'actions').read_bytes()
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        again = subprocess.run(['bash', str(COLLECTOR), '1', 'boot.img'], cwd=folder,
                               env=env, capture_output=True)
        assert again.returncode != 0
        assert (root / 'actions').read_bytes() == actions, 'overwrite refusal touched phone'
        assert before == {p.name: p.read_bytes() for p in folder.iterdir()}
        linked = root / 'linked' / 'snapshot43'
        linked.mkdir(parents=True)
        (linked / 'boot.img').write_bytes(b'fixture image')
        (linked / 'run1-sd.log').symlink_to('absent')
        again = subprocess.run(['bash', str(COLLECTOR), '1', 'boot.img'],
                               cwd=linked, env=env, capture_output=True)
        assert again.returncode != 0
        assert (root / 'actions').read_bytes() == actions, 'dangling output touched phone'
        assert (linked / 'run1-sd.log').is_symlink()
        for status in ('0', '1'):
            folder, result = capture(b'cat: /sdlog/ack-kmsg.log: No such file or directory\n', SD_EXIT=status)
            assert result.returncode == 0, result.stderr.decode()
            assert not list(folder.glob('run1-sd*'))
            assert (folder / 'run1-logdump.log').read_bytes() == TEXT
        folder, result = capture(TEXT, SD_EXIT='1')
        assert result.returncode == 0 and not list(folder.glob('run1-sd*'))
        with raw.open('ab') as out:
            out.write(b'x')
        folder, result = capture(TEXT)
        assert result.returncode == 0 and not (folder / 'run1-logdump.bin').exists()
        assert (folder / 'run1-sd-unverified.log').read_bytes() == TEXT
        with raw.open('r+b') as out:
            out.truncate(67108864)
        stale = TEXT.replace(b'0,1000', b'9,9000').replace(b'fixture-kernel', b'other-kernel')
        folder, result = capture(stale)
        assert result.returncode == 0
        assert (folder / 'run1-sd-unverified.log').read_bytes() == stale
        assert not (folder / 'run1-sd.log').exists()
        assert b'mismatch' in result.stdout.lower()
        raw.write_bytes(TEXT)
        folder, result = capture(TEXT)
        assert result.returncode == 0
        assert not (folder / 'run1-logdump.bin').exists()
        assert (folder / 'run1-sd-unverified.log').read_bytes() == TEXT
        folder, result = capture(b'cat: missing\n', RAW_EXIT='1', SD_EXIT='1')
        assert result.returncode != 0
        assert {p.name for p in folder.iterdir()} == {'boot.img'}
        print('collector trust-boundary checks passed: matching, invalid slots, cat errors, stale SD, short raw, both failed, overwrite refusal')


if __name__ == '__main__':
    main()
