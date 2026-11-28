// Loaded first by the browser build's pages: if the page is not cross-origin isolated yet, install coi-sw.js and reload
// once, so that the play worker can have a shared buffer. Where the host already sends the headers (or the browser cannot
// run a service worker) it does nothing; Play then says why it cannot start.
"use strict";
(function () {
  if (window.crossOriginIsolated || !("serviceWorker" in navigator) || !window.isSecureContext) return;
  let tried = false;
  try { tried = sessionStorage.getItem("coi_tried") === "1"; } catch (e) { /* storage off */ }
  if (tried) return;
  navigator.serviceWorker.register("coi-sw.js").then((reg) => {
    const go = () => { try { sessionStorage.setItem("coi_tried", "1"); } catch (e) { /* storage off */ } location.reload(); };
    if (reg.active && !navigator.serviceWorker.controller) go();
    else if (!reg.active) reg.addEventListener("updatefound", () => reg.installing && reg.installing.addEventListener("statechange", (ev) => { if (ev.target.state === "activated") go(); }));
  }).catch(() => { /* no service worker: Play will say so */ });
})();
