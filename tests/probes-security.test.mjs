import assert from "node:assert/strict";
import test from "node:test";
import {
  resolveWorkerEndpoints, requestWorker, colonyPath, WorkerRequestError,
  createSelectionScope, belongsToSelectedColony, openAuthenticatedSocket,
} from "../src/lib/probes/transport.ts";

const endpoints = resolveWorkerEndpoints({ environment: "production", apiUrl: "https://worker.example", wsUrl: "wss://worker.example/ws" });

test("worker configuration fails closed outside local development without crashing imports", () => {
  assert.equal(endpoints.error, null);
  assert.equal(resolveWorkerEndpoints({ environment: "development" }).apiUrl, "http://localhost:8765");
  for (const input of [
    { environment: "production" }, { environment: "test" },
    { environment: "production", apiUrl: "http://worker.example", wsUrl: "wss://worker.example/ws" },
    { environment: "production", apiUrl: "https://localhost", wsUrl: "wss://localhost/ws" },
    { environment: "production", apiUrl: "https://worker.example", wsUrl: "ws://worker.example/ws" },
    { environment: "development", apiUrl: "http://remote.example", wsUrl: "ws://remote.example/ws" },
    { environment: "production", apiUrl: "https://user:secret@worker.example", wsUrl: "wss://worker.example/ws" },
    { environment: "production", apiUrl: "https://worker.example", wsUrl: "wss://worker.example/ws?token=secret" },
  ]) {
    const result = resolveWorkerEndpoints(input);
    assert.ok(result.error);
    assert.equal(result.apiUrl, null);
    assert.equal(result.wsUrl, null);
    assert.ok(!result.error.includes("secret"));
  }
});

test("colony controls use explicit encoded IDs and the current bearer without URL credentials or redirects", async () => {
  let calls = 0;
  const result = await requestWorker(endpoints, "current-session-token", colonyPath("colony/A", "pause"), { method: "POST" }, async (url, options) => {
    calls++;
    assert.equal(url, "https://worker.example/api/v1/colonies/colony%2FA/pause");
    assert.equal(options.headers.Authorization, "Bearer current-session-token");
    assert.equal(options.headers["x-api-key"], undefined);
    assert.equal(options.redirect, "error");
    assert.equal(options.credentials, "omit");
    assert.equal(options.body, undefined);
    return Response.json({ status: "paused" });
  });
  assert.equal(calls, 1);
  assert.equal(result.status, "paused");
  assert.throws(() => colonyPath(" "), /Select a colony/);
  for (const path of ["https://attacker.example", "/api/v1/colonies/?token=x"]) {
    await assert.rejects(requestWorker(endpoints, "session", path, {}, () => { throw new Error("must not fetch"); }), /Invalid worker/);
  }
  await assert.rejects(requestWorker(endpoints, null, "/api/v1/colonies/", {}, () => { throw new Error("must not fetch"); }), WorkerRequestError);
});

test("worker failures expose safe actionable messages instead of private response bodies", async () => {
  for (const status of [401, 404, 503, 500]) {
    await assert.rejects(requestWorker(endpoints, "session", "/api/v1/colonies/", {}, async () => new Response("private-token-and-data", { status })), (error) => {
      assert.equal(error.status, status);
      assert.ok(!error.message.includes("private-token-and-data"));
      return true;
    });
  }
});

test("only events with the exact selected colony are accepted, including status and lifecycle events", () => {
  for (const type of ["probe_born", "probe_update", "probe_dying", "probe_reproducing", "simulation_status", "generation_complete", "price_update"]) {
    assert.equal(belongsToSelectedColony({ type, colony_id: "A", data: {} }, "A"), true);
    assert.equal(belongsToSelectedColony({ type, colony_id: "B", data: {} }, "A"), false);
    assert.equal(belongsToSelectedColony({ type, data: {} }, "A"), false);
    assert.equal(belongsToSelectedColony({ type, colony_id: "A", data: {} }, null), false);
  }
});

test("selection and session generations reject late reads and controls after A -> B -> A, refresh and logout", () => {
  const scope = createSelectionScope();
  scope.select("A");
  const dataA = scope.begin("data");
  const controlA = scope.begin("control");
  scope.select("B");
  assert.equal(scope.current(), "B");
  assert.equal(scope.isCurrent(dataA), false);
  assert.equal(scope.isCurrent(controlA), false);
  scope.select("A");
  assert.equal(scope.isCurrent(dataA), false);
  const older = scope.begin("data");
  const newer = scope.begin("data");
  assert.equal(scope.isCurrent(older), false);
  assert.equal(scope.isCurrent(newer), true);
  scope.dispose();
  assert.equal(scope.isCurrent(newer), false);
  scope.activate();
  assert.equal(scope.isCurrent(newer), false);
  assert.equal(scope.isCurrent(scope.begin("data")), true);
});

function socketHarness(token = "token-one", userId = "user-A") {
  const sockets = [], states = [], messages = [], timers = new Map();
  let clock = 1_000_000, serial = 0;
  const options = {
    url: "wss://worker.example/ws", accessToken: token, userId,
    onStatus: (status) => states.push(status), onMessage: (message) => messages.push(message),
    now: () => clock,
    schedule: (callback, delay) => { const id = ++serial; timers.set(id, { callback, delay }); return id; },
    cancel: (id) => timers.delete(id),
    createSocket: (url) => {
      const socket = {
        url, sent: [], closed: [], onopen: null, onmessage: null, onclose: null, onerror: null,
        send(frame) { this.sent.push(JSON.parse(frame)); },
        close(code, reason) { this.closed.push({ code, reason }); },
        open() { this.onopen?.({}); },
        message(message) { this.onmessage?.({ data: JSON.stringify(message) }); },
        end(code) { this.onclose?.({ code }); },
      };
      sockets.push(socket);
      return socket;
    },
  };
  const dispose = openAuthenticatedSocket(options);
  return { sockets, states, messages, timers, dispose, options,
    auth(socket = sockets.at(-1), owner = userId, lifetime = 30_000) {
      socket.message({ type: "auth_ok", data: { user_id: owner, expires_at: (clock + lifetime) / 1000 } });
    },
    advance(delay) {
      const entry = [...timers].find(([, timer]) => timer.delay === delay);
      assert.ok(entry, `Missing timer for ${delay}ms`);
      timers.delete(entry[0]); clock += delay; entry[1].callback();
    },
  };
}

test("socket remains disconnected until matching, unexpired auth_ok and sends the token only in its first frame", () => {
  const h = socketHarness();
  const socket = h.sockets[0];
  assert.equal(socket.url, "wss://worker.example/ws");
  assert.equal(h.states.at(-1).connected, false);
  socket.open();
  assert.deepEqual(socket.sent, [{ type: "auth", access_token: "token-one" }]);
  assert.equal(h.states.at(-1).connected, false);
  h.auth();
  assert.equal(h.states.at(-1).connected, true);
  socket.message({ type: "probe_update", colony_id: "A", data: { probe_id: "probe" } });
  assert.equal(h.messages.length, 1);
  h.dispose();
  assert.equal(h.timers.size, 0);
});

test("unauthenticated events, wrong user acknowledgements and expired sessions fail closed", () => {
  for (const frame of [
    { type: "probe_born", colony_id: "A", data: {} },
    { type: "auth_ok", data: { user_id: "user-B", expires_at: 1030 } },
    { type: "auth_ok", data: { user_id: "user-A", expires_at: 999 } },
  ]) {
    const h = socketHarness();
    const socket = h.sockets[0];
    socket.message(frame);
    assert.equal(socket.closed.at(-1).code, 4401);
    h.auth(); // A frame already queued before close must not revive this socket.
    socket.message({ type: "probe_born", colony_id: "A", data: {} });
    assert.equal(h.states.at(-1).connected, false);
    assert.equal(h.messages.length, 0);
    socket.end(4401);
    assert.equal(h.timers.size, 0);
    h.dispose();
  }
});

test("logout and token rotation retire captured callbacks and reconnect timers", () => {
  const h = socketHarness();
  const socket = h.sockets[0];
  h.auth();
  const oldMessage = socket.onmessage, oldClose = socket.onclose;
  const before = h.states.length;
  h.dispose();
  const nextDispose = openAuthenticatedSocket({ ...h.options, accessToken: "token-two" });
  const next = h.sockets.at(-1);
  next.open();
  assert.equal(next.sent[0].access_token, "token-two");
  oldMessage({ data: JSON.stringify({ type: "probe_born", colony_id: "A", data: {} }) });
  oldClose({ code: 1006 });
  assert.equal(h.messages.length, 0);
  assert.equal(h.states.length, before + 1);
  assert.equal(h.timers.size, 1); // Only the new socket's handshake deadline.
  nextDispose();
  assert.equal(h.timers.size, 0);
});

test("temporary failures retry with bounded exponential backoff and no retries after terminal rejection", () => {
  const h = socketHarness();
  for (const delay of [1000, 2000, 4000, 8000, 15000, 15000]) {
    h.sockets.at(-1).end(1013);
    h.advance(delay);
  }
  h.sockets.at(-1).end(1013);
  assert.equal(h.sockets.length, 7);
  assert.equal(h.timers.size, 0);
  assert.match(h.states.at(-1).error, /Reload/);
  h.dispose();
  for (const code of [4400, 4401, 4403]) {
    const rejected = socketHarness();
    rejected.sockets[0].end(code);
    assert.equal(rejected.timers.size, 0);
    rejected.dispose();
  }
});

test("successful authentication resets consecutive retry failures; expired sockets stop delivering data", () => {
  const h = socketHarness();
  h.sockets[0].end(1013); h.advance(1000);
  h.auth();
  h.sockets.at(-1).end(1006); h.advance(1000);
  h.auth();
  const socket = h.sockets.at(-1);
  h.advance(30_000);
  assert.equal(socket.closed.at(-1).code, 4401);
  socket.message({ type: "probe_update", colony_id: "A", data: {} });
  assert.equal(h.messages.length, 0);
  assert.equal(h.states.at(-1).connected, false);
  h.dispose();
});

test("unresponsive authentication is timed out and disposed retries never open another socket", () => {
  const h = socketHarness();
  h.advance(7500);
  assert.equal(h.sockets[0].closed.at(-1).code, 4408);
  h.sockets[0].end(4408);
  const retry = [...h.timers.values()][0].callback;
  h.dispose();
  retry();
  assert.equal(h.sockets.length, 1);
  assert.equal(h.timers.size, 0);
});
