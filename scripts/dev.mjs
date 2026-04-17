#!/usr/bin/env node

import { spawn } from "node:child_process";
import { StringDecoder } from "node:string_decoder";

const children = new Map();
let shuttingDown = false;

const processes = [
  {
    name: "broker",
    color: "\x1b[33m",
    command: ".venv/bin/amqtt",
    args: ["-c", "amqtt.yaml"],
  },
  {
    name: "backend",
    color: "\x1b[34m",
    command: ".venv/bin/python",
    args: ["-m", "core.main"],
  },
  {
    name: "frontend",
    color: "\x1b[32m",
    command: "pnpm",
    args: ["--filter", "dashboard", "dev"],
  },
];

function prefixStream(stream, name, color, output) {
  const decoder = new StringDecoder("utf8");
  let buffered = "";

  stream.on("data", (chunk) => {
    buffered += decoder.write(chunk);
    const lines = buffered.split(/\r?\n/);
    buffered = lines.pop() ?? "";

    for (const line of lines) {
      output.write(`${color}[${name}]\x1b[0m ${line}\n`);
    }
  });

  stream.on("end", () => {
    const remainder = buffered + decoder.end();
    if (remainder) {
      output.write(`${color}[${name}]\x1b[0m ${remainder}\n`);
    }
  });
}

function terminateAll(signal = "SIGTERM") {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;
  for (const [name, child] of children) {
    if (child.exitCode !== null || child.signalCode !== null) {
      continue;
    }

    try {
      process.kill(-child.pid, signal);
    } catch (error) {
      if (error.code !== "ESRCH") {
        console.error(`[dev] failed to stop ${name}: ${error.message}`);
      }
    }
  }
}

for (const processConfig of processes) {
  const child = spawn(processConfig.command, processConfig.args, {
    cwd: process.cwd(),
    detached: true,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  children.set(processConfig.name, child);
  prefixStream(child.stdout, processConfig.name, processConfig.color, process.stdout);
  prefixStream(child.stderr, processConfig.name, processConfig.color, process.stderr);

  child.on("exit", (code, signal) => {
    children.delete(processConfig.name);

    if (!shuttingDown) {
      console.error(
        `[dev] ${processConfig.name} exited with ${signal ? `signal ${signal}` : `code ${code}`}`,
      );
      terminateAll("SIGTERM");
      process.exitCode = signal ? 1 : (code ?? 1);
    }
  });

  child.on("error", (error) => {
    console.error(`[dev] failed to start ${processConfig.name}: ${error.message}`);
    terminateAll("SIGTERM");
    process.exitCode = 1;
  });
}

process.on("SIGINT", () => {
  terminateAll("SIGTERM");
});

process.on("SIGTERM", () => {
  terminateAll("SIGTERM");
});

process.on("exit", () => {
  terminateAll("SIGTERM");
});
