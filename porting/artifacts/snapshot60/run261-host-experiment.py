#!/usr/bin/env python3
"""Reuse the reviewed capture workflow in the fresh run261 namespace.

Run only after reviewing run261-build.log and package-run261.json.
Preserves evidence, RAM-boots once (never flashes), observes ten minutes,
returns to stock, and pulls logs. Refuses to overwrite existing run261 evidence.
"""
import hashlib
from pathlib import Path

helper = Path(__file__).with_name('run259-host-experiment.py')
data = helper.read_bytes()
assert hashlib.sha256(data).hexdigest() == (
    'fdd319be3cf91d45b6bd023ef502f84fb534f7a597d181a06144ed37aaa2b464'
), 'Capture helper changed; review it before operating the phone.'
source = data.decode().replace('run259', 'run261').replace("'259'", "'261'")
exec(compile(source, str(helper), 'exec'))
