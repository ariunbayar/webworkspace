#!/usr/bin/env python3
"""Local resource monitor — live web dashboard, stdlib only.

Run:  python3 resmon_server.py           # then open http://localhost:8765
      python3 resmon_server.py --port N  # custom port
"""
import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- sampling -------------------------------------------------------------

_prev_cpu = {}  # holds last /proc/stat snapshot for %-delta computation


def _read_cpu():
    """Return (total_pct, [per_core_pct]) using a delta vs the last call."""
    out = []
    with open("/proc/stat") as f:
        lines = [l for l in f if l.startswith("cpu")]
    result_total = 0.0
    per_core = []
    for line in lines:
        parts = line.split()
        name = parts[0]
        vals = list(map(int, parts[1:8]))  # user nice sys idle iowait irq softirq
        idle = vals[3] + vals[4]
        total = sum(vals)
        p_idle, p_total = _prev_cpu.get(name, (idle, total))
        dt = total - p_total
        di = idle - p_idle
        pct = 0.0 if dt <= 0 else max(0.0, min(100.0, 100.0 * (dt - di) / dt))
        _prev_cpu[name] = (idle, total)
        if name == "cpu":
            result_total = pct
        else:
            per_core.append(round(pct, 1))
    return round(result_total, 1), per_core


def _read_mem():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, rest = line.partition(":")
            info[k] = int(rest.split()[0])  # kB
    total = info["MemTotal"]
    avail = info.get("MemAvailable", info["MemFree"])
    used = total - avail
    swap_total = info.get("SwapTotal", 0)
    swap_used = swap_total - info.get("SwapFree", 0)
    return {
        "used_mb": round(used / 1024),
        "total_mb": round(total / 1024),
        "pct": round(100.0 * used / total, 1) if total else 0.0,
        "swap_used_mb": round(swap_used / 1024),
        "swap_total_mb": round(swap_total / 1024),
    }


def _read_load():
    with open("/proc/loadavg") as f:
        a, b, c = f.read().split()[:3]
    return [float(a), float(b), float(c)]


def _top_procs(n=8):
    """Top-n processes by CPU via a self-contained /proc walk (two samples)."""
    def snapshot():
        snap = {}
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/stat") as f:
                    parts = f.read().rsplit(") ", 1)[1].split()
                utime, stime = int(parts[11]), int(parts[12])
                with open(f"/proc/{pid}/comm") as f:
                    comm = f.read().strip()
                snap[pid] = (utime + stime, comm)
            except (IOError, IndexError, ValueError):
                continue
        return snap

    s1 = snapshot()
    time.sleep(0.15)
    s2 = snapshot()
    clk = os.sysconf("SC_CLK_TCK")
    ncpu = os.cpu_count() or 1
    rows = []
    for pid, (t2, comm) in s2.items():
        if pid in s1:
            dt = t2 - s1[pid][0]
            pct = 100.0 * (dt / clk) / 0.15 / ncpu
            if pct > 0.1:
                rows.append({"pid": pid, "name": comm, "cpu": round(pct, 1)})
    rows.sort(key=lambda r: r["cpu"], reverse=True)
    return rows[:n]


def sample():
    cpu_total, per_core = _read_cpu()
    return {
        "t": time.time(),
        "cpu": cpu_total,
        "cores": per_core,
        "ncpu": os.cpu_count(),
        "mem": _read_mem(),
        "load": _read_load(),
        "procs": _top_procs(),
    }


# ---- web ------------------------------------------------------------------

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>resmon</title>
<style>
  :root{color-scheme:light dark}
  body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px;
       background:#0e1116;color:#e6edf3}
  h1{font-size:16px;margin:0 0 12px;font-weight:600}
  .row{display:flex;gap:16px;flex-wrap:wrap}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;
        padding:12px 14px;flex:1;min-width:220px}
  .big{font-size:28px;font-weight:600}
  .sub{color:#8b949e;font-size:12px}
  canvas{width:100%;height:60px;display:block;margin-top:6px}
  table{width:100%;border-collapse:collapse;margin-top:6px;font-size:13px}
  td{padding:2px 4px;border-bottom:1px solid #21262d}
  td.n{text-align:right;color:#58a6ff;font-variant-numeric:tabular-nums}
  .bar{height:4px;background:#238636;border-radius:2px;margin-top:8px}
</style></head><body>
<h1>Local resource monitor <span class=sub id=host></span></h1>
<div class=row>
  <div class=card><div class=sub>CPU</div><div class=big id=cpu>–</div>
    <div class=bar id=cpubar style=width:0></div>
    <canvas id=cpuc></canvas></div>
  <div class=card><div class=sub>Memory</div><div class=big id=mem>–</div>
    <div class=sub id=memsub></div><canvas id=memc></canvas></div>
  <div class=card><div class=sub>Load avg (1/5/15m)</div><div class=big id=load>–</div>
    <div class=sub id=cores></div></div>
</div>
<div class=card style=margin-top:16px>
  <div class=sub>Top processes by CPU</div>
  <table id=procs></table>
</div>
<script>
const HIST=90;               // ~3 min at 2s poll
let cpuH=[], memH=[];
function draw(cv,data,max,color){
  const dpr=devicePixelRatio||1, w=cv.clientWidth, h=cv.clientHeight;
  cv.width=w*dpr; cv.height=h*dpr; const g=cv.getContext('2d');
  g.scale(dpr,dpr); g.clearRect(0,0,w,h); g.strokeStyle=color; g.lineWidth=1.5;
  g.beginPath();
  data.forEach((v,i)=>{const x=w*i/(HIST-1), y=h-(v/max)*h;
    i?g.lineTo(x,y):g.moveTo(x,y);});
  g.stroke();
}
async function tick(){
  let d; try{ d=await (await fetch('/metrics')).json(); }catch(e){ return; }
  document.getElementById('cpu').textContent=d.cpu+'%';
  document.getElementById('cpubar').style.width=d.cpu+'%';
  const m=d.mem;
  document.getElementById('mem').textContent=m.pct+'%';
  document.getElementById('memsub').textContent=
    (m.used_mb/1024).toFixed(1)+' / '+(m.total_mb/1024).toFixed(1)+' GB'+
    (m.swap_total_mb? '  ·  swap '+(m.swap_used_mb/1024).toFixed(1)+' GB':'');
  document.getElementById('load').textContent=d.load.map(x=>x.toFixed(2)).join(' ');
  document.getElementById('cores').textContent=d.ncpu+' cores';
  document.getElementById('host').textContent='· '+d.ncpu+' cores';
  cpuH.push(d.cpu); memH.push(m.pct);
  if(cpuH.length>HIST){cpuH.shift();memH.shift();}
  draw(document.getElementById('cpuc'),cpuH,100,'#58a6ff');
  draw(document.getElementById('memc'),memH,100,'#3fb950');
  document.getElementById('procs').innerHTML=d.procs.map(p=>
    '<tr><td>'+p.name+'</td><td class=sub>'+p.pid+
    '</td><td class=n>'+p.cpu+'%</td></tr>').join('');
}
tick(); setInterval(tick,2000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # quiet

    def do_GET(self):
        if self.path == "/metrics":
            body = json.dumps(sample()).encode()
            ctype = "application/json"
        else:
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    _read_cpu()  # prime the CPU delta baseline
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"resmon → http://{args.host}:{args.port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
