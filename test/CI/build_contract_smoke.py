#!/usr/bin/env python3
"""Exercise the real distributable library and its warm header dependencies."""
import os
from pathlib import Path
import subprocess


repo = Path(__file__).resolve().parents[2]
library = repo / 'lib/no_trick'
header = repo / 'aspects/dynamics/GunnsDynEuler321.hh'
archive = library / 'libgunns.a'
env = dict(os.environ, GUNNS_HOME=str(repo))


def make(*arguments):
    subprocess.check_call(['make', '-C', str(library)] + list(arguments), env=env)


make('clean')
make('-j4')
objects = list((library / 'build').rglob('GunnsDynEuler321.o'))
if len(objects) != 1 or not archive.is_file():
    raise RuntimeError('Expected the real no_trick archive and Euler321 object')
obj = objects[0]
before = (obj.stat().st_mtime_ns, archive.stat().st_mtime_ns)
make('-q')
original = header.read_bytes()
stat = header.stat()
try:
    header.write_bytes(original + b'\n// CI header dependency smoke.\n')
    make('-j4')
    after = (obj.stat().st_mtime_ns, archive.stat().st_mtime_ns)
    if not all(new > old for old, new in zip(before, after)):
        raise RuntimeError('Header edit did not rebuild the dependent object and archive')
    make('-q')
finally:
    header.write_bytes(original)
    os.utime(str(header), ns=(stat.st_atime_ns, stat.st_mtime_ns))
print('no_trick: clean build, initial no-op, header rebuild, and final no-op passed')
