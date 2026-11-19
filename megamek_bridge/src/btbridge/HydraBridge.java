/*
 * MegaMek bridge (INTEGRATION__MEGAMEK_BRIDGE.md), stages B2-B4. GPL v3: built on MegaMek (see README.md).
 */
package btbridge;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.Vector;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import megamek.client.bot.PhysicalOption;
import megamek.common.actions.DfaAttackAction;
import megamek.common.actions.ChargeAttackAction;
import megamek.client.bot.princess.Princess;
import megamek.common.actions.EntityAction;
import megamek.common.actions.TorsoTwistAction;
import megamek.common.actions.WeaponAttackAction;
import megamek.common.board.Coords;
import megamek.common.enums.GamePhase;
import megamek.common.enums.MoveStepType;
import megamek.common.equipment.Mounted;
import megamek.common.game.Game;
import megamek.common.game.GameTurn;
import megamek.common.moves.MovePath;
import megamek.common.moves.MoveStep;
import megamek.common.rolls.TargetRoll;
import megamek.common.units.Entity;
import megamek.common.units.Targetable;
import megamek.logging.MMLogger;

/**
 * A MegaMek bot player whose decisions come from our engine (Hydra by default), built the way MegaMek's own CASPAR is:
 * Princess with a few parts replaced. Each decision: our engine's copy of the game is brought up to date (the start from
 * settings, then every unit's state as MegaMek knows it, {@link GameView}), the question is asked of
 * {@code btsim decide}, and the answer is turned into MegaMek's orders. Anything that can't be done that way (the
 * engine failed to start, a unit file missing, a move MegaMek won't accept, a prone unit, a charge...) goes to
 * Princess instead: a FALLBACK, counted by reason in the game's record. Physical attacks stay Princess's in this
 * version.
 */
public class HydraBridge extends Princess {
    private static final MMLogger LOGGER = MMLogger.create(HydraBridge.class);

    private final DecisionProcess engine;
    private final String engineStatus;
    private final File dataDir;
    private final String boardFile;
    private final long seed;
    private final Map<String, Integer> fallbacks = new TreeMap<>();
    private final Map<String, Integer> made = new TreeMap<>();
    private int decisions;

    private GameView view;
    private final List<String> rulesNotes = new ArrayList<>();
    private boolean broken;
    private String brokenWhy;
    /** The round our engine last heard a Movement / Weapon Attack phase start in. */
    private int movementRound = -1;
    private int firingRound = -1;
    /** Where each unit stood when this round's movement began, and which units' moves were already reported. */
    private final Map<Integer, String> startHex = new HashMap<>();
    private final Set<Integer> reportedMoved = new HashSet<>();

    /**
     * @param btsim     the path to our engine's {@code btsim} binary
     * @param dataDir   our data folder (the .mtf files our engine loads)
     * @param boardFile the game's board file, absolute
     */
    public HydraBridge(String name, String host, int port, String btsim, File dataDir, String boardFile, long seed,
          File transcript) {
        super(name, host, port);
        this.dataDir = dataDir;
        this.boardFile = boardFile;
        this.seed = seed;
        DecisionProcess started = null;
        String status;
        try {
            started = new DecisionProcess(btsim, transcript);
            status = started.ask("{\"ping\": true}");
        } catch (IOException exception) {
            status = "could not start btsim decide: " + exception.getMessage();
            LOGGER.error(exception, status);
        }
        engine = started;
        engineStatus = status;
        if (engine == null) {
            broken = true;
            brokenWhy = status;
        }
    }

    public String engineStatus() {
        return engineStatus;
    }

    public int decisions() {
        return decisions;
    }

    /** Princess decided instead of our engine, by reason. */
    /** Our engine's notes on MegaMek's game options: what it set to match them, what it cannot follow. */
    public List<String> rulesNotes() {
        return rulesNotes;
    }

    public Map<String, Integer> fallbacks() {
        return new TreeMap<>(fallbacks);
    }

    /** Our engine decided, by kind of decision. */
    public Map<String, Integer> made() {
        return new TreeMap<>(made);
    }

    private void fallback(String reason) {
        fallbacks.merge(reason, 1, Integer::sum);
    }

    // ---- talking to our engine -------------------------------------------------------------------------------------

    /** Starts our engine's copy of the game on the first question; false (and a reason) if it can't. */
    private boolean ready() {
        if (broken) {
            return false;
        }
        if (view != null) {
            return true;
        }
        try {
            view = new GameView();
            StringBuilder why = new StringBuilder();
            ObjectNode start = view.start(getGame(), boardFile, dataDir, List.of("T" + getLocalPlayer().getTeam()), seed, why);
            if (start == null) {
                return breakWith(why.toString());
            }
            JsonNode reply = GameView.JSON.readTree(engine.ask(start.toString()));   // (a failure here: caught below)
            if (!reply.path("started").asBoolean(false)) {
                return breakWith("our engine could not build the game: " + reply.path("error").asText(reply.toString()));
            }
            // what our engine set to match MegaMek's game options, and the options it cannot follow (kept in the record)
            for (JsonNode note : reply.path("rules")) {
                rulesNotes.add(note.asText());
                LOGGER.info("[bridge] rules: {}", note.asText());
            }
            return true;
        } catch (Exception exception) {
            LOGGER.error(exception, "bridge start");
            return breakWith("bridge start failed: " + exception);
        }
    }

    private boolean breakWith(String why) {
        broken = true;
        brokenWhy = why;
        LOGGER.error("Bridge disabled for this game: {}", why);
        return false;
    }

    /** One call: brings the units up to date and asks; the answer, or null after an error (logged). */
    private JsonNode ask(String method, ObjectNode args) throws IOException {
        return ask(method, args, null);
    }

    /** One call; with a mover, the state also carries who moves after it (the move queue). */
    private JsonNode ask(String method, ObjectNode args, Entity mover) throws IOException {
        ObjectNode line = GameView.JSON.createObjectNode();
        line.put("method", method);
        line.set("args", args);
        ObjectNode state = view.state(getGame());
        if (mover != null) {
            state.set("move_queue", view.moveQueue(getGame(), mover));
        }
        line.set("state", state);
        JsonNode reply;
        try {
            reply = GameView.JSON.readTree(engine.ask(line.toString()));
        } catch (IOException gone) {
            // the process died or ran past its time limit: our engine is out for the rest of this game
            breakWith(gone.getMessage());
            throw gone;
        }
        if (reply.has("error")) {
            LOGGER.error("btsim decide, {}: {}", method, reply.get("error").asText());
            return null;
        }
        return reply.get("answer");
    }

    private static ObjectNode args() {
        return GameView.JSON.createObjectNode();
    }

    /**
     * The signals our bots' memories are built from (bridge.rs: the engine sends them at these moments): a new
     * round's Movement Phase starts (after the last round's end), and each unit that has moved since we last asked.
     */
    private void signalsForMovement() throws IOException {
        Game game = getGame();
        int round = game.getCurrentRound();
        if (round != movementRound) {
            if (movementRound >= 0) {
                ask("end_of_turn", args());
            }
            movementRound = round;
            startHex.clear();
            reportedMoved.clear();
            for (int id : view.roster) {
                Entity e = game.getEntity(id);
                startHex.put(id, e == null ? null : GameView.label(e.getPosition()));
            }
            ask("start_movement", args());
        }
        for (int id : view.roster) {
            Entity e = game.getEntity(id);
            if (e != null && e.isDone() && !reportedMoved.contains(id) && game.getPhase() == GamePhase.MOVEMENT) {
                reportedMoved.add(id);
                ObjectNode a = args();
                a.put("mover", view.roster.indexOf(id));
                a.put("start_hex", startHex.get(id));
                ask("unit_moved", a);
            }
        }
    }

    // ---- movement --------------------------------------------------------------------------------------------------

    @Override
    protected MovePath calculateMoveTurn() {
        decisions++;
        try {
            MovePath ours = ourMove();
            if (ours != null) {
                made.merge("move", 1, Integer::sum);
                return ours;
            }
        } catch (Exception exception) {
            LOGGER.error(exception, "bridge move");
            fallback("move: error " + exception.getClass().getSimpleName());
        }
        return super.calculateMoveTurn();
    }

    /** Our engine's move for one of our units, as a MegaMek path; null (a fallback counted) when it can't be used. */
    private MovePath ourMove() throws IOException {
        if (!ready()) {
            fallback("bridge off: " + brokenWhy);
            return null;
        }
        Game game = getGame();
        signalsForMovement();
        GameTurn turn = game.getTurnForPlayer(getLocalPlayerNumber());
        List<Entity> movable = new ArrayList<>();
        for (Entity e : getEntitiesOwned()) {
            if (!e.isDone() && e.isDeployed() && e.getPosition() != null && turn != null && turn.isValidEntity(e, game)
                  && view.index(e) >= 0) {
                movable.add(e);
            }
        }
        if (movable.isEmpty()) {
            fallback("move: no unit of ours to move");
            return null;
        }
        ArrayNode candidates = GameView.JSON.createArrayNode();
        movable.forEach(e -> candidates.add(view.index(e)));
        ObjectNode a = args();
        a.set("candidates", candidates);
        JsonNode picked = ask("move_pick", a);
        Entity mover = movable.getFirst();
        if (picked != null && picked.isInt()) {
            Entity p = game.getEntity(view.roster.get(picked.asInt()));
            if (movable.contains(p)) {
                mover = p;
            }
        }
        // A prone unit plans with the MP left after standing (Core p.98: standing costs 2 MP; our engine rolls the stand
        // inside its own battle, here MegaMek rolls it during the move), and the route starts with GET_UP.
        Integer standupMp = null;
        if (mover.isProne()) {
            // Core p.51: standing costs 2 MP, but a prone 'Mech with only 1 MP may still make one attempt (minimum movement);
            // whether it can stand at all (gyro, limbs) our engine decides, and answers with turns on the ground if not
            if (mover.getRunMP() < 1) {
                fallback("move: prone unit with no MP");
                return null;
            }
            standupMp = Math.max(mover.getRunMP() - 2, 0);
        }
        int me = view.index(mover);
        a = args();
        a.put("mover", me);
        JsonNode foe = ask("choose_foe", a);
        if (foe == null || !foe.isInt()) {
            fallback("move: no foe");
            return null;
        }
        Entity other = game.getEntity(view.roster.get(foe.asInt()));
        a = args();
        a.put("mover", me);
        a.put("other", foe.asInt());
        a.put("moves_first", other != null && !other.isDone());
        if (standupMp == null) {
            a.putNull("standup_mp");
        } else {
            a.put("standup_mp", standupMp);
        }
        a.putNull("entry_edge");
        JsonNode choice = ask("choose_movement", a, mover);
        if (choice == null || choice.get("pick") == null || choice.get("pick").isNull()) {
            fallback("move: our engine found no move");
            return null;
        }
        JsonNode pick = choice.get("pick");
        boolean charge = pick.path("charge").asBoolean(), dfa = pick.path("dfa").asBoolean();
        a = args();
        a.put("mover", me);
        a.set("pick", pick);
        if (standupMp == null) {
            a.putNull("standup_mp");
        } else {
            a.put("standup_mp", standupMp);
        }
        JsonNode steps = ask("path_steps", a, mover);
        Coords dest = GameView.coords(pick.get("hex").asText());
        int facing = compass(pick.get("facing").asText());
        String mode = pick.get("mode").asText();
        if (charge || dfa) {
            // the pick is the hex next to the target, facing it: the target stands one hex on in that facing
            MovePath attack = buildMovementAttack(mover, steps, dest.translated(facing), other, dfa, standupMp != null);
            LOGGER.info("[bridge] round {} {}: {} -> {} at {} steps {} => {}", game.getCurrentRound(), dfa ? "death from above" : "charge",
                  mover.getDisplayName(), other == null ? "nobody" : other.getDisplayName(), GameView.label(dest.translated(facing)), steps, attack);
            if (attack == null) {
                fallback("move: MegaMek would not take the " + (dfa ? "death from above" : "charge") + " on " + GameView.label(dest.translated(facing)));
            } else {
                made.merge(dfa ? "move: death from above" : "move: charge", 1, Integer::sum);
            }
            return attack;
        }
        MovePath path = build(mover, steps, dest, facing, mode, standupMp != null);
        LOGGER.info("[bridge] round {} move: {} -> {} {} {} steps {} => {}", game.getCurrentRound(), mover.getDisplayName(),
              pick.get("hex").asText(), pick.get("facing").asText(), mode, steps, path);
        if (path == null) {
            fallback("move: MegaMek would not take the route to " + pick.get("hex").asText() + " (" + mode + ")");
        }
        return path;
    }

    private static int compass(String c) {
        return List.of("N", "NE", "SE", "S", "SW", "NW").indexOf(c);
    }

    /**
     * The move as a MegaMek path: our engine's steps first; if MegaMek refuses them (or for a jump), MegaMek's own
     * path finder to the same hex, then turns to the same facing. Null if neither is legal and ends where we chose.
     */
    private MovePath build(Entity mover, JsonNode steps, Coords dest, int facing, String mode, boolean standUp) {
        Game game = getGame();
        if ("Stand Still".equals(mode) && !standUp) {
            return new MovePath(game, mover);
        }
        if (steps != null && steps.has("steps")) {
            MovePath p = new MovePath(game, mover);
            for (JsonNode s : steps.get("steps")) {
                switch (s.asText()) {
                    case "forward" -> p.addStep(MoveStepType.FORWARDS);
                    case "backward" -> p.addStep(MoveStepType.BACKWARDS);
                    case "turn_left" -> p.addStep(MoveStepType.TURN_LEFT);
                    case "turn_right" -> p.addStep(MoveStepType.TURN_RIGHT);
                    case "get_up" -> p.addStep(MoveStepType.GET_UP);
                    default -> {
                        return null;
                    }
                }
            }
            if (fits(p, dest, facing)) {
                return p;
            }
            explainRefusal(mover, p, dest, facing);
        }
        MovePath p = new MovePath(game, mover);
        if (standUp) {
            p.addStep(MoveStepType.GET_UP);
        }
        if ("Jump".equals(mode)) {
            p.addStep(MoveStepType.START_JUMP);
        }
        if (!dest.equals(p.getFinalCoords())) {
            p.findPathTo(dest, MoveStepType.FORWARDS);
        }
        turnTo(p, facing);
        return fits(p, dest, facing) ? p : null;
    }

    /**
     * A charge or a death from above as MegaMek takes it (as its own movement screen builds one, MovementDisplay): a charge
     * is our route to the hex next to the target then a CHARGE step into the target's hex; a death from above, MegaMek's
     * path finder jumping to the target with the DFA step last (jumps always go to its path finder here). The step carries
     * the target; MegaMek's own to-hit must allow the attack. Null when it cannot be made (a fallback, counted).
     */
    private MovePath buildMovementAttack(Entity mover, JsonNode steps, Coords targetHex, Entity target, boolean dfa, boolean standUp) {
        Game game = getGame();
        if (target == null || target.getPosition() == null || !target.getPosition().equals(targetHex)) {
            LOGGER.info("[bridge] movement attack: the foe is not on {}", GameView.label(targetHex));
            return null;
        }
        MoveStepType type = dfa ? MoveStepType.DFA : MoveStepType.CHARGE;
        List<MovePath> tries = new ArrayList<>();
        if (!dfa && steps != null && steps.has("steps")) {
            MovePath p = new MovePath(game, mover);
            boolean ok = true;
            for (JsonNode st : steps.get("steps")) {
                switch (st.asText()) {
                    case "forward" -> p.addStep(MoveStepType.FORWARDS);
                    case "backward" -> p.addStep(MoveStepType.BACKWARDS);
                    case "turn_left" -> p.addStep(MoveStepType.TURN_LEFT);
                    case "turn_right" -> p.addStep(MoveStepType.TURN_RIGHT);
                    case "get_up" -> p.addStep(MoveStepType.GET_UP);
                    default -> ok = false;
                }
            }
            if (ok) {
                p.addStep(type);
                tries.add(p);
            }
        }
        MovePath planned = new MovePath(game, mover);
        if (standUp) {
            planned.addStep(MoveStepType.GET_UP);
        }
        if (dfa) {
            planned.addStep(MoveStepType.START_JUMP);
        }
        planned.findPathTo(targetHex, type);
        if (targetHex.equals(planned.getFinalCoords()) && (planned.getLastStep() == null || planned.getLastStep().getType() != type)) {
            planned.removeLastStep();
            planned.addStep(type);
        }
        tries.add(planned);
        for (MovePath p : tries) {
            if (p.getLastStep() == null || p.getLastStep().getType() != type || !targetHex.equals(p.getFinalCoords()) || !p.isMoveLegal()) {
                explainRefusal(mover, p, targetHex, p.getFinalFacing());
                continue;
            }
            p.getLastStep().setTarget(target);
            var toHit = dfa ? DfaAttackAction.toHit(game, mover.getId(), target, p) : new ChargeAttackAction(mover, target).toHit(game, p);
            LOGGER.info("[bridge]   {} to-hit {}: {}", dfa ? "death from above" : "charge", toHit.getValue(), toHit.getDesc());
            if (toHit.getValue() != TargetRoll.IMPOSSIBLE) {
                return p;
            }
        }
        return null;
    }

    /**
     * Why MegaMek would not take our steps (session 30, chasing "would not take the route"): each step's position, facing,
     * MP used, movement type and legality as MegaMek sees them, with the unit's MP, heat and posture.
     */
    private void explainRefusal(Entity mover, MovePath p, Coords dest, int facing) {
        StringBuilder sb = new StringBuilder();
        sb.append("walk ").append(mover.getWalkMP()).append(" run ").append(mover.getRunMP()).append(" jump ")
              .append(mover.getJumpMP()).append(", heat ").append(mover.heat).append(", prone ").append(mover.isProne())
              .append(", done ").append(mover.isDone()).append(", at ").append(GameView.label(mover.getPosition()))
              .append(" facing ").append(mover.getFacing()).append(";");
        for (MoveStep st : p.getStepVector()) {
            sb.append(" ").append(st.getType()).append("->").append(GameView.label(st.getPosition())).append("/")
                  .append(st.getFacing()).append(" mp ").append(st.getMpUsed()).append(" ")
                  .append(st.getMovementType(st == p.getLastStep())).append(st.isLegal(p) ? "" : " ILLEGAL");
        }
        sb.append("; path legal ").append(p.isMoveLegal()).append(", ends ").append(GameView.label(p.getFinalCoords()))
              .append(" facing ").append(p.getFinalFacing()).append(" (wanted ").append(GameView.label(dest)).append(" facing ")
              .append(facing).append(")");
        LOGGER.info("[bridge] refused steps: {}", sb);
    }

    private static void turnTo(MovePath p, int facing) {
        for (int i = 0; i < 6 && p.getFinalFacing() != facing; i++) {
            int diff = ((facing - p.getFinalFacing()) % 6 + 6) % 6;
            p.addStep(diff <= 3 ? MoveStepType.TURN_RIGHT : MoveStepType.TURN_LEFT);
        }
    }

    private static boolean fits(MovePath p, Coords dest, int facing) {
        return p.isMoveLegal() && dest.equals(p.getFinalCoords()) && p.getFinalFacing() == facing;
    }

    // ---- weapon attacks --------------------------------------------------------------------------------------------

    @Override
    protected void calculateFiringTurn() {
        decisions++;
        try {
            if (ourFire()) {
                made.merge("fire", 1, Integer::sum);
                return;
            }
        } catch (Exception exception) {
            LOGGER.error(exception, "bridge fire");
            fallback("fire: error " + exception.getClass().getSimpleName());
        }
        super.calculateFiringTurn();
    }

    /** Our engine's target and weapons for the unit whose turn it is, sent to MegaMek; false = a fallback (counted). */
    private boolean ourFire() throws IOException {
        if (!ready()) {
            fallback("bridge off: " + brokenWhy);
            return false;
        }
        Game game = getGame();
        Entity shooter = game.getFirstEntity(getMyTurn());
        if (shooter == null || view.index(shooter) < 0) {
            fallback("fire: no unit of ours to fire");
            return false;
        }
        if (game.getCurrentRound() != firingRound) {
            firingRound = game.getCurrentRound();
            ask("end_movement", args());
            ask("reset_assigned", args());
        }
        int me = view.index(shooter);
        ObjectNode a = args();
        a.put("attacker", me);
        JsonNode target = ask("choose_target", a);
        Vector<EntityAction> actions = new Vector<>();
        LOGGER.info("[bridge] round {} fire: {} targets {}", game.getCurrentRound(), shooter.getDisplayName(), target);
        if (target == null || !target.isInt()) {
            sendAttackData(shooter.getId(), actions);   // holds fire: no target in reach
            return true;
        }
        Entity foe = game.getEntity(view.roster.get(target.asInt()));
        if (foe == null) {
            fallback("fire: the target left the game");
            return false;
        }
        a = args();
        a.put("attacker", me);
        a.put("target", target.asInt());
        JsonNode decl = ask("choose_declaration", a);
        if (decl == null || decl.has("no_attack") || decl.path("weapons").isEmpty()) {
            LOGGER.info("[bridge] no attack on {} ({}) from {}{}; MegaMek's to-hit: {}", foe.getDisplayName(),
                  GameView.label(foe.getPosition()), GameView.label(shooter.getPosition()),
                  decl != null && decl.has("no_attack") ? " (our engine: no line of sight or cannot fire)" : " (our engine: no weapon worth firing)",
                  megamekToHit(game, shooter, foe));
            sendAttackData(shooter.getId(), actions);
            return true;
        }
        LOGGER.info("[bridge] declaration at {} ({}) from {}: {}", foe.getDisplayName(), GameView.label(foe.getPosition()),
              GameView.label(shooter.getPosition()), decl);
        int twist = decl.path("action").path("twist").asInt(0);
        if (decl.path("action").path("flip").asBoolean(false)) {
            fallback("fire: arm flip (not wired yet)");
            return false;
        }
        if (twist != 0) {
            actions.add(new TorsoTwistAction(shooter.getId(), ((shooter.getFacing() + twist) % 6 + 6) % 6));
            shooter.setSecondaryFacing(((shooter.getFacing() + twist) % 6 + 6) % 6, false);
        }
        int dropped = 0;
        for (JsonNode w : decl.path("weapons")) {
            Mounted<?> m = GameView.mountedAt(shooter, w.asText());
            if (m == null) {
                dropped++;
                continue;
            }
            WeaponAttackAction waa = new WeaponAttackAction(shooter.getId(), Targetable.TYPE_ENTITY, foe.getId(),
                  shooter.getEquipmentNum(m));
            var toHit = waa.toHit(game);
            LOGGER.info("[bridge]   {} ({}) to-hit {}: {}", w.asText(), m.getName(), toHit.getValue(), toHit.getDesc());
            if (toHit.getValue() == TargetRoll.IMPOSSIBLE) {
                dropped++;
                continue;
            }
            actions.add(waa);
        }
        if (twist != 0) {
            shooter.setSecondaryFacing(shooter.getFacing(), false);
        }
        if (dropped > 0) {
            made.merge("fire: weapons MegaMek ruled out of reach", dropped, Integer::sum);
        }
        sendAttackData(shooter.getId(), actions);
        return true;
    }

    /** MegaMek's own to-hit for each of the shooter's weapons at the target (for comparing the two engines' rules). */
    private static String megamekToHit(Game game, Entity shooter, Entity foe) {
        StringBuilder s = new StringBuilder();
        for (Mounted<?> w : shooter.getWeaponList()) {
            var toHit = new WeaponAttackAction(shooter.getId(), Targetable.TYPE_ENTITY, foe.getId(),
                  shooter.getEquipmentNum(w)).toHit(game);
            s.append(w.getName()).append(' ').append(toHit.getValue() == TargetRoll.IMPOSSIBLE ? "impossible (" + toHit.getDesc() + ")"
                  : String.valueOf(toHit.getValue())).append("; ");
        }
        return s.toString();
    }

    // ---- physical attacks: punches and kicks (anything else is Princess's, counted) ---------------------------------

    @Override
    protected PhysicalOption calculatePhysicalTurn() {
        decisions++;
        try {
            PhysicalOption ours = ourPhysical();
            if (ours != null) {
                made.merge("physical", 1, Integer::sum);
                return ours;
            }
        } catch (Exception exception) {
            LOGGER.error(exception, "bridge physical");
            fallback("physical: error " + exception.getClass().getSimpleName());
        }
        return super.calculatePhysicalTurn();
    }

    /** MegaMek's type for one of our engine's attack names ("punch (Left Arm)", "kick (Right Leg)"), or -1. */
    private static int physicalType(List<String> names) {
        if (names.size() == 2 && names.contains("punch (Left Arm)") && names.contains("punch (Right Arm)")) {
            return PhysicalOption.PUNCH_BOTH;
        }
        if (names.size() == 1 && names.getFirst().equals("push")) {
            return PhysicalOption.PUSH_ATTACK;
        }
        if (names.size() != 1) {
            return -1;
        }
        return switch (names.getFirst()) {
            case "punch (Left Arm)" -> PhysicalOption.PUNCH_LEFT;
            case "punch (Right Arm)" -> PhysicalOption.PUNCH_RIGHT;
            case "kick (Left Leg)" -> PhysicalOption.KICK_LEFT;
            case "kick (Right Leg)" -> PhysicalOption.KICK_RIGHT;
            default -> -1;
        };
    }

    /** Our engine's physical attack for the unit whose turn it is; a "no attack" option, or null for a fallback. */
    private PhysicalOption ourPhysical() throws IOException {
        if (!ready()) {
            fallback("bridge off: " + brokenWhy);
            return null;
        }
        Game game = getGame();
        Entity attacker = game.getFirstEntity(getMyTurn());
        if (attacker == null || view.index(attacker) < 0) {
            fallback("physical: no unit of ours");
            return null;
        }
        ObjectNode a = args();
        a.put("attacker", view.index(attacker));
        JsonNode target = ask("choose_target", a);
        if (target == null || !target.isInt()) {
            return new PhysicalOption(attacker);
        }
        Entity foe = game.getEntity(view.roster.get(target.asInt()));
        if (foe == null || foe.getPosition() == null || attacker.getPosition() == null
              || attacker.getPosition().distance(foe.getPosition()) != 1) {
            return new PhysicalOption(attacker);    // not adjacent: no physical attack
        }
        a = args();
        a.put("attacker", view.index(attacker));
        a.put("target", target.asInt());
        JsonNode choice = ask("choose_physical", a);
        if (choice == null || choice.isNull()) {
            return new PhysicalOption(attacker);
        }
        List<String> names = new ArrayList<>();
        choice.path("names").forEach(n -> names.add(n.asText()));
        int type = physicalType(names);
        LOGGER.info("[bridge] round {} physical: {} -> {} {}", game.getCurrentRound(), attacker.getDisplayName(),
              foe.getDisplayName(), names);
        if (type < 0 || choice.path("action").path("flip").asBoolean()) {
            fallback("physical: " + names + " (only punches, kicks and pushes are wired; no arm flip)");
            return null;
        }
        // the torso twist our engine attacks with, the same convention as in firing (torso facing = facing + twist). If it is
        // already the 'Mech's twist (made in the firing phase) nothing more is sent; otherwise a TorsoTwistAction goes first
        // (Core: a 'Mech that has not twisted this turn may twist as it declares physical attacks; MegaMek's Core Rules allow
        // it - CoreRulesUnits.getPhysicalTwistEnabled).
        int twist = choice.path("action").path("twist").asInt(0);
        int current = ((attacker.getSecondaryFacing() - attacker.getFacing() + 9) % 6) - 3;
        if (twist == current) {
            return new PhysicalOption(attacker, foe, 0, type, null);
        }
        if (!attacker.canChangeSecondaryFacing()) {
            fallback("physical: " + names + " with a twist MegaMek does not allow now");
            return null;
        }
        int torso = ((attacker.getFacing() + twist) % 6 + 6) % 6;
        TorsoTwistAction tta = new TorsoTwistAction(attacker.getId(), torso);
        return new PhysicalOption(attacker, foe, 0, type, null) {
            @Override
            public Vector<EntityAction> getVector() {
                Vector<EntityAction> v = new Vector<>();
                v.add(tta);
                v.addAll(super.getVector());
                return v;
            }
        };
    }

    @Override
    public void die() {
        if (engine != null) {
            engine.close();
        }
        super.die();
    }
}
