<?php
class actionFileManage extends actionBase
{
    public function execute($action = null)
    {
        $rsp = [
            'isSuccess'=> false,
            'message'  => '',
        ];

        switch ($action) {
            case 'add':
                $filename = $this->getRequestParamPost('filename', '');
                $result = $this->addOrError($filename);
                break;
            case 'move':
                break;
            case 'delete':
                break;
            case 'copy':
                break;
            default:
                $result = 'Invalid request';
        }

        if ($result === true) {
            $rsp['isSuccess'] = true;
        } else {
            $rsp['message'] = $result;
        }

        $this->renderJson($rsp);
    }

    public function addOrError($filename)
    {
        if ($filename[0] != '/') {
            return 'Invalid file or directory';
        }

        $file = Project::getDirectoryOrCWD() . $filename;

        if (file_exists($file)) {
            return 'File or directory already exists';
        }

        # proceed as filename is good
        $isAddingDirectory = substr($file, -1) == '/';
        if ($isAddingDirectory) {
            if (!mkdir($file, 0755, true)) {
                return 'Cannot create directory. Please check permission';
            }
        } else {
            if (!file_exists(dirname($file))) {
                if (!mkdir(dirname($file), 0755, true)) {
                    return 'Cannot create directory for new file. Please check permission';
                }
            }
            if (!touch($file)) {
                return 'Cannot create file. Please check permission';
            }
        }

        return true;
    }
}
