#!/usr/bin/env python3
"""After reviewing run259-build.log: preserve, RAM boot once, observe, recover.

Refuses existing evidence. No flashing or frequency/governor writes.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time

REPO = Path('/home/kurision/development/kernel/ack-kgsl')
SNAP = REPO / 'porting/artifacts/snapshot60'
ADB = ['adb', '-s', '2819f2320604']
PYTHON = Path('/tmp/opencode/run258-diagvenv/bin/python')
assert (SNAP / 'run259-build.status').read_text().strip() == 'status=0'
assert PYTHON.is_file(), 'Restore pyserial venv before starting; see run258 workflow.'
subprocess.run([str(PYTHON), '-B', '-c', 'import serial; print(serial.__version__)'], check=True)
for p in [SNAP / 'run259-live', SNAP / 'run259-preboot', SNAP / 'run259-logdump.bin',
          SNAP / 'run259-usb.log', SNAP / 'run259-preclear.status']:
    assert not p.exists(), f'Refusing to overwrite {p}'
for line in subprocess.check_output(['ps', '-eo', 'pid,args'], text=True).splitlines():
    if any(x in line for x in ('usb-boot-capture.py', 'fastboot-boot-capture.py',
                              'adb -s 2819f2320604 logcat')):
        raise SystemExit('Existing capture process: ' + line)
LIVE = SNAP / 'run259-live'
LIVE.mkdir()
history = (LIVE / 'commands.jsonl').open('x')


def record(**rec):
    rec['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    history.write(json.dumps(rec) + '\n')
    history.flush()


def command(args, timeout=30, binary=False, cwd=None):
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd,
                           env=os.environ | {'TMPDIR': '/tmp/opencode'})
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = 124, e.stdout or b'', e.stderr or b''
    record(start=start, command=args, rc=rc,
           stdout=(dict(bytes=len(out), sha256=hashlib.sha256(out).hexdigest())
                   if binary else out.decode(errors='replace')),
           stderr=err.decode(errors='replace'))
    return rc, out


def stop(proc):
    if proc is not None and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    if proc is not None:
        record(event='capture stopped', pid=proc.pid, rc=proc.returncode)


rc, identity = command(ADB + ['shell', 'uname -r; cat /proc/sys/kernel/random/boot_id; su -c id'])
assert rc == 0 and identity.startswith(b'4.19') and b'uid=0' in identity
report = json.loads((SNAP / 'package-run259.json').read_text())
image = SNAP / 'boot-run259.img'
assert hashlib.sha256(image.read_bytes()).hexdigest() == report['sha256']
archive = SNAP / 'run259-preboot'
archive.mkdir()
(archive / 'identity.txt').write_bytes(identity)
hash_command = ADB + ['shell', 'su -c "sha256sum /dev/block/by-name/logdump"']
rc, digest = command(hash_command)
assert rc == 0
expected = digest.decode().split()[0]
rc, data = command(ADB + ['shell', '-T', "su -c 'dd if=/dev/block/by-name/logdump bs=1048576 count=64'"], timeout=120, binary=True)
assert rc == 0 and len(data) == 67108864
assert hashlib.sha256(data).hexdigest() == expected
(archive / 'logdump.bin').write_bytes(data)
(archive / 'logdump.sha256').write_text(expected + '  logdump.bin\n')
rc, digest = command(hash_command)
assert rc == 0 and digest.decode().split()[0] == expected
rc, listing = command(ADB + ['shell', "su -c 'find /data/local/tmp -maxdepth 1 -name \"ack-early-logcat.log*\" -type f'"])
assert rc == 0
names = listing.decode().splitlines()
for name in names:
    assert re.fullmatch(r'/data/local/tmp/ack-early-logcat\.log(?:\.[1-4])?', name), name
    rc, data = command(ADB + ['shell', '-T', 'su -c ' + shlex.quote('cat ' + shlex.quote(name))], binary=True)
    assert rc == 0
    (archive / Path(name).name).write_bytes(data)
    rc, digest = command(ADB + ['shell', 'su -c ' + shlex.quote('sha256sum ' + shlex.quote(name))])
    assert rc == 0 and hashlib.sha256(data).hexdigest() == digest.decode().split()[0]
(archive / 'archive.json').write_text(json.dumps(dict(logdump_sha256=expected, early_logcat_files=names), indent=2) + '\n')
for name in names:
    rc, digest = command(ADB + ['shell', 'su -c ' + shlex.quote('sha256sum ' + shlex.quote(name))])
    assert rc == 0 and hashlib.sha256((archive / Path(name).name).read_bytes()).hexdigest() == digest.decode().split()[0]
    rc, _ = command(ADB + ['shell', 'su -c ' + shlex.quote('rm -- ' + shlex.quote(name))])
    assert rc == 0
rc, data = command(['bash', str(REPO / 'porting/logging/clear-logdump.sh'), 'run259'], cwd=SNAP, timeout=120)
assert rc == 0, data
rc, _ = command(ADB + ['reboot', 'bootloader'])
assert rc == 0
capture_out = (LIVE / 'usb-capture.out').open('xb')
capture_args = ['timeout', '550', str(PYTHON), '-B',
                str(REPO / 'porting/logging/fastboot-boot-capture.py'),
                '--image', str(image), '--log', str(SNAP / 'run259-usb.log'),
                '--status', str(SNAP / 'run259-usb-capture.status'), '--boot-timeout', '480']
record(event='start USB/fastboot capture', command=capture_args)
capture = subprocess.Popen(capture_args, stdout=capture_out, stderr=subprocess.STDOUT,
                           start_new_session=True)
probe = ('uname -r; cat /proc/sys/kernel/random/boot_id; cut -d" " -f1 /proc/uptime; '
         'getprop sys.boot_completed; getprop init.svc.bootanim; '
         'pidof surfaceflinger; pidof system_server; ls -l /dev/ashmem; '
         'for p in /sys/devices/system/cpu/cpufreq/policy*; do '
         'echo POLICY=$p; cat $p/related_cpus $p/scaling_available_frequencies '
         '$p/scaling_cur_freq $p/cpuinfo_cur_freq $p/scaling_min_freq $p/scaling_max_freq '
         '$p/scaling_governor $p/stats/time_in_state; done; '
         'head -n 9 /proc/stat; cat /proc/loadavg; '
         'grep -E "^(MemAvailable|MemFree|SwapTotal|SwapFree):" /proc/meminfo')
logcat = None
logfile = None
seen_port = False
lost_stock = False
extra_samples = set()
start = time.monotonic()
try:
    with (LIVE / 'adb-timeline.jsonl').open('x') as timeline:
        while time.monotonic() - start < 600:
            tick = time.monotonic()
            rc, state = command(ADB + ['get-state'], timeout=3)
            rec = dict(elapsed=round(tick-start, 2), state=state.decode(errors='replace').strip(), rc=rc)
            uptime = 0
            if rc == 0 and state.strip() == b'device':
                rc, data = command(ADB + ['shell', probe], timeout=8)
                rec['probe'] = data.decode(errors='replace')
                if data.startswith(b'6.12'):
                    seen_port = True
                    try:
                        uptime = float(data.splitlines()[2])
                    except (ValueError, IndexError):
                        pass
                    if logcat is None or logcat.poll() is not None:
                        if logfile:
                            logfile.close()
                        logfile = (LIVE / ('logcat-' + str(int(tick-start)) + '.log')).open('xb')
                        logcat = subprocess.Popen(ADB + ['logcat', '-b', 'all', '-v', 'threadtime'],
                            stdout=logfile, stderr=subprocess.STDOUT, start_new_session=True)
                    for threshold in (120, 240):
                        if uptime >= threshold and threshold not in extra_samples:
                            rc, snapshot = command(ADB + ['shell', probe + '; top -b -n 1 -m 25'], timeout=15)
                            (LIVE / f'lag-sample-{threshold}.txt').write_bytes(snapshot)
                            extra_samples.add(threshold)
                if data.startswith(b'4.19') and (seen_port or lost_stock) and tick-start > 45:
                    rec['returned_to_stock'] = True
                    timeline.write(json.dumps(rec)+'\n'); timeline.flush()
                    break
            else:
                lost_stock = True
            timeline.write(json.dumps(rec)+'\n'); timeline.flush()
            if uptime >= 480:
                break
            time.sleep(max(0, 4-(time.monotonic()-tick)))
finally:
    stop(logcat)
    stop(capture)
    if logfile:
        logfile.close()
    capture_out.close()

rc, state = command(ADB + ['shell', 'uname -r'], timeout=8)
if state.startswith(b'6.12'):
    for name, args in [('final-probe.txt', ['shell', probe]),
                       ('logcat-final.log', ['logcat', '-b', 'all', '-d']),
                       ('crash-final.log', ['logcat', '-b', 'crash', '-d']),
                       ('cpuinfo-final.txt', ['shell', 'dumpsys cpuinfo']),
                       ('anr-final.txt', ['shell', 'dumpsys activity lastanr']),
                       ('dmesg-attempt.txt', ['shell', 'dmesg']),
                       ('clocks-attempt.txt', ['shell', 'cat /sys/kernel/debug/clk/clk_summary'])]:
        rc, data = command(ADB + args, timeout=20)
        (LIVE / name).write_bytes(data)
    record(event='host requested recovery reboot after observation')
    rc, _ = command(ADB + ['reboot'])
    assert rc == 0
end = time.monotonic() + 180
while time.monotonic() < end:
    rc, state = command(ADB + ['shell', 'uname -r; cat /proc/sys/kernel/random/boot_id; su -c id'], timeout=8)
    if state.startswith(b'4.19') and b'uid=0' in state:
        (LIVE / 'final-stock-identity.txt').write_bytes(state)
        break
    time.sleep(4)
else:
    raise SystemExit('Stock not confirmed; manual recovery required. No additional boot attempted.')
rc, data = command(['bash', str(REPO / 'porting/logging/pull-run-evidence.sh'), '259', str(image)], cwd=SNAP, timeout=180)
(LIVE / 'pull-evidence.out').write_bytes(data)
assert rc == 0
rc, data = command(['python3', '-B', str(REPO / 'porting/logging/decode-reset.py'), str(SNAP / 'run259-logdump.bin')])
(LIVE / 'reset.txt').write_bytes(data)
for suffix in ['', '.1', '.2', '.3', '.4']:
    rc, data = command(ADB + ['shell', '-T', 'su -c ' + shlex.quote('cat /data/local/tmp/ack-early-logcat.log' + suffix)], binary=True)
    if rc == 0:
        (LIVE / ('ack-early-logcat.log' + suffix)).write_bytes(data)
record(event='observation and recovery complete', port_observed=seen_port)
print('Observation and recovery complete; stock root confirmed. Port observed:', seen_port)
