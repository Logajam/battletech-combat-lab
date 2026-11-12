/*
 * MegaMek bridge (INTEGRATION__MEGAMEK_BRIDGE.md), stage B2. GPL v3: built on MegaMek (see megamek_bridge/README.md).
 */
package btbridge;

import java.io.IOException;
import java.util.Map;
import java.util.TreeMap;

import megamek.client.bot.PhysicalOption;
import megamek.client.bot.princess.Princess;
import megamek.common.moves.MovePath;
import megamek.logging.MMLogger;

/**
 * A MegaMek bot player whose decisions come from our engine (Hydra, Gladiator or our Princess clone), built the way
 * MegaMek's own CASPAR is: Princess with a few parts replaced. Movement, firing and physical attacks are asked of
 * {@code btsim decide}; everything else (deployment, morale, unit types our engine does not model) stays Princess's.
 *
 * <p>STAGE B2 (this version): the plumbing only. The decision process is started and checked, and every decision
 * is a FALLBACK to Princess, counted by reason, because the game state is not translated yet (stage B3) nor are the
 * answers (stage B4). A game played with this bot is therefore Princess's game; that is B2's check.</p>
 */
public class HydraBridge extends Princess {
    private static final MMLogger LOGGER = MMLogger.create(HydraBridge.class);

    /** Why a decision went to Princess, until B3 and B4 are built. */
    static final String NOT_TRANSLATED = "game state not translated yet (bridge stage B3)";

    private final DecisionProcess engine;
    private final String engineStatus;
    private final Map<String, Integer> fallbacks = new TreeMap<>();
    private int decisions;

    /**
     * @param name  the player's name, as in the scenario
     * @param host  the MegaMek server
     * @param port  its port
     * @param btsim the path to our engine's {@code btsim} binary
     */
    public HydraBridge(String name, String host, int port, String btsim) {
        super(name, host, port);
        DecisionProcess started = null;
        String status;
        try {
            started = new DecisionProcess(btsim);
            status = started.ask("{\"ping\": true}");
        } catch (IOException exception) {
            status = "could not start btsim decide: " + exception.getMessage();
            LOGGER.error(exception, status);
        }
        engine = started;
        engineStatus = status;
    }

    /** The decision process's answer to the start-up ping, or why it could not start. */
    public String engineStatus() {
        return engineStatus;
    }

    /** Every decision this bot was asked for. */
    public int decisions() {
        return decisions;
    }

    /** The FALLBACKs so far, by reason (Princess decided instead of our engine). */
    public Map<String, Integer> fallbacks() {
        return new TreeMap<>(fallbacks);
    }

    private void fallback(String reason) {
        decisions++;
        fallbacks.merge(reason, 1, Integer::sum);
    }

    @Override
    protected MovePath calculateMoveTurn() {
        fallback(NOT_TRANSLATED);
        return super.calculateMoveTurn();
    }

    @Override
    protected void calculateFiringTurn() {
        fallback(NOT_TRANSLATED);
        super.calculateFiringTurn();
    }

    @Override
    protected PhysicalOption calculatePhysicalTurn() {
        fallback(NOT_TRANSLATED);
        return super.calculatePhysicalTurn();
    }

    @Override
    public void die() {
        if (engine != null) {
            engine.close();
        }
        super.die();
    }
}
