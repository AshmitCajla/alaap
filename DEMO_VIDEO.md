# Making the Alaap demo video

Goal: a short video that shows a real call being answered and booked, so you can test whether shop owners want it
and whether investors want to talk. Make **one 90-second master**, then cut a **60-second vertical** version for
Reels, WhatsApp status and the Gnani contest.

Everything in the script below was tested end to end on 7 Nov 2026: a voice caller said these exact lines, Alaap
understood them (Gnani speech recognition), booked the slot, said the right booking number, and the booking and the
WhatsApp confirmation showed up on the owner's dashboard.

---

## 1. Rules that keep the video honest (investors check)

- **Label the demo shop.** Put "Demo shop · sample data" on screen whenever the dashboard is visible. The week of
  history is generated sample data, not customers. Never present those numbers as traction.
- **Show the call as it really happened.** Retakes are fine. Speeding up Alaap's pauses is not.
- **Say what's live and what isn't.** Today the call runs in the browser (the **Call** button on the shop page).
  Until Exotel is connected, don't show a phone dialling a number. Caption it "Live web call. Phone line via Exotel
  next."
- **Hide phone numbers.** The demo numbers (98765…) may belong to real people. Blur them in the edit, and use your
  own number when you speak one on the call.

---

## 2. One day before

1. **Use a paid Gemini key if you can.** On the free tier most replies take 3–5 s, but some took 9–14 s in testing.
   Paid is much steadier. Put the key in `backend/.env`; nothing else changes.
2. **Check Gnani credits.** Each take costs a few minutes of speech-to-text and text-to-speech.
3. **Install the tools (all free):**
   - **OBS Studio** records the screen with *both* your microphone and the browser's audio (Alaap's voice).
     QuickTime can't record the browser's sound.
   - **CapCut** (desktop) or **DaVinci Resolve** for editing.
4. **Book a real location (best):** a friendly salon in Patiala for 30 minutes of B-roll. You need the owner busy
   with a client while a phone rings on the counter, then the owner glancing at the booking on their phone. Get the
   owner's OK to film and a signed one-line consent.
5. **Rehearse the call once** with the exact lines in section 4.

## 3. Recording day setup (10 minutes)

```bash
./demo.sh
```

This wipes **only** the demo database and loads fresh demo data:
- 3 shops: salon, kirana, coaching;
- today's bookings and a week of sample history;
- 2 free numbers in the pool;
- a team login.

It then starts the API on :8000 and the dashboard on :3000. Your normal data (`alaap.db`) is never touched.

- **Logins:** owner `owner@glow.demo` / `demo1234`; team `team@alaap.dev` / `demo1234` at `/ops`.
- **Browser:** Chrome, light mode, zoom 110 %, bookmarks bar hidden, notifications off (macOS Focus mode),
  other tabs closed.
- **Window:** 1920×1080 for the master. For the vertical cut, use Chrome DevTools' phone view (iPhone 14 Pro) or
  record your real phone's screen.
- **Mic:** a wired earphone mic or USB mic, in a quiet room. Turn the fan off.
- **OBS:**
  - Add a "macOS Screen Capture" source for the Chrome window.
  - Add "Audio Input Capture" for your mic and "Application Audio Capture" for Chrome.
  - Do a 10-second test and check both voices are audible and neither is clipping.
- **After every take:** run `./demo.sh` again, or `cd backend && DATABASE_URL=sqlite:///data/demo.db
  ../.venv/bin/python -m alaap.admin demo-reset` while the servers keep running. This frees the 6:30 slot again.

## 4. The script (90 seconds)

| Time | On screen | You say (voice-over unless marked) |
|---|---|---|
| 0–6 s | Salon B-roll: owner cutting hair, phone ringing on the counter, nobody picks up | "Every missed call at a small shop is a customer who calls the shop next door." |
| 6–12 s | Landing page hero ("Har call ka jawab. Har customer ki booking.") | "Alaap answers your shop's calls and WhatsApp — in Hindi, Punjabi and English." |
| 12–50 s | Customer page `localhost:8000/c/glow-salon`, press **Call**, the call screen with the glowing orb | **The live call**, below. No voice-over; let it play. |
| 50–60 s | Switch to the owner dashboard → **Appointments**: Rohit, tomorrow 6:30 pm, booked via phone | "The booking is already in the owner's dashboard…" |
| 60–66 s | **Messages sent**: "Booking confirmed…" and the reminder 2 hours before | "…the customer gets a WhatsApp confirmation, and a reminder before the visit." |
| 66–78 s | Team console `/ops` → Add shop → paste a rate card → **Read it** → the review table fills in | "Setup takes five minutes: send us your rate card, and Alaap learns your prices and timings." |
| 78–84 s | Quick cut: someone types "bridal makeup kitne ka hai?" → Alaap offers a callback instead of inventing a price | "It never makes up a price, and it always says it's an AI." |
| 84–90 s | End card: "Pilot in Patiala — ₹999/month · WhatsApp JOIN to +91 …" and "Voice by Gnani AI" | "We're starting with 10 shops in Patiala. Want to be one of them?" |

**The live call: say exactly these lines.** Wait until Alaap fully stops talking each time; talking over it
makes it stop and listen, which looks like a glitch on camera.

1. Alaap greets you ("Sat Sri Akal ji! Glow Unisex Salon se … bol rahi hoon, call record ho rahi hai…").
2. You: **"Sat Sri Akal ji. Kal shaam saade chhe baje gents haircut ho jayega? Mera naam Rohit hai."**
3. Alaap asks for your mobile number. You: **"Mera number hai …"** (your own number, as words).
4. Alaap reads it back: "Toh kal shaam saade chhe baje, Gurpreet ke saath haircut, do sau rupaye. Pakka kar doon?"
   You: **"Haan ji, pakka kar do."**
5. Alaap: "Ji, ho gaya! Booking number … hai, WhatsApp par confirmation aa jayega." You: **"Bas ji, bahut
   dhanyavaad."**
6. Alaap says goodbye and hangs up by itself. That's a strong ending; keep it in.

**If something goes off script:** keep going if Alaap handled it sensibly (for example, it offers another time).
A real, unscripted moment is more convincing than a perfect one. Retake only if a reply took over 6 seconds or
the audio broke up. Then reset the demo data first.

**Optional 15-second extras (good for a second video):**
- *English caller:* "Hi, what time do you close on Saturday and how much is a beard trim?" → it answers in English.
- *Kirana order* on `/c/sharma-kirana`: tap **Place an order**, "2 packet atta aur 1 oil bhej do".
- *Owner command* in **Ask Alaap**: "Facial ka rate 900 kar do" → it updates the price itself.

## 5. Editing (about 2 hours)

1. Put the salon B-roll first. Hook in the first 3 seconds: a ringing phone nobody answers.
2. **Captions for everything spoken**, in English (the call is in Hinglish/Punjabi). CapCut's auto-captions are a
   starting point; fix the words by hand.
3. Add lower-thirds:
   - "Live AI call — not acted" during the call;
   - "Demo shop · sample data" on dashboard shots;
   - "Voice: Gnani Prisma (speech recognition) + Timbre (voice)" once (this matters for the contest).
4. Highlight clicks: zoom in 120 % on the booking row when it appears, and on the booking number in the transcript.
5. Background music: low (about −25 dB), and off during the call.
6. Blur every phone number.
7. **Export:**
   - Master: 1920×1080, 30 fps, H.264, about 12 Mbps.
   - Vertical: 1080×1920. Crop to the call screen and the phone dashboard, with captions in the middle third.
8. Watch it once on a phone with the sound off. If the story still makes sense, the captions are doing their job.

## 6. Using it to test demand (the real point)

Post it with **one clear ask** and count the responses. The video doesn't prove demand; responses do.

| Audience | Where | The ask | A good signal |
|---|---|---|---|
| Shop owners | Show it in person to 20 Patiala shops; WhatsApp business groups; Instagram Reel with a local hashtag | "Free 14-day pilot — WhatsApp JOIN" | 5+ of 20 owners start a pilot; 2+ agree to pay ₹999 after the trial |
| Investors / mentors | LinkedIn post, Gnani contest, college incubator, direct messages with the video link | "15 minutes to show you the pilot results?" | Replies asking for the pilot numbers or a call |
| Everyone | Landing page with the video at the top | Sign-up or JOIN | Count views → JOIN messages → pilots → paid |

Write the numbers down every week. Investors care about *"7 shops, 412 calls answered, 63 bookings, 4 paying"*
far more than about the video.

## 7. Before you hit publish

- [ ] Every number blurred; "Demo shop · sample data" visible on dashboard shots
- [ ] The call shown is a real take, with nothing sped up
- [ ] Gnani credited on screen
- [ ] The CTA number/link works (send "JOIN" yourself and check it arrives)
- [ ] Salon owner's consent to appear
- [ ] Watched once on a phone, sound off, start to finish
