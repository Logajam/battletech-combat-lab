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
