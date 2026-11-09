# LinkedIn post

**How to post:** upload `demo/alaap-demo.mp4` as the post's video (native upload gets far more reach than a link),
paste the text below, and when you type "@Gnani" pick the Gnani.ai page from LinkedIn's list so it becomes a real tag.

---

Every missed call at a small shop is a customer who calls the shop next door. 📞

So for The Great Indian AI Internship Challenge by @Gnani.ai, I built **Alaap**, an AI front desk for India's salons,
clinics, kiranas and coaching centres.

Alaap answers calls, WhatsApp and web chat in Hindi, Punjabi, English and the mix in between, the way customers actually
speak. It checks real free slots, books appointments, takes orders with UPI links, and passes anything it can't handle to
the owner on WhatsApp.

In the video, a caller asks in Punjabi-Hindi for a haircut at "saade chhe baje". Riya, the shop's AI assistant, asks for
his number, reads the booking back, waits for a clear "haan ji", and gives him a booking number. That booking shows up
in the owner's dashboard right away.

🗣️ The voice is Gnani AI end to end:
• **Prisma** streaming speech-to-text hears the caller in real time, code-mixed speech included, and detects when they've
finished talking
• **Timbre** streaming text-to-speech speaks each reply sentence by sentence, in one of 13 voices
• Even the video's narration is Timbre

What I cared about most was trust. Alaap never invents a price, never books without a read-back and a "yes", and
database locks make double bookings impossible. There are 44 automated tests behind it, plus live conversation checks.

It's a working MVP today. Next: a real phone line, the WhatsApp Business API, and a pilot with 10 shops in Patiala.

If you run a small business, or know someone who loses customers to missed calls, I'd love your feedback. 🙏

🔗 Code + one-page pitch: https://github.com/AshmitCajla/alaap

#GnaniAI #GreatIndianAIInternshipChallenge #VoiceAI #AIForBharat #SmallBusiness #BuildInPublic #ConversationalAI
