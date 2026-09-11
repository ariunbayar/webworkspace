#!/usr/bin/env python3
"""Terminals the browser can hold on to — one PTY per session, stdlib only.

A browser cannot start a shell; a page has no way in. So this holds the fake
terminals instead: it starts a shell on one, streams what the shell prints to
whoever is attached, and writes back what they type. The PTY lives here rather
than in the tab, so a reload reattaches to the session it left instead of
killing it.

Run:  python3 pty_server.py              # then http://127.0.0.1:8767/sessions
      python3 pty_server.py --port N

  GET    /sessions          every session, and what is running in it
  POST   /sessions          start one: {"cwd":…, "argv":[…], "cols":…, "rows":…}
  POST   /sessions/<id>/resize   {"cols":…, "rows":…}
  DELETE /sessions/<id>     hang it up
  GET    /attach/<id>       WebSocket: binary frames are terminal bytes both
                            ways, text frames are JSON control messages

Shells are the whole point, so the door is only ever open to this machine:
--host must be a loopback address unless you say --allow-remote and mean it.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import pty
import re
import signal
import struct
import sys
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8767
SCROLLBACK = 256 * 1024   # bytes kept per session, enough to redraw a full screen
MAX_SESSIONS = 32
KEEP_DEAD = 600           # seconds a finished session stays readable
READ_CHUNK = 65536


# ---- sessions -------------------------------------------------------------

def _set_size(fd, cols, rows):
    # the kernel keeps the window size on the terminal itself, and tells the
    # foreground program it changed by raising SIGWINCH — which is how a shell
    # learns to rewrap without anybody asking it
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


# a terminal's title is set by the program running in it, with an escape
# sequence rather than any kind of property: OSC 0/1/2, terminated by BEL or
# ST. Reading it is how we know a session is running vim without asking.
_OSC = re.compile(rb"\x1b\][012];([^\x07\x1b]{0,256})(?:\x07|\x1b\\)")


class Session:
    """One shell on one pseudo-terminal, plus everyone watching it."""

    def __init__(self, sid, argv, cwd, cols, rows):
        self.id = sid
        self.argv = argv
        self.cols, self.rows = cols, rows
        self.started = time.time()
        self.ended = None
        self.title = ""
        self.exit = None
        self.buf = bytearray()          # scrollback, so a reload can catch up
        self.clients = set()            # WSConn, everyone attached right now
        self.lock = threading.Lock()
        self._tail = b""                # a title sequence split across two reads

        # After a fork, a process holding threads may only do what is safe to do
        # in a signal handler until it execs — and setting an environment
        # variable is not on that list, since it can want the allocator's lock
        # while another thread is holding it. So the environment is finished
        # here, on the near side of the fork, and handed to exec as a whole.
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"
        # the terminal knows its own size; a stale copy in the environment
        # would only contradict it
        env.pop("COLUMNS", None)
        env.pop("LINES", None)

        pid, fd = pty.fork()
        if pid == 0:                    # the child is the shell, and never returns
            try:
                # A signal that was ignored when this server started stays
                # ignored through fork and exec, and a shell cannot undo one it
                # inherited — so a server launched in the background would hand
                # every terminal it opens a Ctrl-C that does nothing, and a
                # SIGPIPE that makes `head` in a pipeline misbehave. A terminal
                # owes its program a clean slate.
                for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM,
                            signal.SIGHUP, signal.SIGPIPE, signal.SIGTSTP,
                            signal.SIGTTIN, signal.SIGTTOU, signal.SIGCHLD):
                    signal.signal(sig, signal.SIG_DFL)
                signal.pthread_sigmask(signal.SIG_SETMASK, set())
                os.chdir(cwd)
                os.execvpe(argv[0], argv, env)
            except Exception as e:      # exec failed: say so on the terminal itself
                os.write(2, ("pty_server: cannot run %s: %s\r\n" % (argv[0], e)).encode())
            os._exit(127)

        self.pid, self.fd = pid, fd
        _set_size(fd, cols, rows)
        threading.Thread(target=self._pump, daemon=True).start()

    # ---- what the shell says ----------------------------------------------

    def _pump(self):
        """Read the terminal forever, keep a tail of it, hand it to watchers."""
        while True:
            try:
                data = os.read(self.fd, READ_CHUNK)
            except OSError:
                break            # the last process to close a PTY reads as EIO, not EOF
            if not data:
                break
            self._note_title(data)
            with self.lock:
                self.buf += data
                if len(self.buf) > SCROLLBACK:
                    self._trim()
                watchers = list(self.clients)
            for c in watchers:
                c.send(data)
        self._reap()

    def _trim(self):
        """Drop the oldest scrollback, preferably at the start of a line.

        Cutting blind can land in the middle of an escape sequence, and half a
        sequence replayed into a fresh terminal is worse than a missing line —
        so the cut is nudged forward to just after a newline when one is close.
        """
        cut = len(self.buf) - SCROLLBACK
        nl = self.buf.find(b"\n", cut, cut + 4096)
        del self.buf[:nl + 1 if nl >= 0 else cut]

    def _note_title(self, data):
        # a sequence can be split across two reads, so the tail of the last one
        # is rescanned with this one
        found = _OSC.findall(self._tail + data)
        if found:
            self.title = found[-1].decode("utf-8", "replace")
        self._tail = data[-300:]

    def _reap(self):
        try:
            _, status = os.waitpid(self.pid, 0)
            self.exit = os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            self.exit = self.exit if self.exit is not None else -1
        self.ended = time.time()
        try:
            os.close(self.fd)
        except OSError:
            pass
        for c in list(self.clients):
            c.close(1000, "session ended")

    # ---- what is actually running in it -----------------------------------

    def _foreground(self):
        """The process group the terminal is currently listening to.

        This is the honest answer to "what is this terminal", the one X could
        never give: not the shell that owns the PTY but whatever it is running
        right now, and the directory that program is sitting in.
        """
        try:
            pgid = os.tcgetpgrp(self.fd)
        except OSError:
            return "", ""
        try:
            with open("/proc/%d/comm" % pgid) as f:
                comm = f.read().strip()
        except OSError:
            comm = ""
        try:
            cwd = os.readlink("/proc/%d/cwd" % pgid)
        except OSError:
            cwd = ""
        return comm, cwd

    def alive(self):
        return self.exit is None

    def info(self):
        comm, cwd = self._foreground() if self.alive() else ("", "")
        with self.lock:
            size = len(self.buf)
        return {
            "id": self.id,
            "argv": self.argv,
            "pid": self.pid,
            "title": self.title,
            "running": comm,
            "cwd": cwd,
            "cols": self.cols, "rows": self.rows,
            "started": round(self.started, 3),
            "age": round(time.time() - self.started, 1),
            "alive": self.alive(),
            "exit": self.exit,
            "ended": round(self.ended, 3) if self.ended else None,
            "scrollback": size,
            "watchers": len(self.clients),
        }

    # ---- being driven ------------------------------------------------------

    def write(self, data):
        if self.alive():
            try:
                os.write(self.fd, data)
            except OSError:
                pass

    def resize(self, cols, rows):
        self.cols, self.rows = cols, rows
        if self.alive():
            try:
                _set_size(self.fd, cols, rows)
            except OSError:
                pass

    def attach(self, conn):
        with self.lock:
            self.clients.add(conn)
            return bytes(self.buf)      # catch the newcomer up before anything else

    def detach(self, conn):
        with self.lock:
            self.clients.discard(conn)

    def hangup(self):
        """What closing a terminal window does: SIGHUP, and let go."""
        if not self.alive():
            return
        try:
            os.killpg(os.getpgid(self.pid), signal.SIGHUP)
        except OSError:
            return
        # closing a terminal window is a request, not a negotiation: anything
        # still there in a moment is taken down. The timer is a daemon, so
        # waiting on it is never what keeps the program from exiting.
        later = threading.Timer(3.0, self.kill)
        later.daemon = True
        later.start()

    def kill(self):
        if not self.alive():
            return
        try:
            os.killpg(os.getpgid(self.pid), signal.SIGKILL)
        except OSError:
            pass


class Sessions:
    def __init__(self, shell, max_sessions):
        self.shell = shell
        self.max = max_sessions
        self.by_id = {}
        self.next_id = 1
        self.lock = threading.Lock()

    def start(self, argv=None, cwd=None, cols=80, rows=24):
        argv = argv or [self.shell]
        cwd = cwd or os.path.expanduser("~")
        if not os.path.isdir(cwd):
            raise ValueError("no such directory: %s" % cwd)
        with self.lock:
            living = sum(1 for s in self.by_id.values() if s.alive())
            if living >= self.max:
                raise ValueError("%d sessions already running (--max-sessions)" % living)
            sid = str(self.next_id)
            self.next_id += 1
            s = Session(sid, argv, cwd, cols, rows)
            self.by_id[sid] = s
        return s

    def get(self, sid):
        return self.by_id.get(sid)

    def drop(self, sid):
        s = self.by_id.get(sid)
        if not s:
            return False
        s.hangup()
        with self.lock:
            # a dead session is kept until somebody asks for it to go, so its
            # last words stay readable
            self.by_id.pop(sid, None)
        return True

    def all(self):
        return [s.info() for s in list(self.by_id.values())]

    def sweep(self):
        """A finished session stays listed so its last words can be read, but
        it is still a shell's worth of scrollback: once nobody has looked at it
        for a while, let it go."""
        while True:
            time.sleep(30)
            for sid, s in list(self.by_id.items()):
                if (not s.alive() and not s.clients and s.ended
                        and time.time() - s.ended > KEEP_DEAD):
                    self.by_id.pop(sid, None)


# ---- websocket ------------------------------------------------------------
# Enough of RFC 6455 to carry a terminal: no extensions, no compression, and
# fragments only because a browser is entitled to send them.

GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


def accept_key(key):
    return base64.b64encode(hashlib.sha1(key.encode() + GUID).digest()).decode()


def frame(opcode, payload):
    """One unfragmented frame, server to client, never masked."""
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += b"\x7e" + struct.pack(">H", n)
    else:
        head += b"\x7f" + struct.pack(">Q", n)
    return head + payload


class WSConn:
    """One attached browser. Writes are serialised; reads run on its thread."""

    def __init__(self, sock, wfile, rfile):
        self.sock, self.wfile, self.rfile = sock, wfile, rfile
        self.wlock = threading.Lock()
        self.open = True

    def _write(self, data):
        with self.wlock:
            if not self.open:
                return
            try:
                self.wfile.write(data)
                self.wfile.flush()
            except (OSError, ValueError):
                self.open = False

    def send(self, payload):
        self._write(frame(OP_BIN, payload))

    def send_json(self, obj):
        self._write(frame(OP_TEXT, json.dumps(obj).encode()))

    def close(self, code=1000, reason=""):
        self._write(frame(OP_CLOSE, struct.pack(">H", code) + reason.encode()[:120]))
        self.open = False
        try:
            self.sock.shutdown(2)
        except OSError:
            pass

    def _exact(self, n):
        data = self.rfile.read(n)
        if data is None or len(data) < n:
            raise ConnectionError("short read")
        return data

    def read(self):
        """Next complete message as (opcode, bytes), or None when it hangs up."""
        payload, first = b"", None
        while True:
            try:
                b1, b2 = self._exact(2)
            except (ConnectionError, OSError):
                return None
            fin, opcode, masked, n = b1 & 0x80, b1 & 0x0F, b2 & 0x80, b2 & 0x7F
            try:
                if n == 126:
                    n = struct.unpack(">H", self._exact(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self._exact(8))[0]
                if n > 8 << 20:                 # nobody types eight megabytes
                    return None
                mask = self._exact(4) if masked else None
                chunk = self._exact(n) if n else b""
            except (ConnectionError, OSError):
                return None
            if mask:
                chunk = bytes(c ^ mask[i % 4] for i, c in enumerate(chunk))
            if opcode == OP_CLOSE:
                return None
            if opcode == OP_PING:
                self._write(frame(OP_PONG, chunk))
                continue
            if opcode == OP_PONG:
                continue
            if first is None:
                first = opcode
            payload += chunk
            if fin:
                return first, payload


# ---- server ---------------------------------------------------------------

LOOPBACK = ("127.0.0.1", "localhost", "[::1]", "::1")


def local_origin(origin):
    """A WebSocket is not stopped by the same-origin policy, and any page in
    the browser can dial localhost. So a cross-origin handshake is refused: a
    site you happen to be reading does not get a shell on this machine."""
    if not origin:
        return True                     # curl, and anything else without a page
    host = origin.split("//", 1)[-1].split("/")[0]
    if host.startswith("["):            # [::1], with or without a port
        host = host[:host.find("]") + 1]
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    return host in LOOPBACK


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    sessions = None                     # set in main()

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            raise ValueError("body is not JSON")

    def _guard(self):
        if local_origin(self.headers.get("Origin")):
            return True
        self._send({"error": "cross-origin requests are refused"}, code=403)
        return False

    # ---- routes -----------------------------------------------------------

    def do_GET(self):
        if not self._guard():
            return
        if self.path == "/sessions":
            return self._send({"sessions": self.sessions.all()})
        if self.path.startswith("/attach/"):
            return self.attach(self.path[len("/attach/"):].split("?")[0])
        if self.path in ("/", "/index.html"):
            return self._send({
                "what": "terminals, held open for the browser",
                "sessions": "/sessions", "attach": "/attach/<id> (websocket)",
            })
        self._send({"error": "not found"}, code=404)

    def do_POST(self):
        if not self._guard():
            return
        try:
            body = self._body()
        except ValueError as e:
            return self._send({"error": str(e)}, code=400)

        if self.path == "/sessions":
            try:
                s = self.sessions.start(argv=body.get("argv"), cwd=body.get("cwd"),
                                        cols=int(body.get("cols", 80)),
                                        rows=int(body.get("rows", 24)))
            except (ValueError, OSError) as e:
                return self._send({"error": str(e)}, code=400)
            return self._send(s.info(), code=201)

        if self.path.endswith("/resize"):
            s = self.sessions.get(self.path.split("/")[2])
            if not s:
                return self._send({"error": "no such session"}, code=404)
            try:
                s.resize(int(body["cols"]), int(body["rows"]))
            except (KeyError, ValueError, TypeError):
                return self._send({"error": "want {cols, rows}"}, code=400)
            return self._send(s.info())

        self._send({"error": "not found"}, code=404)

    def do_DELETE(self):
        if not self._guard():
            return
        if self.path.startswith("/sessions/"):
            closed = self.sessions.drop(self.path[len("/sessions/"):])
            return self._send({"closed": closed}, code=200 if closed else 404)
        self._send({"error": "not found"}, code=404)

    # ---- attaching --------------------------------------------------------

    def attach(self, sid):
        s = self.sessions.get(sid)
        key = self.headers.get("Sec-WebSocket-Key")
        if not s:
            return self._send({"error": "no such session"}, code=404)
        if not key or "websocket" not in (self.headers.get("Upgrade") or "").lower():
            return self._send({"error": "/attach wants a websocket"}, code=426)
        if not s.alive():
            return self._send({"error": "that session has ended"}, code=410)

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_key(key))
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True    # this socket is no longer HTTP's to reuse

        conn = WSConn(self.connection, self.wfile, self.rfile)
        backlog = s.attach(conn)
        try:
            # everything said before you arrived, so the terminal draws itself
            if backlog:
                conn.send(backlog)
            conn.send_json({"session": s.info()})
            while True:
                msg = conn.read()
                if msg is None:
                    break
                opcode, payload = msg
                if opcode == OP_BIN:
                    s.write(payload)            # keystrokes, as typed
                elif opcode == OP_TEXT:
                    self._control(s, conn, payload)
        finally:
            s.detach(conn)
            conn.open = False

    @staticmethod
    def _control(s, conn, payload):
        """Text frames are for talking about the terminal, not typing into it."""
        try:
            msg = json.loads(payload)
        except (ValueError, json.JSONDecodeError):
            return
        if "resize" in msg:
            try:
                s.resize(int(msg["resize"]["cols"]), int(msg["resize"]["rows"]))
            except (KeyError, ValueError, TypeError):
                return
            conn.send_json({"session": s.info()})


# ---- serving --------------------------------------------------------------

def serve(host="127.0.0.1", port=DEFAULT_PORT, shell=None, max_sessions=MAX_SESSIONS):
    """Start the terminal server on threads of its own and hand it back.

    Whoever calls this owns it — `winlist_server.py` runs it inside itself so
    there is one program to start and one to stop, and `main()` below runs it
    the same way and then simply waits. Raises OSError if the port is taken,
    which usually means one of these is already running there.
    """
    Handler.sessions = Sessions(shell or os.environ.get("SHELL", "/bin/bash"), max_sessions)
    threading.Thread(target=Handler.sessions.sweep, daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def stop(srv, grace=2.0):
    """Shut the door, and hang up on everything still inside.

    A shell outliving the thing that started it is exactly what a terminal
    emulator is supposed to prevent, so this is not optional tidying — and it
    finishes before this returns rather than on a timer somebody might not wait
    for. A shell that goes quietly costs nothing; one that will not go is given
    `grace` seconds and then killed.
    """
    srv.shutdown()
    srv.server_close()
    sessions = list(Handler.sessions.by_id.values())
    for s in sessions:
        Handler.sessions.drop(s.id)
    deadline = time.time() + grace
    for s in sessions:
        while s.alive() and time.time() < deadline:
            time.sleep(0.02)
        s.kill()


# ---- main -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="terminals held open for the browser")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--shell", default=os.environ.get("SHELL", "/bin/bash"),
                    help="what a new session runs (default $SHELL)")
    ap.add_argument("--max-sessions", type=int, default=MAX_SESSIONS, metavar="N",
                    help="how many may run at once (default %d)" % MAX_SESSIONS)
    ap.add_argument("--allow-remote", action="store_true",
                    help="really listen off this machine — every visitor gets a shell")
    args = ap.parse_args()

    if args.host not in LOOPBACK and not args.allow_remote:
        sys.exit("refusing to listen on %s: anyone who can reach it gets a shell here.\n"
                 "Say --allow-remote if that is genuinely what you want." % args.host)

    try:
        srv = serve(args.host, args.port, args.shell, args.max_sessions)
    except OSError as e:
        sys.exit("cannot listen on %s:%d (%s) — another pty_server is probably "
                 "already running" % (args.host, args.port, e))
    print("pty → http://%s:%d/sessions  running %s  (Ctrl-C to stop)"
          % (args.host, args.port, args.shell))
    try:
        threading.Event().wait()        # the serving happens on its own thread
    except KeyboardInterrupt:
        print("\nbye")
        stop(srv)


if __name__ == "__main__":
    main()
