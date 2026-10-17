#!/bin/tcsh -f
####################### BASH HEADER ######################
# PROGRAMMERS:
#    (
#       (Jason Harvey)  (L-3 Communications Corp) (File Creation)                                (A time long ago...)
#       (Syam Evani)    (Axiom Space)             (Converting to automatically find all folders) (08-30-2023)
#    )
##########################################################

# Copyright 2025 United States Government as represented by the Administrator of the
# National Aeronautics and Space Administration.  All Rights Reserved.

set OUT = `pwd`/make_all_ut.out
echo ' ' > $OUT
echo '**** make_all_ut summary ****' >> $OUT

# clean & re-build the test compiled lib
cd $GUNNS_HOME/lib/test
make clean
if ($status != 0) then
    echo 'COMMAND FAILED: lib/test make clean' >> $OUT
    exit 1
endif
make
if ($status != 0) then
    echo 'COMMAND FAILED: lib/test make' >> $OUT
    exit 1
endif

# Array of partial paths of excluded subfolders
set excluded_subfolder_partials = ("ThermAspectGenerate/test" "radiation/test" "radiation/network/test" "networks/electrical/test" "networks/fluid/test" "networks/basic/test" "cuda/test" "intersect/test" "hs/test" "software/unit_test/test" "software/exceptions/test" "lib/test")

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
        make
        if ($status != 0) echo "$FOLDER\: COMMAND FAILED: make" >> $OUT
        if ( -f $FOLDER/output/unit-tests-valgrind.log ) then
            set test_result = "`grep -s -E 'OK \(*|FAILURES\!|Failures \!' $FOLDER/output/unit-tests-valgrind.log`"
            if ("$test_result" == "") then
                echo "$FOLDER\: NO TEST OUTPUT" >> $OUT
            else
                echo "$FOLDER\: $test_result" >> $OUT
            endif
            grep -s 'ERROR SUMMARY' $FOLDER/output/unit-tests-valgrind.log >> $OUT
        else
            echo $FOLDER\: NO TEST OUTPUT, possibly failed to build! >> $OUT
        endif
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
python3 $GUNNS_HOME/test/scan_all_ut.py
exit $status
