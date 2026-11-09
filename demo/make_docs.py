"""captions.srt (from captions.ass, without the edit badges) and SCRIPT.md with timestamps."""
import json, re
import assemble as A

ass = (A.HERE / "captions.ass").read_text().splitlines()
cues = []
for ln in ass:
    if ln.startswith("Dialogue:"):
        parts = ln.split(",", 9)
        if parts[3] == "Badge":
            continue
        cues.append((parts[1], parts[2], re.sub(r"\{[^}]*\}", "", parts[9])))
def srt_t(t):
    h, m, s = t.split(":"); sec = float(s)
    return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int(round((sec % 1) * 1000)):03d}"
cues.sort(key=lambda c: srt_t(c[0]))
(A.HERE / "captions.srt").write_text("\n".join(f"{i}\n{srt_t(a)} --> {srt_t(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)))

lengths = {}
for n in A.ORDER:
    m = A.META[n]; rec = m["end"] - m["start"]
    if n == "call":
        lengths[n] = sum(e - s for s, e in A.call_material()[1])
    else:
        if A.MAN["scenes"].get(n) and n in ("hook", "gnani", "tech", "close", "call_intro", "solution", "dashboard"):
            rec = min(rec, A.nar_starts(n)[1] + (1.3 if n == "close" else 0.5))
        lengths[n] = rec
start, g = {}, 0.0
for n in A.ORDER:
    start[n] = g; g += lengths[n] - A.XF
TITLE = {"hook": "Opening hook: the problem", "solution": "The solution (landing page)", "call_intro": "Setting up the live call",
         "call": "Live call: a real booking, end to end", "dashboard": "Owner dashboard: booking + WhatsApp queue",
         "gnani": "Gnani AI integration", "owner": "Owner command in plain language (Ask Alaap)",
         "setup": "New shop setup from a rate card (team console)", "tech": "Technical highlights", "close": "Closing"}
mmss = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"
out = ["# Alaap demo — narration script and call transcript", "",
       f"Final video: `alaap-demo.mp4`, {mmss(g + A.XF)}, 1920×1080. Narration voiced with Gnani Timbre (voice: Devansh).", ""]
d = json.loads((A.FR / "call_audio.json").read_text())
tr = [e for e in d["events"] if e["event"] == "transcript"]
for n in A.ORDER:
    out.append(f"## {mmss(start[n])} — {TITLE[n]}")
    out.append("")
    if n == "call":
        out.append("No narration. The call below is real: the caller's lines were synthesized (Gnani Timbre, voice Avinash)"
                   " and played into the browser's microphone; everything Riya heard, said and did came from the live app."
                   " Silences longer than 0.6 s were shortened in the edit and marked on screen; the uncut call is"
                   " `call-uncut.mp4`. The call was cut after Riya's \"anything else?\" for length.")
        out.append("")
        out.append("| Who | What the app transcribed / said | English |")
        out.append("|---|---|---|")
        for e, en in zip(tr, A.TRANSLATE):
            who = "Riya (Gnani Timbre)" if e["role"] == "alaap" else "Caller (heard by Gnani Prisma)"
            out.append(f"| {who} | {e['text']} | {en['en']} |")
    else:
        for line in A.MAN["scenes"].get(n, []):
            out.append(f"> {line['text']}")
            out.append("")
    out.append("")
(A.HERE / "SCRIPT.md").write_text("\n".join(out))
print(len(cues), "captions;", "SCRIPT.md written")
