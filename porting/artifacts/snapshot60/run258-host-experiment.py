#!/usr/bin/env python3
"""One bounded RAM boot; preserve logs and return to rooted stock."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

REPO = Path('/home/kurision/development/kernel/ack-kgsl')
SNAP = REPO / 'porting/artifacts/snapshot60'
ADB = ['adb', '-s', '2819f2320604']
LIVE = SNAP / 'run258-live'
LIVE.mkdir()
history = (LIVE / 'commands.jsonl').open('x')


def command(args, timeout=30):
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = 124, e.stdout or b'', e.stderr or b''
    history.write(json.dumps(dict(start=start, command=args, rc=rc,
                                 stdout=out.decode(errors='replace'),
                                 stderr=err.decode(errors='replace'))) + '\n')
    history.flush()
    return rc, out


rc, identity = command(ADB + ['shell', 'uname -r; su -c id'])
assert rc == 0 and identity.startswith(b'4.19') and b'uid=0' in identity
report = json.loads((SNAP / 'package-run258.json').read_text())
image = SNAP / 'boot-run258.img'
assert hashlib.sha256(image.read_bytes()).hexdigest() == report['sha256']
archive = SNAP / 'run258-preboot'
expected = (archive / 'logdump.sha256').read_text().split()[0]
rc, digest = command(ADB + ['shell', 'su -c "sha256sum /dev/block/by-name/logdump"'])
assert rc == 0 and digest.decode().split()[0] == expected
for name in json.loads((archive / 'archive.json').read_text())['early_logcat_files']:
    local = archive / Path(name).name
    rc, digest = command(ADB + ['shell', 'su -c ' + shlex.quote('sha256sum ' + shlex.quote(name))])
    assert rc == 0 and hashlib.sha256(local.read_bytes()).hexdigest() == digest.decode().split()[0]
    rc, _ = command(ADB + ['shell', 'su -c ' + shlex.quote('rm -- ' + shlex.quote(name))])
    assert rc == 0
p = subprocess.run(['bash', str(REPO / 'porting/logging/clear-logdump.sh'), 'run258'], cwd=SNAP)
assert p.returncode == 0
rc, _ = command(ADB + ['reboot', 'bootloader'])
assert rc == 0
capture_out = (LIVE / 'usb-capture.out').open('xb')
capture = subprocess.Popen([
    '/tmp/opencode/run258-diagvenv/bin/python', '-B',
    str(REPO / 'porting/logging/fastboot-boot-capture.py'),
    '--image', str(image), '--log', str(SNAP / 'run258-usb.log'),
    '--status', str(SNAP / 'run258-usb-capture.status'), '--boot-timeout', '480'],
    stdout=capture_out, stderr=subprocess.STDOUT)
probe = ('uname -r; cat /proc/sys/kernel/random/boot_id; cat /proc/uptime; '
         'getprop sys.boot_completed; getprop init.svc.bootanim; '
         'pidof surfaceflinger; pidof system_server; ls -l /dev/ashmem; '
         'for p in /sys/devices/system/cpu/cpufreq/policy*; do '
         'echo POLICY=$p; cat $p/related_cpus $p/scaling_available_frequencies '
         '$p/scaling_cur_freq $p/scaling_min_freq $p/scaling_max_freq; done')
logcat = None
logfile = None
seen_port = False
lost_stock = False
start = time.monotonic()
try:
    with (LIVE / 'adb-timeline.jsonl').open('x') as timeline:
        while time.monotonic() - start < 540:
            tick = time.monotonic()
            rc, state = command(ADB + ['get-state'], timeout=3)
            rec = dict(elapsed=round(tick-start, 2), state=state.decode(errors='replace').strip(), rc=rc)
            if rc == 0 and state.strip() == b'device':
                rc, data = command(ADB + ['shell', probe], timeout=8)
                rec['probe'] = data.decode(errors='replace')
                port = data.startswith(b'6.12')
                if port:
                    seen_port = True
                    if logcat is None or logcat.poll() is not None:
                        if logfile:
                            logfile.close()
                        logfile = (LIVE / ('logcat-' + str(int(tick-start)) + '.log')).open('xb')
                        logcat = subprocess.Popen(ADB + ['logcat', '-b', 'all', '-v', 'threadtime'], stdout=logfile, stderr=subprocess.STDOUT)
                if data.startswith(b'4.19') and (seen_port or lost_stock) and tick-start > 45:
                    rec['returned_to_stock'] = True
                    timeline.write(json.dumps(rec)+'\n'); timeline.flush()
                    break
            else:
                lost_stock = True
            timeline.write(json.dumps(rec)+'\n'); timeline.flush()
            if tick-start >= 480 and seen_port:
                break
            time.sleep(max(0, 4-(time.monotonic()-tick)))
finally:
    for p in (logcat, capture):
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait()
    if logfile:
        logfile.close()
    capture_out.close()

rc, state = command(ADB + ['shell', 'uname -r'], timeout=8)
if state.startswith(b'6.12'):
    for name, args in [('final-probe.txt', ['shell', probe]),
                       ('logcat-final.log', ['logcat', '-b', 'all', '-d']),
                       ('dmesg-attempt.txt', ['shell', 'dmesg'])]:
        rc, data = command(ADB + args, timeout=30)
        (LIVE / name).write_bytes(data)
    rc, _ = command(ADB + ['reboot'])
    assert rc == 0
end = time.monotonic() + 180
while time.monotonic() < end:
    rc, state = command(ADB + ['shell', 'uname -r; su -c id'], timeout=8)
    if state.startswith(b'4.19') and b'uid=0' in state:
        (LIVE / 'final-stock-identity.txt').write_bytes(state)
        break
    time.sleep(4)
else:
    raise SystemExit('Stock not confirmed; manual recovery required. No additional boot attempted.')
with (LIVE / 'pull-evidence.out').open('xb') as out:
    p = subprocess.run(['bash', str(REPO / 'porting/logging/pull-run-evidence.sh'), '258', str(image)], cwd=SNAP, stdout=out, stderr=subprocess.STDOUT, env=__import__('os').environ | {'TMPDIR': '/tmp/opencode'})
assert p.returncode == 0
rc, data = command(['python3', '-B', str(REPO / 'porting/logging/decode-reset.py'), str(SNAP / 'run258-logdump.bin')])
(LIVE / 'reset.txt').write_bytes(data)
for suffix in ['', '.1', '.2', '.3', '.4']:
    rc, data = command(ADB + ['shell', '-T', 'su -c ' + shlex.quote('cat /data/local/tmp/ack-early-logcat.log' + suffix)])
    if rc == 0:
        (LIVE / ('ack-early-logcat.log' + suffix)).write_bytes(data)
print('Observation and recovery complete; stock root confirmed. Port observed:', seen_port)
