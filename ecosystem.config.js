// PM2 process definitions for the ReasoningReceipt backend.
//
// Scope: the always-on, low-cost services only — the FastAPI API server and the
// Cloudflare tunnel that fronts it. Both are pointed straight at the project
// virtualenv / cloudflared binary (no `uv run` wrapper) so PM2 owns the real
// process and can stop/restart it cleanly without orphaning a child.
//
// The agent.loop daemon is intentionally NOT managed here. It runs on a bounded
// daily schedule (scheduled task `rrtrace-daemon-daily`, ~1h/day) to cap the
// Gemini ensemble bill; running it continuously would multiply that cost.
//
// Start:    pm2 start ecosystem.config.js
// Persist:  pm2 save   (snapshot restored on reboot by the logon task)
// Status:   pm2 ls / pm2 logs rr-server / pm2 logs rr-tunnel

const repo = "C:\\Users\\tangm\\Documents\\GitHub\\reasoning-receipt";
const venv = repo + "\\.venv\\Scripts";
const logs = repo + "\\tmp\\services";

module.exports = {
  apps: [
    {
      name: "rr-server",
      script: venv + "\\uvicorn.exe",
      args: "server.main:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      cwd: repo,
      autorestart: true,
      max_restarts: 30,
      restart_delay: 3000,
      time: true,
      out_file: logs + "\\pm2-server.out.log",
      error_file: logs + "\\pm2-server.err.log",
    },
    {
      name: "rr-tunnel",
      script: "C:\\Program Files (x86)\\cloudflared\\cloudflared.exe",
      args: "tunnel run rrtrace",
      interpreter: "none",
      cwd: repo,
      autorestart: true,
      max_restarts: 60,
      restart_delay: 3000,
      time: true,
      out_file: logs + "\\pm2-tunnel.out.log",
      error_file: logs + "\\pm2-tunnel.err.log",
    },
  ],
};
