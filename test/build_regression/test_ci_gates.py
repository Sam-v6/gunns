"""Failure-boundary regressions; external builds are fixtures, not component tests."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]


class CiGates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gunns-ci-gates-')
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GUNNS_HOME=str(self.root))
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env['PATH'] = str(self.bin) + os.pathsep + os.environ['PATH']

    def tearDown(self):
        self.temp.cleanup()

    def run_command(self, command, cwd=None):
        return subprocess.run(command, cwd=str(cwd or self.root), env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)

    def executable(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def scan(self, asan, text):
        suffix = '_asan' if asan else ''
        (self.root / ('make_all_ut' + suffix + '.out')).write_text(text)
        return self.run_command([sys.executable, str(REPO / 'test' /
                                                   ('scan_all_ut' + suffix + '.py'))])

    def test_summary_scanners(self):
        for asan in (False, True):
            for text, passed in [
                ('suite: OK (2 tests)\n', True),
                ('suite: OK (1 tests)\n', True),
                ('summary heading only\n', False),
                ('suite: OK (0 tests)\n', False),
                ('suite: OK (1 tests)\nother: OK (0 tests)\n', False),
                ('suite: FAILURES!!!\n', False),
                ('suite: Failures !!!\n', False),
                ('suite: NO TEST OUTPUT\n', False),
                ('suite: OK (1 tests)\nCOMMAND FAILED: make exited 2\n', False),
                ('suite: OK (1 tests)\n==3== ERROR SUMMARY: 1 errors\n', False),
                ('suite: OK (1 tests)\n==3== ERROR SUMMARY: 0 errors\n', True),
            ]:
                with self.subTest(asan=asan, text=text):
                    result = self.scan(asan, text)
                    self.assertEqual(result.returncode == 0, passed, result.stdout)
        for diagnostic in ('SUMMARY: AddressSanitizer: leak',
                           'ERROR: LeakSanitizer: detected memory leaks',
                           'AddressSanitizer:DEADLYSIGNAL'):
            result = self.scan(True, 'suite: OK (1 tests)\n' + diagnostic)
            self.assertNotEqual(result.returncode, 0, result.stdout)

    def make_log(self, target, extra=()):
        return self.run_command(['make', '-f', str(REPO / 'test/utils/Makefile.default'),
                                 'ASAN=asan', target] + list(extra))

    def test_executable_exit_survives_tee(self):
        (self.root / 'unit-tests').write_text('#!/bin/sh\necho "OK (1 tests)"\nexit 9\n')
        (self.root / 'unit-tests').chmod(0o755)
        result = self.make_log('./output/./unit-tests.log')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('OK (1 tests)', (self.root / 'output/unit-tests.log').read_text())

    def test_valgrind_exit_and_summary(self):
        (self.root / 'unit-tests').write_text('fixture')
        self.executable('valgrind', '#!/bin/sh\necho "==3== ERROR SUMMARY: 1 errors"\ncase "$*" in *--error-exitcode=1*) exit 42 ;; *) exit 0 ;; esac\n')
        # Override the executable prerequisite so this exercises only the real log rule.
        result = self.run_command(['make', '-f', str(REPO / 'test/utils/Makefile.default'),
                                   '-o', './unit-tests', './output/unit-tests-valgrind.log'])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('ERROR SUMMARY: 1 errors',
                      (self.root / 'output/unit-tests-valgrind.log').read_text())

    def test_successful_executable_and_valgrind(self):
        executable = self.root / 'unit-tests'
        executable.write_text('#!/bin/sh\necho "OK (1 tests)"\n')
        executable.chmod(0o755)
        result = self.make_log('./output/./unit-tests.log')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.executable('valgrind', '#!/bin/sh\necho "==3== ERROR SUMMARY: 0 errors"\n')
        result = self.run_command(['make', '-f', str(REPO / 'test/utils/Makefile.default'),
                                   '-o', './unit-tests', './output/unit-tests-valgrind.log'])
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_real_asan_leak(self):
        if not shutil.which('g++'):
            self.skipTest('g++ required for intentional sanitizer leak')
        source = self.root / 'leak.cpp'
        source.write_text('#include <cstdlib>\n#include <cstdio>\n'
                          'int main(){void *p=malloc(123); *((volatile char*)p)=42; '
                          'puts("OK (1 tests)"); fflush(stdout); return 0;}\n')
        result = self.run_command(['g++', '-O0', '-g', '-fsanitize=address',
                                   str(source), '-o', 'unit-tests'])
        self.assertEqual(result.returncode, 0, result.stdout)
        self.env['ASAN_OPTIONS'] = 'log_path=output/asan.log:detect_leaks=1'
        result = self.make_log('./output/./unit-tests.log')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        diagnostics = '\n'.join(p.read_text() for p in (self.root / 'output').glob('asan.log*'))
        self.assertIn('SUMMARY: AddressSanitizer:', diagnostics)
        self.assertNotEqual(self.scan(True, 'suite: OK (1 tests)\n' + diagnostics).returncode, 0)

    def runner(self, asan, scenario='pass', suites=True):
        if not shutil.which('tcsh'):
            self.skipTest('tcsh required for aggregate runner fixtures')
        test_dir = self.root / 'test'
        test_dir.mkdir(exist_ok=True)
        for name in ('scan_all_ut.py', 'scan_all_ut_asan.py'):
            shutil.copyfile(str(REPO / 'test' / name), str(test_dir / name))
        (self.root / 'lib/test').mkdir(parents=True, exist_ok=True)
        if suites:
            for folder in ('core/test', 'cuda/test', 'FetSwitch/test'):
                directory = self.root / folder
                directory.mkdir(parents=True, exist_ok=True)
                (directory / 'Makefile').write_text('fixture')
        self.env['CI_SCENARIO'] = scenario
        self.executable('make', '''#!/usr/bin/env python3
import os, pathlib, shutil, sys
here = pathlib.Path.cwd()
scenario = os.environ['CI_SCENARIO']
if 'clean' in sys.argv:
    if (here / 'output').exists(): shutil.rmtree(str(here / 'output'))
    sys.exit(2 if scenario == 'clean_fail' and here.name == 'test' and here.parent.name != 'lib' else 0)
if here == pathlib.Path(os.environ['GUNNS_HOME']) / 'lib/test':
    sys.exit(2 if scenario == 'lib_fail' else 0)
if 'cuda' in str(here): sys.exit(99)
if 'FetSwitch' in str(here) and any('ASAN=' in arg for arg in sys.argv): sys.exit(99)
if scenario == 'missing': sys.exit(0)
output = here / 'output'
output.mkdir(exist_ok=True)
name = 'unit-tests.log' if any('ASAN=' in arg for arg in sys.argv) else 'unit-tests-valgrind.log'
(output / name).write_text('' if scenario == 'empty' else 'OK (1 tests)\\n')
if scenario == 'asan': (output / 'asan.log.123').write_text('SUMMARY: AddressSanitizer: leak\\n')
if scenario == 'valgrind':
    with (output / name).open('a') as stream: stream.write('==3== ERROR SUMMARY: 7 errors\\n')
sys.exit(2 if scenario == 'make_fail' else 0)
''')
        script = 'make_all_ut_asan.sh' if asan else 'make_all_ut.sh'
        return self.run_command(['tcsh', '-f', str(REPO / 'test' / script)], test_dir)

    def test_aggregate_runners(self):
        for asan in (False, True):
            for scenario in ('pass', 'clean_fail', 'make_fail', 'empty', 'missing',
                             'asan' if asan else 'valgrind'):
                with self.subTest(asan=asan, scenario=scenario):
                    result = self.runner(asan, scenario)
                    self.assertEqual(result.returncode == 0, scenario == 'pass', result.stdout)
                    self.assertIn('Excluding folder:', result.stdout)
        result = self.runner(False, 'lib_fail')
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_no_discovered_suites(self):
        for asan in (False, True):
            with self.subTest(asan=asan):
                result = self.runner(asan, suites=False)
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def class_driver(self, stage):
        sim = self.root / 'sims/SIM_class_test_compile'
        sim.mkdir(parents=True, exist_ok=True)
        interface = self.root / 'lib/trick_if'
        interface.mkdir(parents=True, exist_ok=True)
        (interface / 'S_source.hh').write_text('#include "Fixture.hh"\n')
        (sim / 'class_test_list.py').write_text('Fixture.hh\n')
        (sim / 'class_ignore_list.py').write_text('class_ignore_list = []\n')
        (sim / 'gen_sm.py').write_text('raise SystemExit({})\n'.format(2 if stage == 'generate' else 0))
        self.executable('make', '#!/bin/sh\nexit {}\n'.format(2 if stage == 'clean' else 0))
        self.executable('trick-CP', '#!/bin/sh\nmkdir -p build\necho "Build FAILED" > build/MAKE_err\nexit {}\n'.format(2 if stage == 'compile' else 0))
        return self.run_command([sys.executable, str(REPO / 'sims/SIM_class_test_compile/test_list.py')], sim)

    def test_class_compile_stages(self):
        for stage in ('clean', 'generate', 'compile', 'success'):
            with self.subTest(stage=stage):
                result = self.class_driver(stage)
                self.assertEqual(result.returncode == 0, stage == 'success', result.stdout)

    def test_sim_xml(self):
        results = self.root / 'sims/SIM_test/RUN_test/results'
        results.mkdir(parents=True)
        path = results / 'SIM_test_int_test_results.xml'
        command = [sys.executable, str(REPO / 'test/CI/sim_test.py')]
        self.assertNotEqual(self.run_command(command).returncode, 0)
        for xml, passed in [
            ('', False), ('not xml', False), ('<testsuites/>', False),
            ('<unrelated><testcase/></unrelated>', False),
            ('<testsuites><testsuite><testcase name="ok"/></testsuite></testsuites>', True),
            ('<testsuite tests="1"><testcase name="ok"/></testsuite>', True),
            ('<testsuite><testcase status="notrun"/></testsuite>', False),
            ('<testsuite><testcase><skipped/></testcase></testsuite>', False),
            ('<testsuites><testsuite><testsuite><testcase><failure/></testcase></testsuite></testsuite></testsuites>', False),
            ('<testsuite><testcase><error/></testcase></testsuite>', False),
            ('<testsuite errors="1"><testcase/></testsuite>', False),
            ('<testsuite failures="1"><testcase/></testsuite>', False),
            ('<testsuite failures="bad"><testcase/></testsuite>', False),
        ]:
            with self.subTest(xml=xml):
                path.write_text(xml)
                result = self.run_command(command)
                self.assertEqual(result.returncode == 0, passed, result.stdout)
        shutil.copyfile(str(REPO / 'sims/SIM_test/RUN_test/results/SIM_test_int_test_results.xml'), str(path))
        self.assertEqual(self.run_command(command).returncode, 0)


if __name__ == '__main__':
    unittest.main()
