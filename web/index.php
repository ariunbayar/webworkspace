<?php
// TODO backup or export redis

ini_set('error_reporting', E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);


require_once(__DIR__ . '/../classes/Application.class.php');
require_once(__DIR__ . '/../classes/DataStore.class.php');
require_once(__DIR__ . '/../classes/DataStoreFile.class.php');
require_once(__DIR__ . '/../classes/DataStoreRedis.class.php');

require_once(__DIR__ . '/../model/Model.php');
require_once(__DIR__ . '/../model/Help.php');
require_once(__DIR__ . '/../model/Project.php');
require_once(__DIR__ . '/../model/File.php');
require_once(__DIR__ . '/../model/Browser.php');
require_once(__DIR__ . '/../model/BrowserItem.php');

require_once(__DIR__ . '/../actions/actionBase.php');
require_once(__DIR__ . '/../actions/actionIndex.php');
require_once(__DIR__ . '/../actions/actionProject.php');
require_once(__DIR__ . '/../actions/actionFile.php');
require_once(__DIR__ . '/../actions/actionFileOpen.php');
require_once(__DIR__ . '/../actions/actionHelp.php');
require_once(__DIR__ . '/../actions/actionBrowser.php');
require_once(__DIR__ . '/../actions/actionFileManage.php');


$app = new Application();
$actionFired = $app->dispatch();

if (!$actionFired) {
    return false;  // serves other file if exists
}

?>
