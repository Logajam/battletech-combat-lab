/*
 * MegaMek bridge (INTEGRATION__MEGAMEK_BRIDGE.md), stage B2/B5. GPL v3: built on MegaMek (see megamek_bridge/README.md).
 * The game set-up follows MegaMek's own megamek.utilities.ScenarioGameRunner (which only creates MegaMek's bots).
 */
package btbridge;

import static megamek.MMConstants.LOCALHOST_IP;

import java.io.File;
import java.io.FileWriter;
import java.io.ObjectInputFilter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

import megamek.MMConstants;
import megamek.client.AbstractClient;
import megamek.client.HeadlessClient;
import megamek.client.bot.AIType;
import megamek.client.bot.BotClient;
import megamek.client.bot.BotFactory;
import megamek.client.bot.princess.BehaviorSettings;
import megamek.client.bot.princess.BehaviorSettingsFactory;
import megamek.common.Player;
import megamek.common.enums.GamePhase;
import megamek.common.event.GameListenerAdapter;
import megamek.common.event.GamePhaseChangeEvent;
import megamek.common.game.Game;
import megamek.common.game.IGame;
import megamek.common.interfaces.IEntityRemovalConditions;
import megamek.common.jacksonAdapters.BotParser;
import megamek.common.loaders.MekSummaryCache;
import megamek.common.net.marshalling.SanityInputFilter;
import megamek.common.scenario.Scenario;
import megamek.common.scenario.ScenarioLoader;
import megamek.common.units.EjectedCrew;
import megamek.common.units.Entity;
import megamek.server.Server;
import megamek.server.totalWarfare.TWGameManager;

/**
 * Plays ONE game of a MegaMek scenario ({@code .mms}) with our engine driving the named players and MegaMek's own
 * bots (Princess or CASPAR, from the scenario's {@code ai:} key) driving the rest, then appends one JSON line to the
 * records file and exits. One game per run because MegaMek's runner sometimes stalls in round 0 (spec Section 1b);
 * the caller runs it again for each game and retries a stalled one.
 *
 * <pre>
 * java -cp 'megamek_bridge.jar:MEGAMEK/MegaMek.jar:MEGAMEK/lib/*' btbridge.BridgeLauncher SCENARIO.mms
 *      --btsim PATH --bridge PLAYER[,PLAYER] [--rounds 100] [--timeout 10] [--records FILE] [--label TEXT]
 * </pre>
 * Run from the MegaMek folder (it reads its data/ and mmconf/ from there).
 */
public final class BridgeLauncher {
    static {
        MekSummaryCache.getInstance();
        ObjectInputFilter.Config.setSerialFilter(new SanityInputFilter());
    }

    private BridgeLauncher() {}

    private static String arg(String[] args, String name, String fallback) {
        for (int i = 0; i < args.length - 1; i++) {
            if (args[i].equals(name)) {
                return args[i + 1];
            }
        }
        return fallback;
    }

    /**
     * Bot behaviour for bridge games (spec Section 7): MegaMek's bots fight to the end, as ours do. By default they
     * withdraw when crippled and may flee the board (in B0 a Princess 'Mech fled, and MegaMek's runner then misread
     * the game).
     */
    private static BehaviorSettings fightToTheEnd(BehaviorSettings settings) throws Exception {
        BehaviorSettings copy = settings.getCopy();
        copy.setForcedWithdrawal(false);
        copy.setAutoFlee(false);
        return copy;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: BridgeLauncher SCENARIO.mms --btsim PATH --bridge PLAYER[,PLAYER] [--rounds N]"
                  + " [--timeout MINUTES] [--records FILE] [--label TEXT]");
            System.exit(2);
        }
        File scenarioFile = new File(args[0]);
        String btsim = arg(args, "--btsim", "btsim");
        Set<String> bridged = new TreeSet<>(List.of(arg(args, "--bridge", "").split(",")));
        bridged.remove("");
        int rounds = Integer.parseInt(arg(args, "--rounds", "100"));
        int timeout = Integer.parseInt(arg(args, "--timeout", "10"));
        String records = arg(args, "--records", "bridge_records.jsonl");
        String label = arg(args, "--label", "");
        // our data folder (the .mtf files our engine loads): --data, else beside btsim (REPO/engine/target/release/btsim)
        File btsimFile = new File(btsim).getAbsoluteFile();
        File repo = btsimFile.getParentFile() == null ? new File(".") : btsimFile.getParentFile().getParentFile().getParentFile().getParentFile();
        File dataDir = new File(arg(args, "--data", new File(repo, "data").getPath()));
        String boardFile = boardOf(scenarioFile);
        long seed = Long.parseLong(arg(args, "--seed", String.valueOf(new Random().nextInt(1 << 30))));

        TWGameManager gameManager = new TWGameManager();
        Server server = new Server(null, new Random().nextInt(MMConstants.MIN_PORT_FOR_QUICK_GAME, MMConstants.MAX_PORT),
              gameManager, false, "", null, true);
        List<AbstractClient> clients = new ArrayList<>();
        List<HydraBridge> ours = new ArrayList<>();
        Map<String, String> botOf = new TreeMap<>();
        String line;
        try {
            Scenario scenario = new ScenarioLoader(scenarioFile).load();
            IGame loaded = scenario.createGame();
            if (!(loaded instanceof Game game)) {
                throw new IllegalArgumentException("Only Total Warfare scenarios are supported: " + scenarioFile);
            }
            server.setGame(game);
            scenario.applyDamage(gameManager);
            gameManager.calculatePlayerInitialCounts();
            List<Player> atStart = List.copyOf(game.getPlayersList());

            List<Player> players = new ArrayList<>(game.getPlayersList());
            players.sort(Comparator.comparingInt(Player::getId));
            Player watcherSlot = players.getFirst();
            CountDownLatch roundCounter = new CountDownLatch(rounds);
            // The standings, saved at every round's end report and at victory: when a game ends MegaMek resets it (round
            // -1, units gone), so a record read afterwards would show no one left (B4: a Hydra win was misread that way).
            java.util.concurrent.atomic.AtomicReference<String> saved = new java.util.concurrent.atomic.AtomicReference<>();
            int[] lastRound = {0};
            HeadlessClient watcher = new HeadlessClient(watcherSlot.getName(), LOCALHOST_IP, server.getPort());
            watcher.getGame().addGameListener(new GameListenerAdapter() {
                @Override
                public void gamePhaseChange(GamePhaseChangeEvent event) {
                    GamePhase phase = event.getNewPhase();
                    if ((phase == GamePhase.END_REPORT || phase == GamePhase.VICTORY) && game.getCurrentRound() >= 0) {
                        lastRound[0] = game.getCurrentRound();
                        saved.set(record(label, scenarioFile.getName(), botOf, true, game, atStart, watcherSlot.getTeam(),
                              ours, 0, lastRound[0]));
                    }
                    if (phase == GamePhase.END_REPORT) {
                        roundCounter.countDown();
                        if (roundCounter.getCount() == 1) {
                            watcher.sendChat("/victory");
                        }
                    } else if (phase == GamePhase.VICTORY) {
                        while (roundCounter.getCount() > 0) {
                            roundCounter.countDown();
                        }
                    }
                    if (phase.isReport()) {
                        watcher.sendDone(true);
                    }
                }
            });
            clients.add(watcher);
            if (!watcher.connect()) {
                throw new IllegalStateException("the watcher could not connect");
            }
            waitFor(() -> watcher.getLocalPlayer() != null);

            for (Player slot : players.subList(1, players.size())) {
                String name = slot.getName();
                BotClient bot;
                if (bridged.contains(name)) {
                    // every line sent to our engine, for replaying a game's decisions offline (DecisionProcess)
                    File transcript = new File(arg(args, "--transcripts", "logs"),
                          "bridge_" + (label + "_" + name).replaceAll("[^A-Za-z0-9_.-]+", "_") + ".jsonl");
                    HydraBridge h = new HydraBridge(name, LOCALHOST_IP, server.getPort(), btsim, dataDir, boardFile, seed,
                          transcript);
                    // as MegaMek's BotFactory does for every Princess: without its background planner it waits forever
                    h.startPrecognition();
                    h.setBehaviorSettings(fightToTheEnd(BehaviorSettingsFactory.getInstance().DEFAULT_BEHAVIOR));
                    ours.add(h);
                    bot = h;
                    botOf.put(name, "bridge");
                } else {
                    AIType type = AIType.PRINCESS;
                    BehaviorSettings settings = BehaviorSettingsFactory.getInstance().DEFAULT_BEHAVIOR;
                    if (scenario.hasBotInfo(name) && scenario.getBotInfo(name) instanceof BotParser.PrincessRecord r) {
                        type = r.aiType();
                        settings = r.behaviorSettings();
                    }
                    bot = BotFactory.createBot(type, name, LOCALHOST_IP, server.getPort(), fightToTheEnd(settings));
                    botOf.put(name, type.name());
                }
                clients.add(bot);
                if (!bot.connect()) {
                    throw new IllegalStateException("bot " + name + " could not connect");
                }
                BotClient connected = bot;
                waitFor(() -> connected.getLocalPlayer() != null);
                bot.sendPlayerInfo();
            }

            long started = System.currentTimeMillis();
            boolean finished = roundCounter.await(timeout, TimeUnit.MINUTES);
            double seconds = (System.currentTimeMillis() - started) / 1000.0;
            if (game.getCurrentRound() < 0 && saved.get() != null) {
                // the game was reset when it ended: the standings saved at its last report, with the time filled in
                line = saved.get().replace("\"seconds\": 0.0", "\"seconds\": " + seconds);
            } else {
                line = record(label, scenarioFile.getName(), botOf, finished, game, atStart, watcherSlot.getTeam(), ours,
                      seconds, game.getCurrentRound());
            }
        } catch (Exception exception) {
            line = "{\"label\": " + q(label) + ", \"scenario\": " + q(scenarioFile.getName()) + ", \"error\": "
                  + q(String.valueOf(exception)) + "}";
        } finally {
            for (AbstractClient client : clients) {
                try {
                    client.die();
                } catch (Exception ignored) {
                    // one client failing to stop must not keep the others alive
                }
            }
            server.die();
        }
        try (PrintWriter out = new PrintWriter(new FileWriter(records, StandardCharsets.UTF_8, true))) {
            out.println(line);
        }
        System.out.println(line);
        System.exit(0);
    }

    /**
     * The board file a scenario names (its first {@code - file:} entry under {@code map: boards:}), as an absolute path
     * into MegaMek's data/boards folder (the launcher runs from the MegaMek folder). Our engine reads the same file.
     */
    static String boardOf(File scenario) throws java.io.IOException {
        for (String line : java.nio.file.Files.readAllLines(scenario.toPath(), StandardCharsets.UTF_8)) {
            String t = line.trim();
            if (t.startsWith("- file:")) {
                return new File("data/boards", t.substring("- file:".length()).trim()).getAbsolutePath();
            }
        }
        throw new IllegalArgumentException("no board file named in " + scenario);
    }

    private static void waitFor(BooleanSupplier condition) throws InterruptedException {
        for (int i = 0; i < 250 && !condition.getAsBoolean(); i++) {
            Thread.sleep(50);
        }
        if (!condition.getAsBoolean()) {
            throw new IllegalStateException("a client did not receive its player slot");
        }
    }

    /** One game's record line: who drove whom, the result, each team's standing, and our bot's decisions. */
    private static String record(String label, String scenario, Map<String, String> botOf, boolean finished, Game game,
          List<Player> atStart, int watcherTeam, List<HydraBridge> ours, double seconds, int round) {
        Map<Integer, Integer> teamOf = new HashMap<>();
        for (Player p : atStart) {
            teamOf.put(p.getId(), p.getTeam());
        }
        Map<Integer, int[]> tally = new TreeMap<>(); // team -> {fielded, survivors, destroyed, fled, bv start, bv left}
        for (Player p : atStart) {
            if (p.getTeam() != watcherTeam) {
                int[] t = tally.computeIfAbsent(p.getTeam(), k -> new int[6]);
                t[0] += p.getInitialEntityCount();
                t[4] += p.getInitialBV();
                t[5] += p.getBV();
            }
        }
        Set<Integer> standing = new TreeSet<>();
        for (Entity e : game.getEntitiesVector()) {
            Integer team = teamOf.get(e.getOwnerId());
            if (team == null || team == watcherTeam || e instanceof EjectedCrew) {
                continue;
            }
            if (e.isDestroyed()) {
                tally.get(team)[2]++;
            } else {
                tally.get(team)[1]++;
                standing.add(team);
            }
        }
        for (Entity e : game.getOutOfGameEntitiesVector()) {
            Integer team = teamOf.get(e.getOwnerId());
            if (team == null || team == watcherTeam || e instanceof EjectedCrew) {
                continue;
            }
            switch (e.getRemovalCondition()) {
                case IEntityRemovalConditions.REMOVE_SALVAGEABLE, IEntityRemovalConditions.REMOVE_EJECTED,
                     IEntityRemovalConditions.REMOVE_DEVASTATED -> tally.get(team)[2]++;
                case IEntityRemovalConditions.REMOVE_IN_RETREAT, IEntityRemovalConditions.REMOVE_CAPTURED,
                     IEntityRemovalConditions.REMOVE_PUSHED -> tally.get(team)[3]++;
                default -> { }
            }
        }
        StringBuilder s = new StringBuilder("{\"label\": ").append(q(label))
              .append(", \"scenario\": ").append(q(scenario))
              .append(", \"finished\": ").append(finished)
              .append(", \"rounds\": ").append(round)
              .append(", \"winning_team\": ").append(winner(tally, standing))
              .append(", \"seconds\": ").append(seconds)
              .append(", \"players\": {");
        String sep = "";
        for (Map.Entry<String, String> e : botOf.entrySet()) {
            s.append(sep).append(q(e.getKey())).append(": ").append(q(e.getValue()));
            sep = ", ";
        }
        s.append("}, \"teams\": {");
        sep = "";
        for (Map.Entry<Integer, int[]> e : tally.entrySet()) {
            int[] t = e.getValue();
            s.append(sep).append(q(String.valueOf(e.getKey()))).append(": {\"fielded\": ").append(t[0])
                  .append(", \"survivors\": ").append(t[1]).append(", \"destroyed\": ").append(t[2])
                  .append(", \"fled\": ").append(t[3]).append(", \"bv_start\": ").append(t[4])
                  .append(", \"bv_left\": ").append(t[5]).append("}");
            sep = ", ";
        }
        s.append("}, \"bridge\": [");
        sep = "";
        for (HydraBridge h : ours) {
            s.append(sep).append("{\"player\": ").append(q(h.getName()))
                  .append(", \"engine\": ").append(q(h.engineStatus()))
                  .append(", \"decisions\": ").append(h.decisions())
                  .append(", \"ours\": {");
            String sep3 = "";
            for (Map.Entry<String, Integer> f : h.made().entrySet()) {
                s.append(sep3).append(q(f.getKey())).append(": ").append(f.getValue());
                sep3 = ", ";
            }
            s.append("}, \"fallbacks\": {");
            String sep2 = "";
            for (Map.Entry<String, Integer> f : h.fallbacks().entrySet()) {
                s.append(sep2).append(q(f.getKey())).append(": ").append(f.getValue());
                sep2 = ", ";
            }
            s.append("}}");
            sep = ", ";
        }
        return s.append("]}").toString();
    }

    /**
     * The winning team: the only one with Battle Value left (a destroyed or removed unit counts 0; units leave MegaMek's
     * list when a game ends, so a count of the units still listed can show no one standing). Else the only team with a
     * unit standing; else none (a draw, or not decided).
     */
    private static String winner(Map<Integer, int[]> tally, Set<Integer> standing) {
        List<Integer> withBv = new ArrayList<>();
        tally.forEach((team, t) -> {
            if (t[5] > 0) {
                withBv.add(team);
            }
        });
        if (withBv.size() == 1) {
            return String.valueOf(withBv.getFirst());
        }
        return (withBv.isEmpty() && standing.size() == 1) ? String.valueOf(standing.iterator().next()) : "null";
    }

    /** A JSON string. */
    private static String q(String text) {
        StringBuilder s = new StringBuilder("\"");
        for (char c : text.toCharArray()) {
            switch (c) {
                case '"' -> s.append("\\\"");
                case '\\' -> s.append("\\\\");
                case '\n' -> s.append("\\n");
                case '\r' -> s.append("\\r");
                case '\t' -> s.append("\\t");
                default -> {
                    if (c < 0x20) {
                        s.append(String.format("\\u%04x", (int) c));
                    } else {
                        s.append(c);
                    }
                }
            }
        }
        return s.append('"').toString();
    }
}
