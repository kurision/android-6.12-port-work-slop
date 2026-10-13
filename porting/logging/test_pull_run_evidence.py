#!/usr/bin/env python3
"""Run the real collector against isolated adb transport fixtures; never a phone."""
import json
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import zlib

COLLECTOR = Path(__file__).with_name('pull-run-evidence.sh').resolve()
TEXT = (b'DIAG: Android capture ready; handing PID 1 to Android init\n'
        b'6,0,1000,-;Linux version fixture-kernel\n'
        b'6,1,2000,-;snapshot43 scm_raw_enter pid=7 fn=0x30000006\n')
CONSOLE = b'[0.000000] Linux version snapshot-console-fixture\n'
RECOVERED_CONSOLE = 'run1-ramoops-slot1-seq2-ns2000-snapshot-console.log'
TAIL = b'6,42,3000,-;periodic printk fixture: Panic#1 Part1 ACKRESET1 text is not an event\n'
RECOVERED_TAIL = 'run1-printk-tail-slot0-seq1-ns3000-periodic-printk.log'


def tail_header(slot, seq, timestamp, payload):
    fields = [0x314c4941544b4341, seq, seq, timestamp, 4096,
              len(payload), 0, slot, 1, zlib.crc32(payload), 0, 0]
    fields[10] = zlib.crc32(struct.pack('<QQQQ8I', *fields))
    return struct.pack('<QQQQ8I', *fields)


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
            for base in (62914560, 63967232):
                for zone in range(119):
                    out.seek(base + 4096 + zone * 4096)
                    out.write(struct.pack('<III', 0x43474244, 0, 0))
                out.seek(base + 4096 + 0x77000)
                out.write(struct.pack('<III', 0x43474244, len(CONSOLE), len(CONSOLE)))
                out.write(CONSOLE)
            out.seek(0x3e02000)
            out.write(tail_header(0, 1, 3000, TAIL))
            out.seek(0x3e02000 + 4096)
            out.write(TAIL)
            out.seek(0x3e22000)
            out.write(tail_header(1, 2, 4000, TAIL))
            out.seek(0x3e22000 + 4096)
            out.write(b'X' + TAIL[1:])  # Valid header CRC, invalid payload CRC.
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
        assert (folder / RECOVERED_CONSOLE).read_bytes() == CONSOLE
        assert (folder / RECOVERED_TAIL).read_bytes() == TAIL
        recovery = json.loads((folder / 'run1-ramoops.json').read_bytes())
        assert not recovery['slots'][0]['header_valid']
        assert recovery['slots'][1]['header_valid']
        assert recovery['slots'][1]['console']['file'] == RECOVERED_CONSOLE
        assert recovery['slots'][1]['version'] == 0
        assert recovery['slots'][1]['validation'] == 'legacy-structural-only'
        assert 'unverified' in recovery['slots'][1]['console']['provenance']['integrity']
        tails = recovery['periodic_tail_slots']
        assert tails[0]['header_valid'] and tails[0]['header_crc_valid'] and tails[0]['payload_crc_valid']
        assert tails[0]['tail']['file'] == RECOVERED_TAIL
        assert tails[0]['tail']['kind'] == 'periodic-printk-tail'
        assert not tails[1]['header_valid'] and tails[1]['header_crc_valid']
        assert not tails[1]['payload_crc_valid']
        assert 'payload CRC32 mismatch' in tails[1]['error']
        assert 'tail' not in tails[1]
        assert recovery['periodic_tail_sample_count'] == 1
        assert recovery['dmesg_record_count'] == recovery['panic_or_oops_record_count'] == 0
        assert {p.name for p in folder.iterdir()} == {
            'boot.img', 'run1-logdump.bin', 'run1-logdump.log', 'run1-sd.log',
            'run1-ramoops.json', RECOVERED_CONSOLE, RECOVERED_TAIL}
        actions = (root / 'actions').read_bytes()
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        again = subprocess.run(['bash', str(COLLECTOR), '1', 'boot.img'], cwd=folder,
                               env=env, capture_output=True)
        assert again.returncode != 0
        assert (root / 'actions').read_bytes() == actions, 'overwrite refusal touched phone'
        assert before == {p.name: p.read_bytes() for p in folder.iterdir()}
        for linked_index, suffix in enumerate((
                '-sd.log', '-ramoops.json',
                '-ramoops-slot1-seq2-ns2000-snapshot-console.log',
                '-printk-tail-slot0-seq1-ns3000-periodic-printk.log',
                '-printk-tail-slot1-seq99-ns99-periodic-printk.log')):
            linked = root / 'linked' / str(linked_index) / 'snapshot43'
            linked.mkdir(parents=True)
            (linked / 'boot.img').write_bytes(b'fixture image')
            output = linked / ('run1' + suffix)
            output.symlink_to('absent')
            again = subprocess.run(['bash', str(COLLECTOR), '1', 'boot.img'],
                                   cwd=linked, env=env, capture_output=True)
            assert again.returncode != 0
            assert (root / 'actions').read_bytes() == actions, 'dangling output touched phone'
            assert output.is_symlink()
        occupied = root / 'occupied' / 'snapshot43'
        occupied.mkdir(parents=True)
        (occupied / 'boot.img').write_bytes(b'fixture image')
        prior_tail = occupied / 'run1-printk-tail-slot1-seq99-ns99-periodic-printk.log'
        prior_tail.write_bytes(b'previous tail evidence\n')
        again = subprocess.run(['bash', str(COLLECTOR), '1', 'boot.img'],
                               cwd=occupied, env=env, capture_output=True)
        assert again.returncode != 0
        assert (root / 'actions').read_bytes() == actions, 'existing periodic output touched phone'
        assert prior_tail.read_bytes() == b'previous tail evidence\n'
        assert {p.name for p in occupied.iterdir()} == {'boot.img', prior_tail.name}
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
        print('collector trust-boundary checks passed: legacy console, CRC-validated periodic tails, CRC rejection, absent crash, matching, invalid slots, cat errors, stale SD, short raw, both failed, overwrite refusal')


if __name__ == '__main__':
    main()
