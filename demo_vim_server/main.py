#!/usr/bin/python
"""
    Usage:
        demo_vim_server.py path/to/script.js
"""
import os
import sys
import time
import subprocess

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import cgi

import json


def cmd(*args):
    return subprocess.check_output(args)


def cmd_detach(*args):
    return subprocess.Popen(args)


class Vim:

    def __init__(self, servername):
        self.servername = servername
        self.launch_vim_server()

    def is_vim_server_running(self):
        process_list = cmd('ps', 'aux')
        return process_list.find('gvim --servername %s' % self.servername) > -1

    def launch_vim_server(self):
        time_expire = time.time() + 5

        is_expired = False
        while not is_expired:
            if self.is_vim_server_running():
                break
            else:
                cmd_detach('gvim', '--servername', self.servername)
                time.sleep(0.5)
            is_expired = time.time() > time_expire

        if (not is_expired) and self.servername == 'TMP':
            # intialize settings for non-interaction
            self.vim_set_initials()

    def vimcmd(self, command):
        cmd('vim', '--servername', self.servername, '--remote-send', ":%s<Enter>" % command)

    def vimkey(self, keys):
        cmd('vim', '--servername', self.servername, '--remote-send', keys)

    def vim_set_initials(self):
        self.vimcmd('set guifont=Monospace\ 6')
        self.vimcmd('set shortmess+=A')


class httpHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            self.path = "/index.html"

        if self.path == "/matches":
            self.serve_matches_json()

        try:
            sendReply = False
            if self.path.endswith(".html"):
                mimetype='text/html'
                sendReply = True
            if self.path.endswith(".jpg"):
                mimetype='image/jpg'
                sendReply = True
            if self.path.endswith(".gif"):
                mimetype='image/gif'
                sendReply = True
            if self.path.endswith(".js"):
                mimetype='application/javascript'
                sendReply = True
            if self.path.endswith(".css"):
                mimetype='text/css'
                sendReply = True

            if sendReply == True:
                #Open the static file requested and send it
                f = open(os.curdir + os.sep + self.path)
                self.send_response(200)
                self.send_header('Content-type', mimetype)
                self.end_headers()
                self.wfile.write(f.read())
                f.close()
            return


        except IOError:
            self.send_error(404, 'File Not Found: %s' % self.path)

    def serve_matches_json(self):
        matches = []

        with open('regex') as f:
            regex = f.read()
        output = cmd('ack', '-s', '-H', '--nopager', '--nogroup', regex, filename)
        for line in output.splitlines():
            try:
                filename_dummy, line, text = line.split(':', 3)
            except ValueError:
                continue

            matches.append({'line': line, 'text': text})

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(matches))

    def do_POST(self):
        if self.path=="/line":
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST',
                         'CONTENT_TYPE': self.headers['Content-Type']}
            )

            line = int(form['line'].value)

            self.send_response(200)
            self.end_headers()
            self.wfile.write('got line=%d' % line)

            vim.vimkey("1gt")  # switch to first tab
            vim.vimkey("%dG" % line)  # go to line


vim_tmp = Vim('TMP')
vim = Vim('CURRENT')

# Open the file given as argument
filename = os.path.abspath(sys.argv[1])

vim.vimkey("1gt")  # switch to first tab
vim.vimcmd("e %s" % filename)

vim_tmp.vimcmd("e %s" % filename)


try:
    PORT_NUMBER = 8080
    server = HTTPServer(('', PORT_NUMBER), httpHandler)
    print 'Started httpserver on port ', PORT_NUMBER
    server.serve_forever()

except KeyboardInterrupt:
    print '^C received, shutting down the web server'
    server.socket.close()

