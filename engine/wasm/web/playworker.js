// BATTLEROM IN THE BROWSER: one Web Worker plays one battle with a person in it. The engine module cannot wait, so this
// worker simply BLOCKS inside the module's call: `host_play_wait` sleeps on a shared buffer (Atomics.wait) until the page
// writes the person's answer (or a query) into it. The page needs cross-origin isolation for a shared buffer (coi.js).
//
// The shared buffer (made by the page, engine.js): `ctl` = Int32Array [flag, length], `data` = bytes. flag 0: nothing sent;
// flag 1: the page has put a message of `length` bytes in `data` ({"k": "a" | "q", "v": ...}). The worker takes it and sets
// the flag back to 0. The worker's own messages to the page: {ev: "post", request} (a question), {ev: "qreply", reply},
// {ev: "done", end}, {ev: "failed", error}.
"use strict";
importScripts("wasmio.js");

onmessage = async (e) => {
  if (e.data.cmd !== "start") return;
  const { module, defaults, files, setup, seed, sab } = e.data;
  const ctl = new Int32Array(sab, 0, 2), data = new Uint8Array(sab, 8);
  const enc = new TextEncoder(), dec = new TextDecoder();
  let taken = null, mem = null;
  const text = (ptr, len) => dec.decode(new Uint8Array(mem().buffer, ptr, len));
  let engine;
  try {
    engine = await makeEngine(module, (m) => {
      mem = m;
      return {
        host_play_post: (ptr, len) => postMessage({ ev: "post", request: JSON.parse(text(ptr, len)) }),
        host_play_reply: (ptr, len) => postMessage({ ev: "qreply", reply: JSON.parse(text(ptr, len)) }),
        host_play_wait: () => {
          while (Atomics.load(ctl, 0) === 0) Atomics.wait(ctl, 0, 0);       // sleeps until the page sends and notifies
          taken = data.slice(0, Atomics.load(ctl, 1));
          return taken.length;
        },
        host_play_take: (ptr) => { new Uint8Array(mem().buffer, ptr, taken.length).set(taken); Atomics.store(ctl, 0, 0); },
      };
    });
    engine.call("files", { defaults, files });
    const r = engine.call("play_run", { setup, seed });
    if (r.error) postMessage({ ev: "failed", error: r.error }); else postMessage({ ev: "done", end: r.end });
  } catch (err) {
    postMessage({ ev: "failed", error: (engine && engine.panic) || String(err && err.message || err) });
  }
};
