/* EVENT SEARCH: the one query engine (INTEGRATION__EVENTS.md). The replay tab runs it in the browser and tools/search_events.py
 * runs the SAME file under node (tools/events_search_runner.js), so a query gives the same answer in both places.
 *
 * An event is {k kind, t turn, p phase, u unit, o other, tn, r roll, ok, d dmg, l loc, s sub, w what, n} (events.rs). A battle's
 * events come in the order they happened; `teams` maps a unit to its team (derived fields u_team and o_team).
 *
 * A query:
 *   { name, steps: [ {as, kind, where} ... ], same: ["t","p"], ordered: true, group: ["u","t","p"], count: {gte: 4} }
 *   steps    one or more events to find, in this order (ordered: false = any order). `kind` is one name or a list.
 *   where    {field: value | {eq, ne, gt, gte, lt, lte, in, nin, re}}. A value "$a.u" means the field `u` of the event step `a`
 *            matched (so a later step can say "the same unit": {o: "$a.u"}). Fields: k t p u o tn r ok d l s w n u_team o_team.
 *   same     fields every event of a match must share: ["t"] = the same turn, ["t","p"] = the same turn and phase.
 *   group    (one step only) count the step's events per group of these fields; each group that passes `count` is one match.
 *   count    {gte, lte, eq ...}: the group's size (or, with no group, the battle's count of the step's events) must pass.
 * A match = {t, p, events: [the events found], units, group?}. A battle's matches are capped (MAX_MATCHES); `capped` says so.
 */
(function (root) {
  "use strict";
  var MAX_MATCHES = 500;
  var FIELDS = ["k", "t", "p", "u", "o", "tn", "r", "ok", "d", "l", "s", "w", "n"];

  function fieldOf(ev, f, teams) {
    if (f === "u_team") return ev.u === undefined ? undefined : teams[ev.u];
    if (f === "o_team") return ev.o === undefined ? undefined : teams[ev.o];
    return ev[f];
  }

  function cmp(have, cond, bound, teams) {
    if (cond === null || typeof cond !== "object") return eq(have, resolve(cond, bound, teams));
    for (var op in cond) {
      var want = resolve(cond[op], bound, teams);
      if (op === "eq") { if (!eq(have, want)) return false; }
      else if (op === "ne") { if (eq(have, want)) return false; }
      else if (op === "gt") { if (!(have !== undefined && have > want)) return false; }
      else if (op === "gte") { if (!(have !== undefined && have >= want)) return false; }
      else if (op === "lt") { if (!(have !== undefined && have < want)) return false; }
      else if (op === "lte") { if (!(have !== undefined && have <= want)) return false; }
      else if (op === "in") { if (!want.some(function (w) { return eq(have, resolve(w, bound, teams)); })) return false; }
      else if (op === "nin") { if (want.some(function (w) { return eq(have, resolve(w, bound, teams)); })) return false; }
      else if (op === "re") { if (!(typeof have === "string" && new RegExp(want).test(have))) return false; }
      else throw new Error("unknown condition operator " + op);
    }
    return true;
  }

  function eq(a, b) { return a === b || (a !== undefined && b !== undefined && String(a) === String(b)); }

  /* "$a.u" -> the field u of the event bound as `a`; anything else is itself */
  function resolve(v, bound, teams) {
    if (typeof v === "string" && v.charAt(0) === "$") {
      var dot = v.indexOf(".");
      var name = v.substring(1, dot < 0 ? v.length : dot), f = dot < 0 ? "u" : v.substring(dot + 1);
      var ev = bound[name];
      if (!ev) throw new Error("the query refers to step '" + name + "' before it is matched");
      return fieldOf(ev, f, teams);
    }
    return v;
  }

  function stepMatches(step, ev, bound, teams) {
    if (step.kind !== undefined) {
      if (Array.isArray(step.kind) ? step.kind.indexOf(ev.k) < 0 : step.kind !== ev.k) return false;
    }
    var where = step.where || {};
    for (var f in where) {
      if (!cmp(fieldOf(ev, f, teams), where[f], bound, teams)) return false;
    }
    return true;
  }

  function sameOk(same, events, teams) {
    for (var i = 0; i < same.length; i++) {
      var v = fieldOf(events[0], same[i], teams);
      for (var j = 1; j < events.length; j++) if (!eq(fieldOf(events[j], same[i], teams), v)) return false;
    }
    return true;
  }

  function matchOf(events, extra) {
    var units = [];
    events.forEach(function (e) { [e.u, e.o].forEach(function (x) { if (x !== undefined && units.indexOf(x) < 0) units.push(x); }); });
    var m = { t: events[0].t, p: events[0].p, events: events, units: units };
    for (var k in extra || {}) m[k] = extra[k];
    return m;
  }

  /* Runs a query on one battle's events. Returns {matches, capped}. */
  function run(query, events, teams) {
    teams = teams || {};
    var steps = query.steps || [];
    if (!steps.length) throw new Error("a query needs at least one step");
    var same = query.same || [];
    var ordered = query.ordered !== false;
    var out = [], capped = false;

    // GROUPED COUNT: one step, events counted per group
    if (query.group || query.count) {
      if (steps.length !== 1) throw new Error("group / count queries have exactly one step");
      var hits = events.filter(function (e) { return stepMatches(steps[0], e, {}, teams); });
      var cond = query.count || { gte: 1 };
      var groups = {}, order = [];
      hits.forEach(function (e) {
        var key = JSON.stringify((query.group || []).map(function (f) { return fieldOf(e, f, teams); }));
        if (!groups[key]) { groups[key] = []; order.push(key); }
        groups[key].push(e);
      });
      order.forEach(function (key) {
        var g = groups[key];
        if (cmp(g.length, cond, {}, teams)) {
          if (out.length >= MAX_MATCHES) { capped = true; return; }
          var gv = {};
          (query.group || []).forEach(function (f) { gv[f] = fieldOf(g[0], f, teams); });
          out.push(matchOf(g, { count: g.length, group: gv }));
        }
      });
      return { matches: out, capped: capped };
    }

    // SEQUENCE: depth-first over the steps; a later step may refer to an earlier one ($a.u)
    var byKind = {};
    events.forEach(function (e, i) { (byKind[e.k] = byKind[e.k] || []).push(i); });
    var seen = {};
    function candidates(step) {
      if (step.kind === undefined) return events.map(function (_, i) { return i; });
      var kinds = Array.isArray(step.kind) ? step.kind : [step.kind], idx = [];
      kinds.forEach(function (k) { idx = idx.concat(byKind[k] || []); });
      return idx.sort(function (a, b) { return a - b; });
    }
    function go(si, picked, bound) {
      if (capped) return;
      if (si === steps.length) {
        var evs = picked.map(function (i) { return events[i]; });
        if (!sameOk(same, evs, teams)) return;
        var key = picked.slice().sort(function (a, b) { return a - b; }).join(",");
        if (seen[key]) return;
        seen[key] = true;
        if (out.length >= MAX_MATCHES) { capped = true; return; }
        out.push(matchOf(evs));
        return;
      }
      var step = steps[si], cand = candidates(step);
      var after = ordered && picked.length ? picked[picked.length - 1] : -1;
      for (var c = 0; c < cand.length; c++) {
        var i = cand[c];
        if (ordered && i <= after) continue;
        if (picked.indexOf(i) >= 0) continue;
        var ev = events[i];
        if (!stepMatches(step, ev, bound, teams)) continue;
        // prune early on the "same" fields
        if (picked.length && same.length && !sameOk(same, [events[picked[0]], ev], teams)) continue;
        var nb = Object.assign({}, bound);
        if (step.as) nb[step.as] = ev;
        go(si + 1, picked.concat([i]), nb);
        if (capped) return;
      }
    }
    go(0, [], {});
    return { matches: out, capped: capped };
  }

  /* A one-line description of an event, for result lists. */
  function describe(ev) {
    var parts = [ev.k];
    if (ev.u !== undefined) parts.push(ev.u + (ev.o !== undefined ? " -> " + ev.o : ""));
    else if (ev.o !== undefined) parts.push("-> " + ev.o);
    ["s", "w", "l"].forEach(function (f) { if (ev[f] !== undefined && ev[f] !== "") parts.push(ev[f]); });
    if (ev.tn !== undefined) parts.push("needs " + ev.tn);
    if (ev.r !== undefined) parts.push("rolled " + ev.r);
    if (ev.ok !== undefined) parts.push(ev.ok ? "yes" : "no");
    if (ev.d !== undefined) parts.push(ev.d + " dmg");
    if (ev.n !== undefined) parts.push("n=" + ev.n);
    return parts.join(" ");
  }

  /* "s=Engine d>=5 u!=Red 1": FIELD(=|!=|>=|<=|>|<)VALUE terms, one per space-or-comma item, into a `where` object (the same
   * syntax as tools/search_events.py's --where). Numbers and true / false are read as such. */
  function parseWhere(text) {
    var ops = [["!=", "ne"], [">=", "gte"], ["<=", "lte"], ["=", "eq"], [">", "gt"], ["<", "lt"]], where = {};
    String(text || "").split(/[,;]+/).forEach(function (item) {
      item = item.trim();
      if (!item) return;
      for (var i = 0; i < ops.length; i++) {
        var at = item.indexOf(ops[i][0]);
        if (at > 0) {
          var f = item.substring(0, at).trim(), v = item.substring(at + ops[i][0].length).trim();
          try { v = JSON.parse(v); } catch (e) { /* text */ }
          (where[f] = where[f] || {})[ops[i][1]] = v;
          return;
        }
      }
      throw new Error("use FIELD=VALUE (or !=, >=, <=, >, <): " + item);
    });
    Object.keys(where).forEach(function (f) { if (Object.keys(where[f]).length === 1 && where[f].eq !== undefined) where[f] = where[f].eq; });
    return where;
  }

  var api = { run: run, describe: describe, parseWhere: parseWhere, FIELDS: FIELDS, MAX_MATCHES: MAX_MATCHES };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.EventsQuery = api;
})(typeof self !== "undefined" ? self : this);
