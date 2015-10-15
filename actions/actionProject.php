<?php
class actionProject extends actionBase
{
    public function execute()
    {
        $data = [
            'a' => 1,
        ];
        $this->renderJson($data);
    }
}
