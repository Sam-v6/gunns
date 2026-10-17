#!/bin/tcsh -f

# Copyright 2025 United States Government as represented by the Administrator of the
# National Aeronautics and Space Administration.  All Rights Reserved.
#
#TODO Clean this up and improve it to work on a list of test folders....

set OUT = `pwd`/make_all_ut_asan.out
echo ' ' > $OUT
echo '**** make_all_ut_asan summary ****' >> $OUT

# Clean & re-build the test compiled lib
#TODO cd $GUNNS_HOME/lib/test; make clean;
setenv ASAN_OPTIONS 'log_path=output/asan.log'
set UT_RECIPE = "make ASAN='asan'"

# Array of partial paths of excluded subfolders
set excluded_subfolder_partials = ("ThermAspectGenerate/test" "radiation/test" "radiation/network/test" "networks/electrical/test" "networks/fluid/test" "networks/basic/test" "cuda/test" "intersect/test" "hs/test" "software/unit_test/test" "software/exceptions/test" "lib/test" "FetSwitch/test")

# Find all "test" folders below the current directory
set test_folders = `find $GUNNS_HOME -type d -name "test" -exec test -e "{}/Makefile" \; -print`

set suite_count = 0

# Loop through each test folder
foreach test_folder ($test_folders)
    # Check if the current test folder's path contains any excluded subfolder partial
    set is_excluded = 0
    foreach excluded_subfolder_partial ($excluded_subfolder_partials)
        if ("$test_folder:q" =~ "*$excluded_subfolder_partial*") then
            set is_excluded = 1
            break
        endif
    end

    # If not excluded, execute the commands
    if ($is_excluded == 0) then
        echo "Executing commands in: $test_folder"
        
        # Set the FOLDER variable to the path of the current test folder
        setenv FOLDER "$test_folder"
        
        # Run
        echo "Running commands in: $FOLDER"
        @ suite_count++
        cd $FOLDER
        make clean
        if ($status != 0) echo "$FOLDER\: COMMAND FAILED: make clean" >> $OUT
        $UT_RECIPE
        if ($status != 0) echo "$FOLDER\: COMMAND FAILED: make" >> $OUT
        if ( -f $FOLDER/output/unit-tests.log ) then
            set test_result = "`grep -s -E 'OK \(*|FAILURES\!|Failures \!' $FOLDER/output/unit-tests.log`"
            if ("$test_result" == "") then
                echo "$FOLDER\: NO TEST OUTPUT" >> $OUT
            else
                echo "$FOLDER\: $test_result" >> $OUT
            endif
        else
            echo $FOLDER\: NO TEST OUTPUT, possibly failed to build! >> $OUT
        endif
        # ASan sends diagnostics to separate PID-suffixed files.
        foreach asan_log (`find output -maxdepth 1 -type f -name 'asan.log*'`)
            cat $asan_log >> $OUT
        end
    else
        echo "Excluding folder: $test_folder"
    endif
end

########################################################
# Summarize results to screen
########################################################
echo "SUITES RUN: $suite_count" >> $OUT
echo ' ' >> $OUT
tail -n 100 $OUT
cd $OUT:h
python3 $GUNNS_HOME/test/scan_all_ut_asan.py
exit $status
