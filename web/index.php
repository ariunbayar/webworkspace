<?php
// TODO backup or export redis

ini_set('error_reporting', E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);


require_once(__DIR__ . '/../classes/Application.class.php');
require_once(__DIR__ . '/../classes/Browser.class.php');
require_once(__DIR__ . '/../classes/FileWatch.class.php');
require_once(__DIR__ . '/../classes/Manager.class.php');

require_once(__DIR__ . '/../actions/actionBase.php');
require_once(__DIR__ . '/../actions/actionIndex.php');
require_once(__DIR__ . '/../actions/actionProject.php');
require_once(__DIR__ . '/../actions/actionFile.php');
require_once(__DIR__ . '/../actions/actionHelp.php');

require_once(__DIR__ . '/../helpers/redis.php');


$app = new Application();
$actionFired = $app->dispatch();

if (!$actionFired) {
    return false;  // serves other file if exists
}

?>
