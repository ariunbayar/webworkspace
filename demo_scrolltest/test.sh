#!/bin/bash
n=0
script_dir=$(dirname "$(readlink -e "$0")")
echo "" > test.log
find .. -name '*.js' |
while read f; do
    n=$((n+1))
    echo "$n - $f" >> test.log
    echo "--------------------------------" >> test.log
    python "$script_dir/../demo_code_fold/parse.py" "$f" "output_${n}.png" 2>> test.log >> test.log
    echo "" >> test.log
    echo "" >> test.log
done
