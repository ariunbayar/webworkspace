#!/usr/bin/env python3
"""Drive pty_server.py the way a browser would, and check what comes back.

Starts a server of its own on a free port, so it never touches one you are
using, and takes it down again at the end. Stdlib only, like everything else.

Run:  python3 pty_server_test.py
      python3 pty_server_test.py --port N     # test a server already running
"""
import argparse
import base64
import json
import os
import select
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        fail += 1
        print("  FAIL %s  %s" % (name, detail))


def mine(lst, sid):
    """The session under test, not whichever happens to be listed first."""
    return next((x for x in lst.get("sessions", []) if x["id"] == sid), {})


def api(method, path, body=None, origin=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


class WS:
    """A hand-rolled client: select() decides when to read, so a quiet moment
    never poisons the socket the way a timed-out file object does."""

    def __init__(self, path, origin=None):
        self.s = socket.create_connection((HOST, PORT), timeout=5)
        self.buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n" % (path, HOST, PORT, key))
        if origin: req += "Origin: %s\r\n" % origin
        self.s.sendall((req + "\r\n").encode())
        while b"\r\n\r\n" not in self.buf:
            chunk = self.s.recv(65536)
            if not chunk: break
            self.buf += chunk
        head, _, self.buf = self.buf.partition(b"\r\n\r\n")
        self.status = head.split(b"\r\n")[0].decode()

    def _need(self, n, deadline):
        while len(self.buf) < n:
            if time.time() > deadline: return False
            r, _, _ = select.select([self.s], [], [], max(0.02, deadline - time.time()))
            if not r: continue
            chunk = self.s.recv(65536)
            if not chunk: return False
            self.buf += chunk
        return True

    def _take(self, n):
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, payload, opcode=0x2):
        mask = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126: head += bytes([0x80 | n])
        elif n < 65536: head += b"\xfe" + struct.pack(">H", n)
        else: head += b"\xff" + struct.pack(">Q", n)
        self.s.sendall(head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def recv(self, timeout=2.0):
        end = time.time() + timeout
        if not self._need(2, end): return None, None
        b1, b2 = self._take(2)
        n = b2 & 0x7F
        if n == 126:
            if not self._need(2, end): return None, None
            n = struct.unpack(">H", self._take(2))[0]
        elif n == 127:
            if not self._need(8, end): return None, None
            n = struct.unpack(">Q", self._take(8))[0]
        if n and not self._need(n, end): return None, None
        return b1 & 0x0F, self._take(n)

    def drain(self, seconds=1.0, want=None):
        """Collect output until it goes quiet, or until `want` shows up."""
        out, end = b"", time.time() + seconds
        while time.time() < end:
            op, payload = self.recv(min(0.3, max(0.02, end - time.time())))
            if op is None:
                if want and want in out: break
                continue
            if op == 0x2: out += payload
            if want and want in out: break
        return out

    def close(self):
        try: self.s.close()
        except OSError: pass


def run():
    print("1. starting a session")
    code, s1 = api("POST", "/sessions", {"argv": ["/bin/bash", "--norc", "--noprofile", "-i"],
                                         "cols": 100, "rows": 30, "cwd": "/tmp"})
    check("POST /sessions → 201", code == 201, str(s1)[:120])
    check("has a pid", s1.get("pid", 0) > 0, str(s1.get("pid")))
    check("size recorded", (s1.get("cols"), s1.get("rows")) == (100, 30), str(s1)[:80])
    sid = s1["id"]

    print("2. listing")
    code, lst = api("GET", "/sessions")
    check("GET /sessions → 200", code == 200)
    check("the session is listed", any(x["id"] == sid for x in lst.get("sessions", [])))
    check("cwd is where we asked", mine(lst, sid)["cwd"] in ("/tmp", os.path.realpath("/tmp")),
          mine(lst, sid)["cwd"])

    print("3. attaching and typing")
    ws = WS("/attach/" + sid)
    check("handshake → 101", "101" in ws.status, ws.status)
    ws.drain(0.6)
    # the shell has to compute the answer, so what comes back cannot be a
    # stray echo of what was typed
    ws.send(b"echo hello-$((6*7))-from-the-pty\n")
    out = ws.drain(3.0, want=b"hello-42-from-the-pty")
    check("the shell answered", b"hello-42-from-the-pty" in out, repr(out[-120:]))

    print("4. resize reaches the terminal")
    ws.send(json.dumps({"resize": {"cols": 132, "rows": 43}}).encode(), opcode=0x1)
    time.sleep(0.3)
    ws.send(b"stty size\n")
    out = ws.drain(3.0, want=b"43 132")
    check("stty agrees", b"43 132" in out, repr(out[-120:]))
    code, lst = api("GET", "/sessions")
    check("the listing agrees", (mine(lst, sid)["cols"], mine(lst, sid)["rows"]) == (132, 43))

    print("5. what is running, and what it calls itself")
    ws.send(b"printf '\\033]0;a-title-set-by-the-shell\\007'\n")
    time.sleep(0.6)
    code, lst = api("GET", "/sessions")
    check("title read off the stream", mine(lst, sid)["title"] == "a-title-set-by-the-shell",
          repr(mine(lst, sid)["title"]))
    ws.send(b"sleep 4\n")
    time.sleep(0.8)
    code, lst = api("GET", "/sessions")
    check("foreground program named", mine(lst, sid)["running"] == "sleep",
          repr(mine(lst, sid)["running"]))
    ws.send(b"\x03")                      # Ctrl-C, as a real terminal would deliver it
    time.sleep(0.5)
    code, lst = api("GET", "/sessions")
    check("Ctrl-C got back to the shell", mine(lst, sid)["running"] == "bash",
          repr(mine(lst, sid)["running"]))

    print("6. a reload reattaches to the same terminal")
    ws.close()
    time.sleep(0.3)
    ws2 = WS("/attach/" + sid)
    backlog = ws2.drain(1.5, want=b"hello-42-from-the-pty")
    check("scrollback replayed", b"hello-42-from-the-pty" in backlog, repr(backlog[-80:]))
    ws2.send(b"echo still-here\n")
    check("still typeable", b"still-here" in ws2.drain(3.0, want=b"still-here\r\n"))

    print("7. two watchers see the same terminal")
    ws3 = WS("/attach/" + sid)
    ws3.drain(0.8)
    ws2.send(b"echo seen-by-both\n")
    a = ws2.drain(2.5, want=b"seen-by-both\r\n")
    b = ws3.drain(2.5, want=b"seen-by-both\r\n")
    check("first watcher", b"seen-by-both" in a)
    check("second watcher", b"seen-by-both" in b, repr(b[-80:]))
    code, lst = api("GET", "/sessions")
    check("both counted", mine(lst, sid)["watchers"] == 2, str(mine(lst, sid)["watchers"]))
    ws3.close()

    print("8. a page on another site gets nothing")
    code, body = api("GET", "/sessions", origin="http://evil.example")
    check("cross-origin GET refused", code == 403, str(code))
    code, body = api("POST", "/sessions", {}, origin="http://evil.example")
    check("cross-origin POST refused", code == 403, str(code))
    wsx = WS("/attach/" + sid, origin="http://evil.example")
    check("cross-origin websocket refused", "403" in wsx.status, wsx.status)
    wsx.close()
    code, body = api("GET", "/sessions", origin="http://127.0.0.1:8766")
    check("the workspace page is let in", code == 200, str(code))

    print("9. hanging up")
    ws2.close()
    code, body = api("DELETE", "/sessions/" + sid)
    check("DELETE → 200", code == 200 and body.get("closed"), str(body))
    for _ in range(40):                   # SIGHUP first, SIGKILL if it dawdles
        if not os.path.exists("/proc/%d" % s1["pid"]): break
        time.sleep(0.15)
    check("the shell is gone", not os.path.exists("/proc/%d" % s1["pid"]))
    code, lst = api("GET", "/sessions")
    check("and delisted", mine(lst, sid) == {}, str(lst)[:160])
    code, body = api("DELETE", "/sessions/nope")
    check("closing a stranger → 404", code == 404, str(code))

    print("9b. a session that has ended still has its last words")
    code, s2 = api("POST", "/sessions", {"argv": ["/bin/bash", "--norc", "--noprofile", "-i"]})
    dead = s2["id"]
    w = WS("/attach/" + dead)
    w.drain(0.6)
    w.send(b"echo the-last-thing-it-said\n")
    w.drain(3.0, want=b"the-last-thing-it-said")
    w.send(b"exit\n")
    time.sleep(1.0)
    w.close()
    code, lst = api("GET", "/sessions")
    check("it is listed as ended", mine(lst, dead).get("alive") is False, str(mine(lst, dead))[:110])
    check("and remembers where it was working", mine(lst, dead).get("cwd", "") != "",
          repr(mine(lst, dead).get("cwd")))
    back = WS("/attach/" + dead)
    check("attaching to it still works", "101" in back.status, back.status)
    said = back.drain(2.5, want=b"the-last-thing-it-said")
    check("its last words come back", b"the-last-thing-it-said" in said, repr(said[-90:]))
    back.close()
    api("DELETE", "/sessions/" + dead)

    print("10. bad input")
    code, body = api("POST", "/sessions", {"cwd": "/no/such/place"})
    check("nonexistent cwd → 400", code == 400, str(body))
    code, body = api("GET", "/attach/999")
    check("attaching to nothing → 404", code == 404, str(code))



def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    global HOST, PORT, BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, help="test a server already listening here")
    args = ap.parse_args()
    HOST = "127.0.0.1"
    PORT = args.port or free_port()
    BASE = "http://%s:%d" % (HOST, PORT)

    server = None
    if not args.port:
        here = os.path.dirname(os.path.abspath(__file__))
        server = subprocess.Popen([sys.executable, os.path.join(here, "pty_server.py"),
                                   "--port", str(PORT)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        for _ in range(50):                     # wait for it to come up
            try:
                api("GET", "/sessions")
                break
            except OSError:
                time.sleep(0.1)
    try:
        run()
    finally:
        if server:
            os.killpg(os.getpgid(server.pid), signal.SIGTERM)
            server.wait(timeout=5)
    print("\n%d ok, %d failed" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
