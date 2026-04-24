module.exports = {
  apps: [
    {
      name: "autochecklist-backend",
      cwd: "/data00/home/mayuanli.233/AutoChecklist",
      script: "/home/mayuanli.233/.local/bin/uv",
      args: [
        "run",
        "--env-file",
        ".env",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
      ],
      interpreter: "none",
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
