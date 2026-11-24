# Play UI design notes (Daniel, 2026-11-24)

Source: a Gemini summary of Daniel's UI design discussion (`Swiss_Matchup_Games.txt`, the part about viewing the simulator
and `battletech-combat-lab`), pasted by Daniel. Second-hand: check it against `INTEGRATION__BATTLEROM_UI.md` (the existing
mockup and decisions) before building; where they differ, ask Daniel. Feeds goal P3 (long presses) and O1 in PROJECT_MAP.

## 1. Principles
- Human-first, intent-driven: the player says what they want, the game infers context (phase, selected unit, legality). No
  software "modes" (waypoint mode, facing mode); not a copy of MegaMek's dense interface.
- Three layers of progressive disclosure:
  1. Always available: moving, firing, basic status.
  2. Contextual, only when legal: Charge (drag onto an enemy hex), Aimed Shot (immobile target), Stand (prone), Club (near
     woods or in trees).
  3. Inspector, rare and advanced: edge-case rules, detailed damage and criticals, ammo and weapon settings, manual overrides.
- Don't ask what the computer already knows: hide impossible actions; menus open away from the finger or pointer, never over
  the hex being worked on.
- Decouple input from game logic: clicks, drags, long presses and later shortcuts all become intents in one pipeline
  (Map -> Selection -> Tool -> Preview -> Confirm), so controls can be remapped without touching the simulation.
- Confirm loop: movement and fire are drafts until confirmed (press-and-hold or explicit confirm to avoid accidents), with
  step-back and clear.

## 2. Screen and devices
- Touch-first, phone-constrained baseline; nothing needs a keyboard; no reliance on hover.
- Phone play area about a 2:1 safe zone (browser chrome, notches, 19.5:9 to 21:9 screens).
- Plan around roughly 1:1 map to controls/readouts, with collapsible or tabbed panels to win back map space (flick a side
  panel closed on touch); movable, dockable tool windows on PC.

## 3. Input handling
- Unified Pointer Events with Tap, Long Press (hold without much movement) and Drag (past a pixel threshold, which cancels the
  long press).
- Suppress the browser's right-click menu over the map so right-click can pan or open desktop context actions.
- Drag conflicts by context: dragging empty terrain, or with no 'Mech selected, pans; two-finger pan and pinch-zoom too.

## 4. Movement and facing
- Two ways in, same commands underneath: grab and drag a 'Mech (live path preview), or select it and tap hexes for waypoints.
  Both reduce to steps and turns that can be stepped back, cleared or edited.
- Facing: five trapezoid choices around the final hex (straight ahead shown as a "front this way" marker), colored by movement
  mode (Walk/Run/Jump) with MP cost.
- Escape hatch: manual turn and command editing in the inspector, to spin in place or override an obstinate pathfinder.

## 5. Firing, placards, readouts
- Target-centric weapon layout: with a target picked, the shooter's weapons are drawn around the target by body location
  (arms, torsos, head, legs), colored ready (green) or fired (red); long press opens that weapon's inspector (ammo, settings,
  its own to-hit number, since range and numbers differ per weapon).
- Torso twist automatic by default, manual override available.
- Tiered "escalation" alpha strike control: smart/optimal fire, then everything at the target, then fire all or split across
  secondary targets; state shown by color and a 3-dot indicator; optional flavor text (escalating missile or autocannon
  strings) that can be turned off or customized in the inspector.
- Unit placard always shows: identity, Piloting/Gunnery, left/right armor and structure bars, current movement, heat against
  capacity (colors escalate as heat rises). A warning mark appears on pilot hits, critical damage or extra detail and opens the
  inspector on long press. Contextual buttons (Aimed Shot, Charge) and map/firepower overlay toggles sit beside it.

## 6. Second summary (GPT's, of the continuation of the same chat; Daniel, 2026-11-24)

Agrees with sections 1-5. GPT says the chat was already under context compression by then, so treat details as second-hand.
What it adds or sharpens:
- Desktop gets convenience only (keyboard, right-click pan, movable windows), never different mechanics.
- Three layers of information, with a rule for the first: **if information has a location, draw it on the map** (positions,
  paths, range, LOS, threat and heat overlays, later artillery and ECM overlays).
- Two placards: a **simple placard on every unit** (name, armor bar, structure bar: "what am I looking at?") and an
  **expanded placard under the selected unit only** (name, Gunnery/Piloting, movement, heat/capacity, bars, overlay toggles,
  context buttons, warning icon: "what can I do with it?"). Long press opens the **Inspector** (criticals, pilot injuries,
  equipment, ammo choice, manual turning, rare movement, personality, debug).
- Everything is planned first, then committed with one contextual Confirm Action button (press-and-hold).
- Overlays (movement, firepower, LOS, heat): several at once, one standard color scale, an on-screen legend.
- Context actions listed: Charge, DFA, Club, Push, Stand, Aimed Shot; shown only when legal.
- Personality layer is cosmetic text for the fire-escalation steps: Standard (Strike / Alpha Strike / All Weapons), Missile
  Boat (Missiles! / More Missiles! / ALL THE MISSILES!), Machine Guns (Brrt. / Brrrrt. / Brrrrrrrrrrrrrrrrt.); themes
  configurable or off in the Inspector.
- Redundant control paths are fine if they call the same backend action; the planner drafts, the player has the last word.

**Next design step (Daniel's plan): before any graphics, draw a complete interaction/state diagram**: every player
decision, transition, context action and confirmation path; then audit it against the Core Rulebook so every legal action has
at least one discoverable control. Design the UI as a finite-state model first, graphics after.
