"""Exercise the library Makefiles with real compilers and small source fixtures.

Run with: python3 -m unittest discover -s test/build_regression -v
The roses fixtures exercise those recipes without requiring CUDA headers/libraries.
"""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("make") and shutil.which("g++"),
                     "requires GNU make and g++")
class HeaderDependenciesTest(unittest.TestCase):
    def make(self, directory, root, target=None, expect_success=True):
        command = ["make", "-C", str(directory), "GUNNS_HOME=" + str(root),
                   "CXX=g++", "OPTS=-O0", "WARNOPTS="]
        if target:
            command.append(target)
        result = subprocess.run(command, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True)
        if expect_success:
            self.assertEqual(0, result.returncode, result.stdout)
        return result

    def check_library(self, library, target):
        with tempfile.TemporaryDirectory(prefix="gunns-header-deps-") as temporary:
            root = Path(temporary)
            directory = root / "lib" / library
            directory.mkdir(parents=True)
            (root / "lib" / "trick_if").mkdir(exist_ok=True)
            shutil.copyfile(str(REPO / "lib" / library / "Makefile"),
                            str(directory / "Makefile"))
            source = root / "src"
            source.mkdir()
            (source / "transitive.hh").write_text("#define TRANSITIVE_VALUE 1\n")
            (source / "direct.hh").write_text(
                '#include "transitive.hh"\n#define DIRECT_VALUE 2\n')
            extensions = ["cpp", "c"] if library == "trick" else ["cpp"]
            for extension in extensions:
                (source / ("dependent_" + extension + "." + extension)).write_text(
                    '#include "direct.hh"\nint dependent_' + extension +
                    '() { return DIRECT_VALUE + TRANSITIVE_VALUE; }\n')
            (source / "unrelated.cpp").write_text("int unrelated() { return 7; }\n")
            (root / "lib" / "sources.mk").write_text(
                "SOURCES := $(wildcard $(GUNNS_HOME)/src/*.cpp) "
                "$(wildcard $(GUNNS_HOME)/src/*.c)\n")
            for name in ("sources_omit.mk", "sources_omit_trickless.mk"):
                (root / "lib" / name).write_text("")
            (root / "lib" / "sources_cuda.mk").write_text("CUDASOURCES := $(SOURCES)\n")

            self.make(directory, root, target)
            build = directory / ("buildroses" if target == "roses" else "build")
            objects = sorted(build.rglob("*.o"))
            self.assertEqual(len(extensions) + 1, len(objects))
            archive = directory / ("libgunnsroses.a" if target == "roses" else "libgunns.a")
            tracked = objects + [archive]

            def snapshot():
                return {path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                        for path in tracked}

            before = snapshot()
            # No explicit target: included depfiles must not replace the default.
            self.make(directory, root, target)
            self.assertEqual(before, snapshot())

            for header, content in (
                    ("direct.hh", '#include "transitive.hh"\n#define DIRECT_VALUE 3\n'),
                    ("transitive.hh", "#define TRANSITIVE_VALUE 4\n")):
                # Put outputs in the past, avoiding sleeps and timestamp races.
                old = time.time() - 2
                for path in source.iterdir():
                    os.utime(str(path), (old - 1, old - 1))
                for path in tracked:
                    os.utime(str(path), (old, old))
                before = snapshot()
                (source / header).write_text(content)
                self.make(directory, root, target)
                after = snapshot()
                for path in objects:
                    if path.name.startswith("dependent_"):
                        self.assertNotEqual(before[path], after[path], str(path))
                        self.assertNotEqual(before[path][1], after[path][1], str(path))
                    else:
                        self.assertEqual(before[path], after[path], str(path))
                self.assertNotEqual(before[archive], after[archive])
                self.make(directory, root, target)
                self.assertEqual(after, snapshot())

            # A stale depfile entry must not prevent removal of an unused header.
            (source / "transitive.hh").unlink()
            (source / "direct.hh").write_text(
                "#define TRANSITIVE_VALUE 5\n#define DIRECT_VALUE 6\n")
            self.make(directory, root, target)
            after = snapshot()
            self.make(directory, root, target)
            self.assertEqual(after, snapshot())
            # Still-included missing headers must fail compilation.
            (source / "direct.hh").unlink()
            result = self.make(directory, root, target, expect_success=False)
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("direct.hh", result.stdout)
            self.make(directory, root, "clean")
            self.assertFalse(build.exists())
            self.assertFalse(archive.exists())
            self.assertFalse(list(directory.rglob("*.d")))

    def test_header_rebuilds(self):
        for library in ("no_trick", "test", "trick"):
            for target in (None, "roses"):
                with self.subTest(library=library, target=target or "default"):
                    self.check_library(library, target)


if __name__ == "__main__":
    unittest.main()
