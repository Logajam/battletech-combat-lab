// One of the page's battle players: an instance of the engine module in its own thread. The page (engine.js) hands it a
// batch (`prepare`) and then battle numbers (`play`); it answers each with the battle's line for the results.
// A battle that crashes the engine stops the instance (a WebAssembly panic cannot be caught); the worker records the
// crash with its seed, starts a fresh instance, prepares it again and carries on, as the desktop Lab does with a thread.
"use strict";
importScripts("wasmio.js");

let module = null, engine = null, prepared = null;

async function fresh() {
  engine = await makeEngine(module);
  if (prepared) {
    engine.call("files", { defaults: prepared.defaults, files: prepared.files });
    engine.call("prepare", { setup: prepared.setup });
  }
}

onmessage = async (e) => {
  const { id, cmd } = e.data;
  const reply = (body) => postMessage({ id, ...body });
  try {
    if (cmd === "init") {
      module = e.data.module;
      engine = await makeEngine(module);
      reply({ ok: true });
    } else if (cmd === "prepare") {
      prepared = { defaults: e.data.defaults, files: e.data.files, setup: e.data.setup };
      engine.call("files", { defaults: prepared.defaults, files: prepared.files });
      reply(engine.call("prepare", { setup: prepared.setup }));
    } else if (cmd === "play") {
      try {
        reply(engine.call("play", { sim: e.data.sim }));
      } catch (err) {
        // the engine stopped inside this battle
        const msg = engine.panic || String(err);
        await fresh();
        const seed = engine.call("seed", { run_seed: prepared.setup.seed || 1, sim: e.data.sim }).seed;
        reply({ crash: true, line: { sim: e.data.sim, seed, crashed: msg, board: null, zones: null } });
      }
    } else if (cmd === "history" || cmd === "page") {
      // answered on a fresh instance when the battle crashes it
      try {
        if (cmd === "history") engine.call("files", { defaults: e.data.defaults, files: e.data.files });
        reply(engine.call(cmd, e.data.request));
      } catch (err) {
        const msg = engine.panic || String(err);
        engine = await makeEngine(module);
        reply({ error: "this battle crashes when played again: " + msg });
      }
    }
  } catch (err) {
    reply({ error: String(err && err.message || err) });
  }
};
