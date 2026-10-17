#!/usr/bin/env python3
# Copyright 2024 United States Government as represented by the Administrator of the
# National Aeronautics and Space Administration.  All Rights Reserved.
#

import os
import sys
import xml.etree.ElementTree as ET


def main():
    path = os.path.join(os.environ['GUNNS_HOME'],
                        'sims/SIM_test/RUN_test/results/SIM_test_int_test_results.xml')
    try:
        root = ET.parse(path).getroot()
        if root.tag not in ('testsuites', 'testsuite'):
            raise ValueError('Expected a JUnit testsuite or testsuites report')
        executed = 0
        for element in root.iter():
            if element.tag in ('failure', 'error'):
                raise ValueError('Simulation reported a failure or error')
            for name in ('failures', 'errors'):
                if int(element.get(name, '0')) != 0:
                    raise ValueError('Simulation reported nonzero ' + name)
            if (element.tag == 'testcase' and element.get('status', 'run') == 'run'
                    and element.find('skipped') is None):
                executed += 1
        if not executed:
            raise ValueError('Simulation report contains no executed testcases')
    except (OSError, ET.ParseError, ValueError) as error:
        print('TEST FAILED: {}: {}'.format(path, error))
        return 1
    print('Simulation report passed: {} executed testcases'.format(executed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
