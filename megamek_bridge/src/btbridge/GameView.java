/*
 * MegaMek bridge (INTEGRATION__MEGAMEK_BRIDGE.md), stage B3 (Java half). GPL v3: built on MegaMek (see README.md).
 */
package btbridge;

import java.io.File;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import megamek.common.CriticalSlot;
import megamek.common.board.Coords;
import megamek.common.equipment.Mounted;
import megamek.common.game.Game;
import megamek.common.units.Entity;

/**
 * What our engine is told about a MegaMek game: the start (which .mtf on which team, where, the board) and, before
 * every question, each unit's state as MegaMek knows it. The Rust side reads these in {@code bridge.rs}
 * ({@code Session::start} with "settings", {@code apply_megamek_view}).
 *
 * <p>Units are named "U" + MegaMek's entity id and listed in id order, so a unit's number in our engine (its place in
 * the roster) is its place in that order. Teams are "T" + MegaMek's team number.</p>
 */
public final class GameView {
    static final ObjectMapper JSON = new ObjectMapper();
    private static final String[] COMPASS = {"N", "NE", "SE", "S", "SW", "NW"};

    /** The units at the start, in roster order (entity id order). */
    final List<Integer> roster = new ArrayList<>();
    /** Entity id -> our unit name. */
    final Map<Integer, String> names = new LinkedHashMap<>();

    /** The hex label our engine uses ("0905": column, row, from 1) for MegaMek's 0-based coordinates. */
    static String label(Coords c) {
        return (c == null) ? null : String.format("%02d%02d", c.getX() + 1, c.getY() + 1);
    }

    /** MegaMek's coordinates for one of our hex labels. */
    static Coords coords(String label) {
        return new Coords(Integer.parseInt(label.substring(0, 2)) - 1, Integer.parseInt(label.substring(2, 4)) - 1);
    }

    static String team(Entity e) {
        return "T" + e.getOwner().getTeam();
    }

    /** The unit file our engine loads for a MegaMek unit: "Chassis Model.mtf" in our data folder. */
    static String mtfName(Entity e) {
        return (e.getChassis() + " " + e.getModel()).trim() + ".mtf";
    }

    /** Our roster index of a MegaMek entity. */
    int index(Entity e) {
        return roster.indexOf(e.getId());
    }

    /**
     * The start line: our engine builds the same game from these settings (Combat Lab CL1). Fails (null + reason in
     * {@code why}) if a unit has no .mtf in our data folder.
     *
     * @param boardFile the board's file, absolute (MegaMek's own board file: the same format as ours)
     * @param dataDir   our data folder (for the .mtf check)
     */
    ObjectNode start(Game game, String boardFile, File dataDir, List<String> hydraTeams, long seed, StringBuilder why) {
        List<Entity> all = new ArrayList<>(game.getEntitiesVector());
        all.sort(Comparator.comparingInt(Entity::getId));
        ArrayNode forces = JSON.createArrayNode();
        for (Entity e : all) {
            if (!new File(dataDir, mtfName(e)).exists()) {
                why.append("no unit file '").append(mtfName(e)).append("' in our data folder");
                return null;
            }
            roster.add(e.getId());
            names.put(e.getId(), "U" + e.getId());
            ObjectNode f = forces.addObject();
            f.put("team", team(e));
            f.put("mtf", mtfName(e));
            f.put("name", "U" + e.getId());
            f.put("hex", label(e.getPosition()));
            f.put("facing", COMPASS[((e.getFacing() % 6) + 6) % 6]);
            f.put("gunnery", e.getCrew().getGunnery());
            f.put("piloting", e.getCrew().getPiloting());
        }
        ObjectNode settings = JSON.createObjectNode();
        settings.set("FORCES", forces);
        settings.put("DEPLOYMENT", "fixed_hexes");
        settings.put("DEFAULT_BOARD_PATH", boardFile);
        ObjectNode line = JSON.createObjectNode();
        line.set("settings", settings);
        ArrayNode teams = line.putArray("hydra_teams");
        hydraTeams.forEach(teams::add);
        line.put("seed", seed);
        return line;
    }

    /**
     * The units that move AFTER {@code mover} this Movement Phase, in order (our engine's move queue; Hydra's forecast
     * reads it): MegaMek's remaining turns, each given to its player's next unit that has not moved (lowest id first,
     * as our engine's roster order), never the mover. A forecast, as ours is: a side may pick another unit when its
     * turn comes.
     */
    ArrayNode moveQueue(Game game, Entity mover) {
        ArrayNode queue = JSON.createArrayNode();
        java.util.Set<Integer> taken = new java.util.HashSet<>();
        taken.add(mover.getId());
        List<megamek.common.game.GameTurn> turns = game.getTurnsList();
        for (int t = game.getTurnIndex() + 1; t < turns.size(); t++) {
            int player = turns.get(t).playerId();
            for (int id : roster) {
                Entity e = game.getEntity(id);
                if (e != null && !taken.contains(id) && e.getOwnerId() == player && !e.isDone() && e.getPosition() != null) {
                    taken.add(id);
                    queue.add(roster.indexOf(id));
                    break;
                }
            }
        }
        return queue;
    }

    /** Every unit's state as MegaMek knows it now (a unit no longer in the game is sent as destroyed). */
    ObjectNode state(Game game) {
        ObjectNode state = JSON.createObjectNode();
        state.put("turn", game.getCurrentRound() + 1);   // our turns count from 1, MegaMek's rounds from 0
        ArrayNode units = state.putArray("megamek_units");
        for (int id : roster) {
            Entity e = game.getEntity(id);
            ObjectNode u = units.addObject();
            u.put("name", names.get(id));
            if (e == null || e.isDestroyed() || e.isDoomed()) {
                u.put("destroyed", true);
                u.putNull("hex");
                continue;
            }
            u.put("hex", label(e.getPosition()));
            u.put("facing", e.getFacing());
            u.put("prone", e.isProne());
            u.put("shutdown", e.isShutDown());
            u.put("heat", e.getHeat());
            u.put("destroyed", false);
            u.put("pilot_hits", e.getCrew().getHits());
            u.put("conscious", !e.getCrew().isUnconscious());
            u.put("twist", ((e.getSecondaryFacing() - e.getFacing() + 9) % 6) - 3);
            u.put("moved", switch (e.moved) {
                case MOVE_WALK -> "Walk";
                case MOVE_RUN -> "Run";
                case MOVE_JUMP -> "Jump";
                default -> "Stand Still";
            });
            // "done": has the unit had its Movement Phase turn this round (our engine's moved_this_turn: a unit that stood
            // still has moved too)? In the Movement Phase that is MegaMek's isDone(); before it no one has, after it everyone
            // has. "moved" alone cannot tell a unit that stood still from one still to move (CASPAR's review, 2026-11-19).
            boolean afterMovement = game.getPhase().isMovementReport() || game.getPhase().isOffboard()
                  || game.getPhase().isOffboardReport() || game.getPhase().isPreFiring() || game.getPhase().isFiring()
                  || game.getPhase().isFiringReport() || game.getPhase().isPhysical() || game.getPhase().isPhysicalReport()
                  || game.getPhase().isEnd() || game.getPhase().isEndReport();
            u.put("done", game.getPhase().isMovement() ? e.isDone() : afterMovement);
            u.put("mp_spent", e.mpUsed);
            u.put("hexes_moved", e.delta_distance);
            ObjectNode locs = u.putObject("locations");
            ArrayNode slots = u.putArray("destroyed_slots");
            ObjectNode ammo = u.putObject("ammo");
            ArrayNode jammed = u.putArray("jammed");
            ArrayNode fired = u.putArray("fired");   // weapons fired this turn (what fired limits what punches)
            for (int loc = 0; loc < e.locations(); loc++) {
                String name = e.getLocationName(loc);
                ObjectNode l = locs.putObject(name);
                l.put("armor", Math.max(0, e.getArmor(loc, false)));
                if (e.hasRearArmor(loc)) {
                    l.put("rear", Math.max(0, e.getArmor(loc, true)));
                }
                l.put("structure", Math.max(0, e.getInternal(loc)));
                l.put("destroyed", e.isLocationBad(loc));
                for (int i = 0; i < e.getNumberOfCriticalSlots(loc); i++) {
                    CriticalSlot cs = e.getCritical(loc, i);
                    if (cs == null) {
                        continue;
                    }
                    if (cs.isDestroyed() || cs.isHit() || cs.isMissing()) {
                        slots.addArray().add(name).add(i);
                    }
                    Mounted<?> m = cs.getMount();
                    if (m != null && firstSlot(e, m) == i && m.getLocation() == loc) {
                        String addr = name + "#" + i;
                        if (m.getType() instanceof megamek.common.equipment.AmmoType) {
                            ammo.put(addr, m.getBaseShotsLeft());
                        }
                        if (m.isJammed()) {
                            jammed.add(addr);
                        }
                        if (m.isUsedThisRound()) {
                            fired.add(addr);
                        }
                    }
                }
            }
        }
        return state;
    }

    /** The first critical slot a mounted item fills in its location (its "address" in our engine), or -1. */
    static int firstSlot(Entity e, Mounted<?> m) {
        int loc = m.getLocation();
        for (int i = 0; i < e.getNumberOfCriticalSlots(loc); i++) {
            CriticalSlot cs = e.getCritical(loc, i);
            if (cs != null && cs.getMount() == m) {
                return i;
            }
        }
        return -1;
    }

    /** The mounted item at one of our addresses ("Left Torso#3"), or null. */
    static Mounted<?> mountedAt(Entity e, String addr) {
        int hash = addr.lastIndexOf('#');
        String locName = addr.substring(0, hash);
        int slot = Integer.parseInt(addr.substring(hash + 1));
        for (int loc = 0; loc < e.locations(); loc++) {
            if (e.getLocationName(loc).equals(locName)) {
                CriticalSlot cs = e.getCritical(loc, slot);
                return (cs == null) ? null : cs.getMount();
            }
        }
        return null;
    }
}
