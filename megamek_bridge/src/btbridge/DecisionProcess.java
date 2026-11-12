/*
 * MegaMek bridge (INTEGRATION__MEGAMEK_BRIDGE.md). GPL v3: built on MegaMek (see megamek_bridge/README.md).
 */
package btbridge;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Our engine's decision process, {@code btsim decide}, as a child process: one JSON line in, one JSON line out
 * (engine/core/src/bridge.rs; spec Section 3b). It starts once per bot player and lives for the whole game, so our
 * bots' memories carry from turn to turn. Any failure (the process will not start, dies, answers with an error, or
 * takes longer than the time limit) is reported to the caller, which then lets Princess decide: a FALLBACK.
 *
 * <p>Every line sent is also written to a TRANSCRIPT file (when given): piped into {@code btsim decide} it replays the
 * game's decisions exactly, so a decision that hung or failed in a MegaMek game can be studied offline.</p>
 */
public final class DecisionProcess implements AutoCloseable {
    /** The longest one answer may take. A Hydra decision in a duel takes well under a second. */
    static final long TIME_LIMIT_SECONDS = 120;

    private final Process process;
    private final BufferedWriter toEngine;
    private final BlockingQueue<String> replies = new ArrayBlockingQueue<>(4);
    private final PrintWriter transcript;

    /**
     * @param btsim      the path to our engine's {@code btsim} binary
     * @param transcript the file every line sent is written to, or null for none
     */
    public DecisionProcess(String btsim, File transcript) throws IOException {
        process = new ProcessBuilder(btsim, "decide").redirectError(ProcessBuilder.Redirect.INHERIT).start();
        toEngine = new BufferedWriter(new OutputStreamWriter(process.getOutputStream(), StandardCharsets.UTF_8));
        this.transcript = (transcript == null) ? null
              : new PrintWriter(new FileWriter(transcript, StandardCharsets.UTF_8, false), true);
        BufferedReader fromEngine = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
        Thread reader = new Thread(() -> {
            try {
                for (String line = fromEngine.readLine(); line != null; line = fromEngine.readLine()) {
                    replies.put(line);
                }
            } catch (IOException | InterruptedException ignored) {
                // the process ended
            }
        }, "btsim decide reader");
        reader.setDaemon(true);
        reader.start();
    }

    /**
     * Sends one JSON line and returns the engine's one-line reply.
     *
     * @throws IOException if the process is gone, closed its output, or did not answer within the time limit (it is
     *                     then stopped: a later question fails at once)
     */
    public synchronized String ask(String jsonLine) throws IOException {
        if (!process.isAlive()) {
            throw new IOException("btsim decide is not running");
        }
        if (transcript != null) {
            transcript.println(jsonLine);
        }
        toEngine.write(jsonLine);
        toEngine.write('\n');
        toEngine.flush();
        try {
            String reply = replies.poll(TIME_LIMIT_SECONDS, TimeUnit.SECONDS);
            if (reply == null) {
                process.destroyForcibly();
                throw new IOException("btsim decide gave no answer in " + TIME_LIMIT_SECONDS + " s (stopped; the transcript has the question)");
            }
            return reply;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IOException("interrupted waiting for btsim decide");
        }
    }

    @Override
    public void close() {
        try {
            toEngine.close();
        } catch (IOException ignored) {
            // the process may already be gone
        }
        if (transcript != null) {
            transcript.close();
        }
        process.destroy();
    }
}
