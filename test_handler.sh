#!/bin/bash
FPATH=$1
EXEC=$(head -1 $FPATH)
(tail +2 $FPATH && echo && cat handler_tests/data.json) | grep . | $EXEC