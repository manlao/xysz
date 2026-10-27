#!/usr/bin/env node
/* AmazingData MCP connector bootstrap (node side)
   Chain: WorkBuddy -> npx -c "node -e require(bootstrap.js)" -> python bootstrap.py -> server.py
   NOTE: WorkBuddy spawns stdio connectors with cwd = app install dir, so this file
   is located via the connectors-marketplace fixed path, not via cwd. */
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const here = __dirname;
const logDir = path.join(here, "logs");
try { fs.mkdirSync(logDir, { recursive: true }); } catch (e) {}
const probe = path.join(logDir, "spawn_probe.log");
const L = (m) => { try { fs.appendFileSync(probe, m + "\n"); } catch (e) {} };

L("time=" + new Date().toISOString());
L("node=" + process.execPath);
L("cwd=" + process.cwd());
L("here=" + here);

function findPython() {
  const cands = [];
  // 1) WorkBuddy managed python (numeric version desc, e.g. 3.13 > 3.9)
  const root = path.join(os.homedir(), ".workbuddy", "binaries", "python", "versions");
  try {
    const parsed = fs.readdirSync(root)
      .map((d) => {
        const m = d.match(/(\d+)\.(\d+)(?:\.(\d+))?/);
        return m ? { d, v: [+m[1], +m[2], +(m[3] || 0)] } : null;
      })
      .filter(Boolean)
      .sort((a, b) => b.v[0] - a.v[0] || b.v[1] - a.v[1] || b.v[2] - a.v[2]);
    for (const { d } of parsed) {
      const p = path.join(root, d, "python.exe");
      if (fs.existsSync(p)) cands.push(p);
    }
  } catch (e) {}
  // 2) python.exe on PATH
  for (const dir of (process.env.PATH || "").split(";")) {
    if (!dir) continue;
    try {
      const p = path.join(dir, "python.exe");
      if (fs.existsSync(p)) cands.push(p);
    } catch (e) {}
  }
  return cands[0] || null;
}

const py = findPython();
if (!py) {
  L("py_source=NONE");
  process.stderr.write("[AmazingData] Python 3.10+ not found. Install Python and add to PATH, then reconnect.\n");
  process.exit(1);
}
L("py=" + py);

/* ---- lifecycle 子命令（WorkBuddy cli.json preAuth 调度）----
   streamable-http 模式下 WorkBuddy 直连 http://127.0.0.1:8443/mcp，
   本地 server 进程由这些子命令负责拉起/检查/停止。凭证由 WorkBuddy
   token-schema 表单收集、经请求头 X-AD-* 逐请求注入，不由本脚本处理。 */
const MODE = process.argv[2] || "";            // --prepare / --health / --stop
const HTTP_PORT = 8443;

function httpHealthy(timeoutMs) {
  // node 18+ 全局 fetch；仅探测端口是否有 HTTP 响应
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs || 3000);
  return fetch("http://127.0.0.1:" + HTTP_PORT + "/mcp", {
    method: "POST",
    signal: ctl.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 0, method: "ping" }),
  })
    .then((r) => { clearTimeout(t); return true; })
    .catch(() => { clearTimeout(t); return false; });
}

if (MODE === "--prepare") {
  // 1) 装依赖（bootstrap.py 内建幂等，已装则秒级）2) detached 启动 server 3) 健康检查
  const boot = spawn(py, ["-u", path.join(here, "bootstrap.py"), "--deps-only", "--http", String(HTTP_PORT)], {
    cwd: here,
    env: Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8" }),
    stdio: ["ignore", "pipe", "pipe"],
  });
  let tail = "";
  boot.stdout.on("data", (d) => { tail = (tail + d).slice(-4000); });
  boot.stderr.on("data", (d) => { tail = (tail + d).slice(-4000); });
  boot.on("exit", (code) => {
    L("prepare_bootstrap_exit=" + code);
    if (code !== 0) {
      process.stderr.write("[AmazingData] deps bootstrap failed:\n" + tail.slice(-1500) + "\n");
      process.exit(1);
    }
    const srv = spawn(py, ["-u", path.join(here, "server.py"), "--http", String(HTTP_PORT)], {
      cwd: here,
      env: Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8" }),
      detached: true,
      stdio: ["ignore", "ignore", "ignore"],
    });
    srv.unref();
    L("server_detached_pid=" + srv.pid);
    (async function poll() {
      for (let i = 0; i < 40; i++) {
        if (await httpHealthy(2000)) {
          console.log("Logged in");
          process.exit(0);
        }
        await new Promise((r) => setTimeout(r, 500));
      }
      process.stderr.write("[AmazingData] MCP server health check timeout\n");
      process.exit(1);
    })();
  });
} else if (MODE === "--health") {
  (async function poll() {
    for (let i = 0; i < 6; i++) {
      if (await httpHealthy(2000)) {
        console.log("Logged in");
        process.exit(0);
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    console.log("Not logged in");
    process.exit(1);
  })();
} else if (MODE === "--stop") {
  console.log("Logged out");
  process.exit(0);
} else {
  /* ---- 默认：stdio 直通（npx 链路，bootstrap 同步拉起 server）---- */
  L("launching bootstrap.py ...");
  const child = spawn(py, ["-u", path.join(here, "bootstrap.py")], {
    cwd: here,
    env: Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8" }),
    stdio: ["pipe", "pipe", "pipe"],
  });
  process.stdin.pipe(child.stdin);
  child.stdout.pipe(process.stdout);
  child.stderr.pipe(process.stderr);
  child.on("error", (e) => { L("spawn_err=" + e.message); process.exit(1); });
  child.on("exit", (c, s) => { L("bootstrap_exit=" + c + " " + (s || "")); process.exit(c || 0); });
}
