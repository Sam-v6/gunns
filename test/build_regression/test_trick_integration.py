"""Exercise the prebuilt Trick build contract with the repository Makefiles.

Run with: python3 -m unittest discover -s test/build_regression -v
Only a C++ compiler, ar, and GNU make are required; no Trick or CUDA install.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[2]


class TrickIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gunns-trick-integration-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / "lib/trick"
        self.interface = self.root / "lib/trick_if"
        self.model.mkdir(parents=True)
        self.interface.mkdir()
        shutil.copyfile(str(REPO / "lib/trick/Makefile"), str(self.model / "Makefile"))
        (self.root / "model.cpp").write_text("int model() { return 1; }\n")
        self.set_sources(["model.cpp"])
        (self.root / "lib/sources_omit.mk").write_text("")
        (self.root / "lib/sources_cuda.mk").write_text("CUDASOURCES := $(SOURCES)\n")

    def set_sources(self, names):
        sources = " ".join("$(GUNNS_HOME)/" + name for name in names)
        (self.root / "lib/sources.mk").write_text("SOURCES := " + sources + "\n")

    def make(self, directory, *args):
        env = os.environ.copy()
        env["GUNNS_HOME"] = str(self.root)
        result = subprocess.run(
            ["make", "--no-print-directory", "-C", str(directory)] + list(args),
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        return result.stdout

    def test_manifest_is_stable_and_recovers_for_every_entry_target(self):
        for target, archive_name in (("all", "libgunns.a"), ("libgunns.a", "libgunns.a"),
                                     ("roses", "libgunnsroses.a"),
                                     ("libgunnsroses.a", "libgunnsroses.a")):
            with self.subTest(target=target):
                self.make(self.model, target)
                archive = self.model / archive_name
                manifest = self.interface / "S_source.hh"
                content = manifest.read_bytes()
                self.assertIn(b'#include "model.hh"', content)
                # Set an old time so a rewrite is visible even on coarse clocks.
                old = int(time.time()) - 20
                os.utime(str(manifest), (old, old))
                archive_time = archive.stat().st_mtime_ns
                self.make(self.model, target)
                self.assertEqual(old * 10**9, manifest.stat().st_mtime_ns)
                self.assertEqual(archive_time, archive.stat().st_mtime_ns)
                manifest.unlink()
                self.make(self.model, target)
                self.assertTrue(manifest.exists(), target + " did not recover the manifest")
                self.assertEqual(content, manifest.read_bytes())
                self.assertEqual(archive_time, archive.stat().st_mtime_ns)

    def test_source_rebuild_preserves_manifest_and_changed_source_list_updates_it(self):
        self.make(self.model, "all")
        manifest = self.interface / "S_source.hh"
        before = manifest.read_bytes()
        old = int(time.time()) - 20
        os.utime(str(manifest), (old, old))
        obj = self.model / ("build" + str(self.root / "model.o"))
        os.utime(str(obj), (old - 1, old - 1))
        os.utime(str(self.root / "model.cpp"), (old, old))
        output = self.make(self.model, "all")
        self.assertIn("ar crs", output)
        self.assertEqual(before, manifest.read_bytes())
        self.assertEqual(old * 10**9, manifest.stat().st_mtime_ns)
        (self.root / "added.cpp").write_text("int added() { return 2; }\n")
        self.set_sources(["model.cpp", "added.cpp"])
        self.make(self.model, "libgunns.a")
        self.assertIn(b'#include "added.hh"', manifest.read_bytes())
        self.assertNotEqual(before, manifest.read_bytes())

    def prepare_sim(self, variant, s_main):
        trick = self.root / "trick/share/trick/makefiles"
        trick.mkdir(parents=True, exist_ok=True)
        (trick / "trickify.mk").touch()
        for name in ("libgunns.a", "libgunnsroses.a"):
            (self.model / name).touch()
        (self.interface / "libgunns.o").touch()
        sim = self.root / "sim"
        sim.mkdir(exist_ok=True)
        (sim / "Makefile").write_text(
            "TRICK_HOME := {root}/trick\nTRICK_HOST_TYPE := Linux\n"
            "{s_main}\n.DEFAULT_GOAL := sim\n"
            "include {repo}/lib/trick_if/{variant}\n"
            "sim:\n\t@echo link >> links\n\t@touch $@\n".format(
                root=self.root, s_main=s_main, repo=REPO, variant=variant))
        return sim

    def test_both_prebuilt_libraries_trigger_relink_and_then_no_op(self):
        for variant, model in (("S_gunns.mk", "libgunns.a"),
                               ("S_gunns_roses.mk", "libgunnsroses.a")):
            with self.subTest(variant=variant):
                sim = self.prepare_sim(variant, "S_MAIN := sim")
                executable = sim / "sim"
                links = sim / "links"
                if links.exists():
                    links.unlink()
                if executable.exists():
                    executable.unlink()
                self.make(sim)
                for library in (self.model / model, self.interface / "libgunns.o"):
                    old = int(time.time()) - 20
                    for path in (self.model / model, self.interface / "libgunns.o"):
                        os.utime(str(path), (old, old))
                    os.utime(str(executable), (old + 1, old + 1))
                    os.utime(str(library), (old + 2, old + 2))
                    count = len(links.read_text().splitlines())
                    self.make(sim)
                    self.assertEqual(count + 1, len(links.read_text().splitlines()))
                    self.make(sim)
                    self.assertEqual(count + 1, len(links.read_text().splitlines()))

    def test_unset_s_main_and_missing_prebuilt_libraries_keep_fallback(self):
        for variant in ("S_gunns.mk", "S_gunns_roses.mk"):
            with self.subTest(variant=variant):
                sim = self.prepare_sim(variant, "")
                self.make(sim)
                # With either library absent, the usual per-sim generation path applies.
                for library in (self.model / ("libgunnsroses.a" if "roses" in variant
                                             else "libgunns.a"),
                                self.interface / "libgunns.o"):
                    sim = self.prepare_sim(variant, "S_MAIN := sim")
                    library.unlink()
                    self.make(sim)


if __name__ == "__main__":
    unittest.main()
