# Copyright 2019 United States Government as represented by the Administrator of the
# National Aeronautics and Space Administration.  All Rights Reserved.
no_TRICK_ENV = 1
# GCC attributes these macros to their test call sites, so there are no production
# source lines for LCOV after test code is filtered out.  Keep tests and Valgrind.
NO_COVERAGE = 1
ifndef $(TS_MODELS_HOME)
    include ${GUNNS_HOME}/test/utils/Makefile.default
else
    include ${TS_MODELS_HOME}/test/utils/Makefile.default
endif

