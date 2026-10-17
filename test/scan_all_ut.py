#!/usr/bin/env python3
# Copyright 2023 United States Government as represented by the Administrator of the
# National Aeronautics and Space Administration.  All Rights Reserved.
#
import re
import sys

def main():
    with open('make_all_ut.out') as stream:
        results = stream.read()
    failed = any(marker in results for marker in
                 ('FAILURES', 'Failures', 'NO TEST OUTPUT', 'COMMAND FAILED'))
    failed = failed or bool(re.search(r'OK \(0 tests?\)', results))
    failed = failed or bool(re.search(r'ERROR SUMMARY:\s*[1-9][0-9]*\s+errors?', results))
    if failed or not re.search(r'OK \([1-9][0-9]* tests?\)', results):
        print('\n***TEST FAILURE*** Failed commands, failed tests, memory errors, or no completed tests.\n')
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
