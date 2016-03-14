#!/bin/sh

dir='/var/www/html/webworkspace'

# start php server
gnome-terminal -t 'PHP Web Server' --working-directory "$dir/web" -e "php -S 127.0.0.1:8081 index.php"

# load a shell
gnome-terminal -t 'Webworkspace shell' --working-directory "$dir"

# Load index page
google-chrome
sleep 3
google-chrome "http://localhost:8081"
google-chrome "https://bitbucket.org/ariunbayar/webworkspace/issues?status=new&status=open"
