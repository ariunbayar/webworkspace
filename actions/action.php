<?php

$m = new Manager();

if (array_key_exists('directory', $_POST)) {
    $m->directory = $_POST['directory'];
    saveAndRedirect($_SERVER['REQUEST_URI']);
}

if (array_key_exists('pick', $_GET)) {
    // TODO don't add if already exists
    $m->watches[] = new FileWatch($_GET['pick']);
    $qargs = $_GET;
    unset($qargs['pick']);
    saveAndRedirect($_SERVER['SCRIPT_NAME'] . '?' . http_build_query($qargs));
}

if (array_key_exists('watch', $_POST)) {
    // save watch file positions
    foreach ($m->watches as $i => $watch) {
        $watch->load($_POST['watch'][$i]);
    }
    saveAndRedirect($_SERVER['REQUEST_URI']);
}

if (array_key_exists('open', $_GET)) {
    openFileAndStop($m->watches[$_GET['open']]);
}

