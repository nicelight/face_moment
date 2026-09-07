import { readdir } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const clientTestsDirectory = path.join(projectRoot, "tests", "client");
const entries = await readdir(clientTestsDirectory, { withFileTypes: true });
const testFiles = entries
  .filter(
    (entry) =>
      entry.isFile() &&
      /^test_.*\.mjs$/.test(entry.name) &&
      !entry.name.endsWith(".spec.mjs"),
  )
  .map((entry) => path.join(clientTestsDirectory, entry.name))
  .sort();

if (testFiles.length === 0) {
  throw new Error("No client unit tests found");
}

const child = spawn(process.execPath, ["--test", ...testFiles], {
  cwd: projectRoot,
  stdio: "inherit",
});

child.on("error", (error) => {
  throw error;
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exitCode = code ?? 1;
});
