// The other end of engine/wasm/src/lib.rs: starts one instance of the engine module and talks to it in JSON.
// Loaded by the page (engine.js) and by every worker (worker.js), so they speak to the module the same way.
"use strict";

// module: a compiled WebAssembly.Module. Returns {call(name, request) -> answer, panic}: `panic` is the message of the
// last panic (after which the instance is dead: start another).
async function makeEngine(module) {
  let panic = "";
  let memory = null;
  const imports = {
    env: {
      host_now_ms: () => performance.now(),
      host_panic: (ptr, len) => { panic = new TextDecoder().decode(new Uint8Array(memory.buffer, ptr, len)); },
    },
  };
  const instance = await WebAssembly.instantiate(module, imports);
  const x = instance.exports;
  memory = x.memory;
  x.wb_init();
  const enc = new TextEncoder(), dec = new TextDecoder();
  const put = (text) => {
    const bytes = enc.encode(text);
    const ptr = x.wb_alloc(bytes.length);
    new Uint8Array(memory.buffer, ptr, bytes.length).set(bytes);
    return [ptr, bytes.length];
  };
  return {
    call(name, request) {
      const [np, nl] = put(name);
      const [rp, rl] = put(JSON.stringify(request || {}));
      const n = x.wb_call(np, nl, rp, rl);
      const answer = dec.decode(new Uint8Array(memory.buffer, x.wb_result(), n));
      x.wb_free(np, nl);
      x.wb_free(rp, rl);
      return JSON.parse(answer);
    },
    get panic() { return panic; },
  };
}
