<?php
function saveAndRedirect($url) {
    global $m;
    $m->save();
    header('Location: ' . $url);
    exit(0);
}

function openFileAndStop($watch) {
    global $m;
    $file = $m->browser->directory . $watch->file;
    exec("gnome-terminal -e \"gvim '$file'\"");
    exit(0);
}
