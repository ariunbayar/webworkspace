#!/bin/bash

# Usage: test.sh main.py
# Press j, k to scroll

f=$(readlink -f $1)

gvim --servername SRV "$1"

a=()

lines=$(ack -s -H --nopager --nogroup 'function [A-z_0-9]+\(' $f)

while read line; do
    IFS=: read v1 n v2<<< "$line"
    a+=($n)
done <<< "$lines"

echo "${a[@]}"


current_idx=0

while read -s -n1 char; do

    case $char in
        "k")
            current_idx=$((current_idx - 1))
            if [[ $current_idx -lt 0 ]]; then
                current_idx=0
            fi
            ;;
        "j")
            current_idx=$((current_idx + 1))
            if [[ $current_idx -ge ${#a[@]} ]]; then
                current_idx=$((${#a[@]} - 1))
            fi
            ;;
    esac

    n=${a[$current_idx]}
    vim --servername SRV --remote-send "${n}Gzz"
done
