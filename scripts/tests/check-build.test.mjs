import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readFile, readdir, symlink, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { prepareBuild, buildEnvironment, removeBuild, runBuild } from "../check-build.mjs";
const INPUTS = ["package.json", "package-lock.json", "tsconfig.json", "src/page.tsx"];

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), "dashboard-ci-input-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, "src"));
  await writeFile(path.join(root, "src/page.tsx"), "export default function Page() { return null; }");
  for (const name of ["package.json", "package-lock.json", "tsconfig.json"]) {
    await writeFile(path.join(root, name), "{}");
  }
  return root;
}

test("export excludes private files and every existing install/build cache", async t => {
  const root = await fixture(t);
  for (const name of [".env", ".env.local", "ssl", "node_modules", ".next", ".claude"]) {
    if (name.startsWith(".env")) await writeFile(path.join(root, name), "REAL_TEST_SECRET=never-copy");
    else { await mkdir(path.join(root, name)); await writeFile(path.join(root, name, "private"), "never-copy"); }
  }
  await writeFile(path.join(root, "src/.env.production"), "never-copy");
  await mkdir(path.join(root, "src/node_modules"));
  await writeFile(path.join(root, "src/node_modules/private"), "never-copy");
  await writeFile(path.join(root, "src/unreviewed.ts"), "never-copy");
  const prepared = await prepareBuild(root, os.tmpdir(), INPUTS);
  t.after(() => removeBuild(prepared));
  assert.deepEqual((await readdir(prepared.directory)).sort(),
    [".dashboard-ci-build-owner", "empty-global-npmrc", "empty-user-npmrc", "package-lock.json", "package.json", "src", "tsconfig.json"]);
  assert.deepEqual(await readdir(path.join(prepared.directory, "src")), ["page.tsx"]);
  assert.equal(prepared.counts.files, 4);
  assert.equal(await readFile(path.join(prepared.directory, "src/page.tsx"), "utf8"),
    "export default function Page() { return null; }");
});

test("allowlisted source cannot escape through a symbolic link", async t => {
  const root = await fixture(t);
  await writeFile(path.join(root, "private"), "never-copy");
  await symlink(path.join(root, "private"), path.join(root, "src/leak.ts"));
  await assert.rejects(prepareBuild(root, os.tmpdir(), [...INPUTS, "src/leak.ts"]), /symbolic links/);
  await assert.rejects(prepareBuild(root, os.tmpdir(), [...INPUTS, "src/.env.production"]), /Private or generated/);
});

test("build subprocess receives only fake app settings and owned npm paths", () => {
  const env = buildEnvironment("/tmp/dashboard-owned-test", {
    PATH: "/test/bin", LANG: "C", HOME: "/real-home", VERCEL_TOKEN: "never-copy",
    SUPABASE_SERVICE_ROLE_KEY: "never-copy", NEXT_PUBLIC_SUPABASE_URL: "https://real.example",
    NEXT_PUBLIC_VN_API_URL: "https://real-worker.example", RAILWAY_TOKEN: "never-copy",
    NODE_OPTIONS: "--require malicious.cjs", NPM_CONFIG_USERCONFIG: "/real-home/.npmrc",
    NPM_CONFIG_MAXSOCKETS: "999",
  });
  assert.equal(env.PATH, "/test/bin");
  assert.equal(env.NEXT_PUBLIC_SUPABASE_URL, "https://dashboard-ci.invalid");
  assert.equal(env.NPM_CONFIG_USERCONFIG, "/tmp/dashboard-owned-test/empty-user-npmrc");
  assert.equal(env.NPM_CONFIG_GLOBALCONFIG, "/tmp/dashboard-owned-test/empty-global-npmrc");
  assert.equal(env.NPM_CONFIG_MAXSOCKETS, "4");
  assert.equal(env.SUPABASE_SERVICE_ROLE_KEY, "dashboard-ci-fake-secret-with-no-access");
  assert.equal(Object.values(env).some(value => value.includes("never-copy")), false);
  for (const key of ["HOME", "VERCEL_TOKEN", "RAILWAY_TOKEN", "NODE_OPTIONS", "NEXT_PUBLIC_VN_API_URL"]) {
    assert.equal(Object.hasOwn(env, key), false);
  }
});

test("real build boundary uses a new install, literal arguments and no shell", async t => {
  const root = await fixture(t);
  const prepared = await prepareBuild(root, os.tmpdir(), INPUTS);
  t.after(() => removeBuild(prepared));
  const calls = [];
  await runBuild(prepared, (command, args, options) => {
    calls.push({ command, args, options }); return { status: 0 };
  });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].args, ["ci", "--include=dev", "--ignore-scripts", "--no-audit", "--no-fund"]);
  assert.equal(calls[1].args[0], path.join(prepared.directory, "node_modules/next/dist/bin/next"));
  for (const call of calls) {
    assert.equal(call.options.cwd, prepared.directory);
    assert.equal(call.options.shell, false);
    assert.equal(call.options.env.NEXT_PUBLIC_SUPABASE_URL, "https://dashboard-ci.invalid");
    assert.equal(call.options.env.NPM_CONFIG_MAXSOCKETS, "4");
    assert.ok(call.options.timeout > 0 && call.options.timeout <= 600_000);
  }
});

test("production build installation explicitly retains required development tools", async t => {
  const root = await fixture(t);
  await writeFile(path.join(root, "package.json"), JSON.stringify({
    devDependencies: { "@tailwindcss/postcss": "4.3.3", typescript: "5.9.3" },
  }));
  const prepared = await prepareBuild(root, os.tmpdir(), INPUTS);
  t.after(() => removeBuild(prepared));
  let installedBuildTools = false;
  await runBuild(prepared, (command, args, options) => {
    if (command === "npm") {
      assert.equal(options.env.NODE_ENV, "production");
      // npm omits dev by default under NODE_ENV=production; include must override it.
      installedBuildTools = args.includes("--include=dev");
    } else {
      assert.equal(installedBuildTools, true, "Tailwind/PostCSS and other build tools must be present before Next build");
    }
    return { status: 0 };
  });
});

test("failure never proceeds to a build and cleanup refuses foreign ownership", async t => {
  const root = await fixture(t);
  const prepared = await prepareBuild(root, os.tmpdir(), INPUTS);
  let calls = 0;
  await assert.rejects(runBuild(prepared, () => { calls++; return { status: 1 }; }), /locked install failed/);
  assert.equal(calls, 1);
  await assert.rejects(removeBuild({ ...prepared, owner: "wrong-owner" }), /ownership marker/);
  assert.ok((await readdir(prepared.directory)).includes("src"));
  await removeBuild(prepared);
});
