#!/usr/bin/env python3
"""Reuse the reviewed capture workflow in the fresh run260 namespace.

Run only after reviewing run260-build.log and package-run260.json.
Preserves evidence, RAM-boots once (never flashes), observes eight minutes,
returns to stock, and pulls logs. Refuses to overwrite existing run260 evidence.
"""
import hashlib
from pathlib import Path

helper = Path(__file__).with_name('run259-host-experiment.py')
data = helper.read_bytes()
assert hashlib.sha256(data).hexdigest() == (
    'fdd319be3cf91d45b6bd023ef502f84fb534f7a597d181a06144ed37aaa2b464'
), 'Capture helper changed; review it before operating the phone.'
source = data.decode().replace('run259', 'run260').replace("'259'", "'260'")
exec(compile(source, str(helper), 'exec'))
