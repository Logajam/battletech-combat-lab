// Gives the site's pages cross-origin isolation (the headers Cross-Origin-Opener-Policy / Embedder-Policy) by passing every
// same-origin response through with them added. A static host (GitHub Pages) cannot set headers itself, and BattleROM's play
// worker needs a SharedArrayBuffer, which a browser gives only to an isolated page (coi.js registers this file).
"use strict";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.cache === "only-if-cached" && r.mode !== "same-origin") return;
  e.respondWith(fetch(r).then((res) => {
    if (res.status === 0) return res;
    const h = new Headers(res.headers);
    h.set("Cross-Origin-Embedder-Policy", "require-corp");
    h.set("Cross-Origin-Opener-Policy", "same-origin");
    h.set("Cross-Origin-Resource-Policy", "same-origin");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
  }).catch((err) => new Response("coi-sw: " + err, { status: 502 })));
});
