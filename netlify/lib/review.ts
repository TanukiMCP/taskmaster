// The user's review page: lists work that is ready for review and records the user's verdict.
// It sits behind its own token (TASKMASTER_REVIEW_TOKEN), which agents are never given.

import { EngineError, currentEntry, entryLabel, recordVerdict, type Session } from "./engine.ts";
import type { Library } from "./library.ts";
import type { Store } from "./store.ts";

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

function sessionBlock(session: Session): string {
  const entry = currentEntry(session)!;
  const last = entry.verifications.at(-1);
  const captures = entry.captures
    .map(
      (c) =>
        `<li>${esc(c.kind)} <b>${esc(c.label)}</b> — <a href="${esc(c.url)}">${esc(c.url)}</a>${c.selector ? ` <code>${esc(c.selector)}</code>` : ""}` +
        ` · taken by ${esc(c.taken_by)}<br><small>${c.widths
          .map((w) => `${w.width}px: page ${w.page_height}px${w.overflow ? ", scrolls sideways" : ""} — ${esc(w.page?.file)}`)
          .join("<br>")}</small></li>`,
    )
    .join("");
  const steps = Array.from({ length: 10 }, (_, k) => `<option value="${k}">${k}</option>`).join("");
  return `<section>
  <h2>${esc(entryLabel(entry))}: ${esc(entry.goal)}</h2>
  <p class="meta">Session ${esc(session.id)} · ${esc(session.request)}</p>
  ${last?.findings ? `<p><b>What the agent reports it measured and checked:</b> ${esc(last.findings)}</p>` : ""}
  <ul>${captures}</ul>
  <form method="post">
    <input type="hidden" name="session_id" value="${esc(session.id)}">
    <label><input type="radio" name="verdict" value="done" required> Done</label>
    <label><input type="radio" name="verdict" value="return"> Send back to procedure step <select name="step">${steps}</select></label>
    <label class="block">Reason (needed to send it back)<textarea name="reason" rows="3"></textarea></label>
    <button>Record verdict</button>
  </form>
</section>`;
}

function page(body: string, message = ""): Response {
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Taskmaster review</title><style>
:root{color-scheme:light dark}body{margin:0;padding:32px 16px;font:15px/1.5 system-ui,sans-serif;background:Canvas;color:CanvasText}
main{max-width:52rem;margin:0 auto}section{border-top:1px solid GrayText;padding:16px 0}.meta{color:GrayText}
label{margin-right:16px}.block{display:block;margin:12px 0}textarea{display:block;width:100%;font:inherit}.msg{padding:8px 12px;border:1px solid GrayText}
</style></head><body><main><h1>Work ready for your review</h1>${message ? `<p class="msg">${esc(message)}</p>` : ""}${body}</main></body></html>`;
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}

async function waiting(store: Store): Promise<Session[]> {
  return (await store.recent(200)).filter((s) => currentEntry(s)?.awaiting_user);
}

export async function handleReview(request: Request, store: Store, lib: Library): Promise<Response> {
  let message = "";
  if (request.method === "POST") {
    const form = await request.formData();
    const session = await store.load(String(form.get("session_id") ?? ""));
    if (!session) message = "That session no longer exists.";
    else {
      try {
        const verdict = String(form.get("verdict") ?? "");
        const outcome = recordVerdict(lib, session, verdict, verdict === "return" ? Number(form.get("step")) : null, String(form.get("reason") ?? ""));
        await store.save(session);
        message = outcome === "done" ? `Marked ${session.id} done.` : `Sent ${session.id} back to step ${form.get("step")}. The agent sees your reason at its next step.`;
      } catch (error) {
        if (!(error instanceof EngineError)) throw error;
        message = error.message;
      }
    }
  }
  const sessions = await waiting(store);
  return page(sessions.length ? sessions.map(sessionBlock).join("") : "<p>Nothing is waiting for you.</p>", message);
}
