import { constants } from "node:fs";
import { access } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(toolsDir, "..");
const [service, ...pythonArgs] = process.argv.slice(2);
const supportedServices = new Set(["api", "worker"]);

if (!supportedServices.has(service) || pythonArgs.length === 0) {
  console.error("Usage: node tools/run-python.mjs <api|worker> <python arguments...>");
  process.exit(2);
}

const pythonRelativePath =
  process.platform === "win32"
    ? ["services", service, ".venv", "Scripts", "python.exe"]
    : ["services", service, ".venv", "bin", "python"];
const python = path.join(workspaceRoot, ...pythonRelativePath);
const sourceRoots = [
  path.join(workspaceRoot, "services", "api"),
  path.join(workspaceRoot, "services", "worker"),
];
const pythonPathKey =
  Object.keys(process.env).find((key) => key.toLowerCase() === "pythonpath") ??
  "PYTHONPATH";
const childEnv = { ...process.env };
childEnv[pythonPathKey] = [...sourceRoots, process.env[pythonPathKey]]
  .filter(Boolean)
  .join(path.delimiter);

try {
  await access(python, constants.X_OK);
} catch {
  console.error(`Python virtual environment is missing or not executable: ${python}`);
  process.exit(1);
}

const child = spawn(python, pythonArgs, {
  cwd: workspaceRoot,
  env: childEnv,
  shell: false,
  stdio: "inherit",
});

child.once("error", (error) => {
  console.error(`Failed to start ${python}: ${error.message}`);
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (signal !== null) {
    console.error(`Python process terminated by signal ${signal}`);
    process.exitCode = 1;
    return;
  }
  process.exitCode = code ?? 1;
});
