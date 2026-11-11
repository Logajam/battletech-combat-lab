# Combat Lab art: why the models read as stacked blocks, and what to build (2026-11-11, session 24)

Daniel, 2026-11-11: "The goal is to eventually get models that look like they could actually be from the
setting. Right now they're still just shaped blocks stacked on each other despite improvements."

Nothing here is built. This is a diagnosis from looking at the current output, then spec sheets A1-A8 in
the order I would do them. The art's own spec stays `INTEGRATION__COMBAT_LAB_SKELETON.md`; Daniel's
design principles there (skeleton, myomer, armor shell, no exposed internals) are not changed by this
file. "CHECK FIRST" marks something I did not verify in the code.

What I looked at: `python -I tools/token_lineup.py <meks folder> out.png torso "Atlas AS7-D" --body`
(the five torso blocks on an Atlas, 3/4 front and rear). One 'Mech, one small picture: treat the
diagnosis as a strong first read, not a survey.

## The diagnosis: six reasons it reads as blocks

1. **Every part is one lump, and every lump is bulging (convex).** Real hardware is full of hollows:
   recesses, inset panels, overhangs, gaps between plates. A shape with no hollows reads as a
   carved block however many facets it has.
2. **Parts touch; they do not interlock.** The head sits ON the torso, the arm hangs BESIDE the
   shoulder, the thigh meets the hip at a face. In a designed machine one part sinks into, wraps or
   overlaps the next (a collar around the head, a pauldron over the arm, a skirt over the hip).
3. **One size of detail.** There are big forms and nothing else: no medium layer (plates, housings,
   vents) and no small layer (panel lines, hatches, rungs). The small layer is also what tells the
   eye the machine is 12 metres tall.
4. **The variants do not change the outline.** The five torso blocks are nearly the same silhouette;
   they differ in facets the eye cannot see at token size. A chassis is recognized by its outline.
5. **No taper and no shared lines.** Limbs are straight prisms of similar thickness; each part has
   its own angles. Designed objects repeat two or three angles everywhere and taper toward joints.
6. **One material, flat light.** Everything is the same grey. Armor paint, bare joint metal, dark
   under-layer, glass and gun barrels are not told apart, and there are no shadows in the gaps.

Reasons 1, 3 and 6 are global: fixing them improves every 'Mech at once. Reasons 2, 4 and 5 are per
slot or per chassis. Hence the order below.

## The order

| Sheet | Job | Fixes | Reach | Size |
|---|---|---|---|---|
| A1 | Materials and light in the renderers | 6 | every 'Mech | small |
| A2 | Two layers: dark under-body, armor plates with gaps | 1, 3 | every 'Mech | medium |
| A3 | Outline first: the silhouette check and a proportion table | 4 | per chassis | medium |
| A4 | Taper and shared angles | 5 | per slot | medium |
| A5 | Interlock at every joint | 2 | per joint kind | medium |
| A6 | The small-detail kit | 3 | every 'Mech | medium |
| A7 | Weapons that look like weapons | 3 | per weapon family | open-ended (Daniel's stockpile) |
| A8 | Paint: schemes, stripes, numbers | 6 | every 'Mech | small |
| A9 | Interchangeable arms and torsos, known slots (advice) | - | the block library | read before adding blocks |

Every sheet ends the same way: publish before / after pages of the same six 'Mechs for Daniel
(suggested: Locust, Jenner, Hunchback, Marauder, Catapult, Atlas: light to assault, humanoid and
bird-legged, arms and no arms). The look is his call; the scripted checks only guard against
breakage. Art changes run only the art checks (CLAUDE.md).

---

## A1. Materials and light in the renderers

**Job.** The same models, drawn so that surfaces can be told apart.

**Build.**
- MATERIAL TAG on every solid, from the class tag it already has (CHECK FIRST: the class names in
  the `B3` output): armor, joint / under-body, weapon metal, glass, vent, marking.
- A small PALETTE per material (armor = the team colour; joint = dark warm grey; weapon metal =
  gunmetal; glass = blue as now; vent = near black).
- LIGHT: one key light from the upper front left, a weak fill, and darkening where surfaces face
  down or sit in a gap (a cheap stand-in for ambient shadow). A soft ground shadow under the feet.
- An OUTLINE around the whole figure in the 2D tokens, so it separates from the board.
- Both renderers: the picture tools (`tools/token_lineup.py`, `token_sheet.py`) and the 3D viewer
  (`tools/token_3d.py`). One palette file feeds both.

**Done when.** The six 'Mechs, old and new side by side, published. Scripted: every solid has a
material; no solid is drawn in the debug colour.

## A2. Two layers: dark under-body, armor plates with gaps

**Job.** The single highest-value change to shape. Each location becomes a slightly smaller DARK
under-body with lighter ARMOR PLATES standing just off it, a narrow gap between neighbouring plates.

**Why.** The gaps are the hollows (reason 1) and they are panel lines for free (reason 3). It is
also what Daniel's principles describe: a shell built around the frame, nothing exposed (the
under-body is a sealed liner, not skeleton or myomer).

**Build.**
- UNDER-BODY: the location's current solid, shrunk a few percent, material "under-body".
- PLATE CUTTER: divides the location's outer surface into 3-7 plates along lines chosen per slot
  (a chest: two breast plates, a centre keel, a belly plate, two flank plates), each plate a thin
  solid following the surface, lifted off the under-body, with a gap of about 2-4% of the part's
  size to its neighbours. Solids must stay convex (the builder's rule): a plate that bends is two
  plates.
- Plate COUNT and THICKNESS follow the location's armor points (the Skeleton spec's layer 4): heavy
  armor = thicker plates and a second overlapping row; light armor = thin plates, wider gaps.
- Plates may overhang the under-body at the edges (brows over a cockpit, a lip over a joint).

**Done when.** Published pages. Scripted: the existing checks still pass (joined, above ground, no
clipping, every muzzle clear); every location has an under-body and at least three plates; no gap
shows through to nothing (a ray through a gap always hits under-body).

**Traps.** Solid count multiplies: measure the 3D viewer's speed at a 12 v 12. The volume sanity
check (Skeleton spec section 4) should count under-body plus plates.

## A3. Outline first: the silhouette check and a proportion table

**Job.** Make the outline carry the chassis, and make the block library's variants differ where the
eye can see it.

**Build.**
- SILHOUETTE SHEET: a tool page showing each 'Mech filled solid black, front and side, at token
  size. If you cannot tell which is which, no amount of surface work will help.
- VARIANT CHECK (scripted): for each slot, the black silhouettes of its blocks on the same 'Mech
  must differ by at least a set share of the outline (start at 8% of pixels, front or side). Blocks
  that fail are the same block to the eye: merge them or push them apart.
- PROPORTION TABLE: per chassis, a handful of ratios that define it (shoulder width, hip width,
  torso height, torso depth, leg length, head size and how deep it sinks, all as shares of height),
  read off the published art for the 47 chart chassis (the Skeleton spec's Phase 2). The builder
  takes the table first and the tonnage defaults second.

**Done when.** The silhouette sheet of the six test 'Mechs, published; Daniel can name each one from
the black shape. The variant check runs in the art tests.

## A4. Taper and shared angles

**Job.** Stop limbs and housings being straight prisms; make the parts of one 'Mech agree.

**Build.**
- TAPER RULE per bone: a part is widest where it carries load or mass and narrows toward the joint
  (thigh wide at the hip, narrow at the knee; shin flaring to the ankle; forearm swelling around
  its weapon; torso narrowing to the waist). Each slot block states its two end sizes, not one.
- ANGLE SET per chassis: two or three chamfer angles (say 15, 30, 45 degrees) chosen once; every
  block's bevels snap to the set, so edges run parallel across neighbouring parts.
- STANCE: a slight forward lean of the torso and feet apart (CHECK FIRST: the current stance tags
  already do part of this).

**Done when.** Published pages. Scripted: no limb block has equal cross-sections at both ends unless
tagged "straight" on purpose; every bevel angle on a 'Mech is in its angle set.

## A5. Interlock at every joint

**Job.** One part sinks into or covers the next, at every joint.

**Build.** A COVER per joint kind, chosen by the chassis tags:
- neck: a collar on the torso that the head sits down inside (for an Atlas, deep);
- shoulder: a pauldron from the torso side or the arm top that overlaps the other;
- elbow, knee: a cap plate on the outside of the bend, overlapping both parts;
- hip: skirt plates from the pelvis over the thigh tops;
- waist: a ring the upper torso sits into;
- ankle: a cuff from the shin over the foot.
Each cover is plates on an under-body (A2), sized so the joint can still swing its stated range
(the Skeleton spec's rule: "would let the joint move, with no gap showing the inside").

**Done when.** Published pages. Scripted: at every joint, seen from the front and the side, the two
parts overlap by a set minimum share of the joint's width; nothing clips through a full swing of the
joint (the audit tool's clipping check, run at the range ends).

## A6. The small-detail kit

**Job.** The small layer, placed by rule so it never looks sprinkled.

**Build.** A kit of tiny solids with placement rules:
- heat-sink vents: in rows on the rear torso and calves, count following the unit's heat sinks;
- access hatches and ladder rungs: one hatch near the cockpit, rungs up one leg and flank (the best
  scale cue there is: a rung is a hand's width);
- lifting eyes and tie-down rings at shoulders and hips; antenna and sensor blisters on the head;
- jump-jet nozzles where the unit has jump jets; ammo-feed humps beside ballistic weapons;
- a rule of density: detail gathers at joints, hatches and weapon mounts, and leaves the large
  plates calm. Never more than a third of a plate's area.

**Done when.** Published pages at two sizes (token size and close-up). Scripted: counts follow the
unit file (vents with sinks, nozzles with jets); no detail solid floats or clips.

## A7. Weapons that look like weapons (Daniel's stockpile, the standing next step)

**Job.** Each weapon family readable at a glance, and mounted like equipment, not glued on.

**Build per family:** a barrel or emitter, a shroud or cooling jacket, a housing that meets the
plate it sits in through a collar or a cut-out (A5's idea at small scale), and the family's tell:
ribbed jacket for lasers, coils for a PPC, a muzzle brake and a fat breech for autocannon, long
rails for a Gauss rifle, a tube face with covers for missile racks. Size by the weapon's tonnage and
critical slots, as now.

**Done when.** A lineup page per family for Daniel. Scripted: every muzzle clear (exists).

## A8. Paint: schemes, stripes, numbers

**Job.** Much of "looks like it is from the setting" is paint.

**Build.** On top of A1's team colour: a second colour on chosen plates (shoulders, one leg, a chest
stripe), a unit number on a shoulder and the rear, a small insignia patch, darker lower legs (mud),
slightly lighter plate edges (wear). Schemes are data: a list of which plate groups take which
colour, so Daniel can add a regiment's scheme without code.

**Done when.** The six 'Mechs in three schemes, published.

---

## A9. Interchangeable arms and torsos with a known variety of slots (advice, Daniel's question 2026-11-11)

Daniel: "advice you could give future you on how to create arms and torsos that are interchangeable, and
contain a known variety of weapon and equipment slots?" The hardpoint rules themselves are his and are in
`INTEGRATION__COMBAT_LAB_SKELETON.md` section 3 (every location can mount ANY combination its critical
slots allow; items take hardpoints by their critical slots; placement shuffled). This sheet is about how to
build blocks so those rules hold for every pairing. CHECK FIRST how much of it `INTEGRATION__shell_facet.py`
(BLOCKS, the joint sockets) and `INTEGRATION__shell_items.py` (rails, `rail_count`) already do.

**The one idea: design the joins and the bays first, the shapes last.** A block is three things, in this
order: its SOCKETS (how it joins), its BAYS (what it can carry), its SHAPE (what covers them). Blocks
are interchangeable when the first two are standard and only the third is free.

1. **A socket standard.** Each joint kind (shoulder, neck, waist, hip, elbow, wrist) has one definition:
   where it is, which way its axis points, and a SIZE CLASS (four classes by tonnage band are enough).
   Every arm block is drawn in its own frame with the shoulder socket at the origin; every torso block
   lists where its shoulder, neck and waist sockets are. Same class = fits, always. A different class
   fits through a scaling ring, never by reshaping either block.
2. **One owner for each joint cover.** Decide once which side brings the cover (suggest: the body-side
   part brings the recess or collar, the limb-side part brings the cap). Otherwise some pairings get two
   covers and some get none. This is A5's interlock, made part of the standard.
3. **A bay list for every block, as data.** Each block declares its bays in a table a person can read:
   bay number, kind (a face cell, a line along the part, a post on top, an inside bay), how many critical
   slots it holds (a range, smallest to largest), which way it faces (front, rear, up, side), what it
   accepts (energy, ballistic, missile, equipment with a face, hidden equipment), and how far an item may
   stick out. The table is the "known variety": publish it as a catalogue page with the bays numbered on
   the picture (the lineup tool already numbers the rails).
4. **The bay list must cover the worst cases, by test, not by eye.** For a location the rules give the
   free slots (arms 8-10, side torsos 12, centre torso 2-7, head up to 4, legs 2). A block passes only if
   it places all of: the largest single item legal there (so one long unbroken bay is needed), the most
   one-slot items, and a set of mixed loads taken from real unit files. Every item placed, none twice,
   every muzzle clear. A block that fails is not in the library.
5. **Bays grow; shapes follow.** A bay has a resting size (empty: a flush blanking plate) and a stated
   direction it grows when filled (outward, rearward, along the limb). The shell (A2's plates) is laid
   AFTER the items are placed, with a collar or cut-out for each item that has a face. So no block has a
   weapon baked into its shape, and a heavy load shows as a bulge where the bay said it would.
6. **A small set of named layouts instead of endless blocks.** Arms: gun arm (one long forearm line bay
   and two face cells), hand arm (forearm bay over the wrist, upper-arm bay, shoulder post), pod arm (a
   box of face cells, for racks), trunk arm. Side torsos: rack (a grid of face cells in front, vents
   behind), shoulder mount (a post on top carrying a long weapon over the shoulder), chest bay (a line
   bay through the torso, muzzle in front), rear deck (jets and vents). Variety then comes from layout x
   shape x load, and each layout is one bay table to test.
7. **Rear and turret mounts are bays too.** A unit file can mount a torso weapon facing the rear; a torso
   block therefore needs rear-facing bays, or the game truth and the model disagree.
8. **Build right-hand parts only** and mirror them; asymmetry comes from the load, not from the block.
9. **The pairing test.** Every torso block x every arm block x every size class: joined, no clipping
   through the joint's full swing, and the worst-case loads of point 4 on both. Run it as a table in the
   art checks; a red cell names the pair.

**Do not:** fuse an arm and a torso into one special block for a chassis (it breaks every pairing); let a
bay's capacity depend on which neighbour is fitted; hide a failed placement by shrinking the item.

## What I would not do yet

- More facets on single lumps. It is the improvement that has already been tried, and it does not
  fix any of the six reasons.
- Smooth or organic surfaces. The setting's machines are plated hardware; A2 gets there faster.
- Per-chassis hand-built models. The proportion table (A3) plus the kit gives chassis identity
  without leaving the builder.
