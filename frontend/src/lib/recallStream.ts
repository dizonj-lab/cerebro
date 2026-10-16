import type { RecallEvent } from "@/lib/api";

/**
 * Read the streaming answer from Ask CEREBRO.
 *
 * Server-sent events over `fetch`, parsed here rather than with
 * `EventSource`, which cannot issue a POST and so cannot carry the question.
 *
 * The caller gets every event in order: the sources first — they are the
 * evidence, and they are known before the first word — then the words as the
 * local model produces them, then a final event with the whole answer, the
 * citations that resolved and what the run cost.
 */
export async function streamRecall(
  input: { question: string; topic?: string | null },
  onEvent: (event: RecallEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/recall/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    credentials: "include",
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(
      response.status === 401
        ? "Your session has expired. Sign in again."
        : "CEREBRO could not answer that.",
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Events are separated by a blank line. A partial event stays in the
    // buffer until the rest of it arrives, which is the whole reason this
    // is parsed rather than split naively.
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice("data: ".length)) as RecallEvent);
      } catch {
        // A malformed event is skipped rather than ending the stream.
      }
    }
  }
}
