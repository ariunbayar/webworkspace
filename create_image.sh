#!/bin/bash
#gvim --servername SRV
vim --servername SRV --remote-send ":view $1<Enter>"
vim --servername SRV --remote-send ":silent! | TOhtml | wq! /run/shm/tohtml.html<Enter>"
sleep 1
