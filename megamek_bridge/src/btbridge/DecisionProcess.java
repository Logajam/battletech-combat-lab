/*
 * MegaMek bridge (INTEGRATION__MEGAMEK_BRIDGE.md), stage B2. GPL v3: built on MegaMek (see megamek_bridge/README.md).
 */
package btbridge;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

/**
 * Our engine's decision process, {@code btsim decide}, as a child process: one JSON line in, one JSON line out
 * (engine/core/src/bridge.rs; spec Section 3b). It starts once per bot player and lives for the whole game, so our
 * bots' memories carry from turn to turn. Any failure (the process will not start, dies, or answers with an error)
 * is reported to the caller, which then lets Princess decide: a FALLBACK, counted in the records.
 */
public final class DecisionProcess implements AutoCloseable {
    private final Process process;
    private final BufferedWriter toEngine;
    private final BufferedReader fromEngine;

    /**
     * @param btsim the path to our engine's {@code btsim} binary
     */
    public DecisionProcess(String btsim) throws IOException {
        process = new ProcessBuilder(btsim, "decide").redirectError(ProcessBuilder.Redirect.INHERIT).start();
        toEngine = new BufferedWriter(new OutputStreamWriter(process.getOutputStream(), StandardCharsets.UTF_8));
        fromEngine = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
    }

    /**
     * Sends one JSON line and returns the engine's one-line reply.
     *
     * @throws IOException if the process is gone or closed its output
     */
    public synchronized String ask(String jsonLine) throws IOException {
        toEngine.write(jsonLine);
        toEngine.write('\n');
        toEngine.flush();
        String reply = fromEngine.readLine();
        if (reply == null) {
            throw new IOException("btsim decide closed its output");
        }
        return reply;
    }

    @Override
    public void close() {
        try {
            toEngine.close();
        } catch (IOException ignored) {
            // the process may already be gone
        }
        process.destroy();
    }
}
