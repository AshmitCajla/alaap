# Alaap demo — narration script and call transcript

Final video: `alaap-demo.mp4`, 2:50, 1920×1080. Narration voiced with Gnani Timbre (voice: Devansh).

## 0:00 — Opening hook: the problem

> Every day, small businesses across India miss customer calls.

> The owner is busy at the counter, the shop has closed for the night, or two phones ring at once.

> Each missed call can be a booking that goes to the shop next door.


## 0:13 — The solution (landing page)

> Alaap is an AI front desk for these shops.

> It answers phone calls, WhatsApp and web chat in Hindi, Punjabi and English, the way customers actually speak.

> It books appointments, takes orders, and passes anything it can't solve to the owner.


## 0:28 — Setting up the live call

> Here's a live call to a demo salon. The caller's voice is synthesized; everything else is the live app.


## 0:35 — Live call: a real booking, end to end

No narration. The call below is real: the caller's lines were synthesized (Gnani Timbre, voice Avinash) and played into the browser's microphone; everything Riya heard, said and did came from the live app. Silences longer than 0.6 s were shortened in the edit and marked on screen; the uncut call is `call-uncut.mp4`. The call was cut after Riya's "anything else?" for length.

| Who | What the app transcribed / said | English |
|---|---|---|
| Riya (Gnani Timbre) | Sat Sri Akal ji! Glow Unisex Salon se Riya bol rahi hoon, call record ho rahi hai. Bataiye, kya seva karoon? | Sat Sri Akal! This is Riya from Glow Unisex Salon. This call is recorded. How can I help? |
| Caller (heard by Gnani Prisma) | सत श्री अकाल जी, कल शाम साढ़े छह बजे gents haircut हो जाएगा, मेरा नाम रोहित है। | Sat Sri Akal. Can I get a gents haircut tomorrow at 6:30 pm? My name is Rohit. |
| Riya (Gnani Timbre) | नमस्ते रोहित जी! | Hello, Rohit ji! |
| Riya (Gnani Timbre) | कल शाम 6:30 बजे हेयरकट के लिए स्लॉट खाली है। | There's a free slot for a haircut tomorrow at 6:30 pm. |
| Riya (Gnani Timbre) | अपना 10-digit मोबाइल नंबर बता देंगे? | Could you tell me your 10-digit mobile number? |
| Riya (Gnani Timbre) | फिर मैं बुकिंग पक्की कर देती हूँ। | Then I'll confirm the booking. |
| Caller (heard by Gnani Prisma) | मेरा नंबर है नौ आठ एक दो तीन चार पाँच छः सात शून्य। | My number is 98123 45670. |
| Riya (Gnani Timbre) | Theek hai Rohit ji, toh kal shaam 6:30 baje, Gurpreet ke saath haircut, Rs 200. Pakka kar doon? | Okay Rohit ji: tomorrow 6:30 pm, haircut with Gurpreet, ₹200. Shall I confirm it? |
| Caller (heard by Gnani Prisma) | ਹਾਂਜੀ, ਪੱਕਾ ਕਰ ਦਿਓ। | Yes, please confirm it. |
| Riya (Gnani Timbre) | Ji, ho gaya! | Done! |
| Riya (Gnani Timbre) | Booking number 5161 hai, WhatsApp par confirmation aa jayega. | Your booking number is 5161. A WhatsApp confirmation is on its way. |
| Riya (Gnani Timbre) | Kuch aur madad kar sakti hoon Rohit ji? | Anything else I can help with, Rohit ji? |
| Caller (heard by Gnani Prisma) | बस जी, बहुत धन्यवाद। | That's all. Thank you very much. |
| Riya (Gnani Timbre) | Zaroor ji, bahut dhanaywad! | Of course, thank you so much! |
| Riya (Gnani Timbre) | Phir milenge, bye bye. | See you again. Bye bye. |

## 1:28 — Owner dashboard: booking + WhatsApp queue

> The booking lands in the owner's dashboard right away, with the customer's name, number and reference.

> A WhatsApp confirmation and a reminder are queued automatically. WhatsApp isn't connected in this demo, so they wait in the outbox.


## 1:42 — Gnani AI integration

> The voice runs on Gnani AI.

> Gnani's Prisma speech recognition streams the caller's audio in real time, understands Hindi, Punjabi, English and code-mixed speech, and detects when the caller has finished speaking.

> Gnani's Timbre text-to-speech gives the assistant its voice, streamed sentence by sentence, so it starts talking while the rest of the reply is still being prepared.


## 2:06 — Owner command in plain language (Ask Alaap)

> Owners run it in plain language. Asking it to make the facial nine hundred rupees updates the price list.


## 2:13 — New shop setup from a rate card (team console)

> New shops are set up in minutes: paste a rate card or a photo, and the language model reads the services, prices and hours for review.


## 2:22 — Technical highlights

> Under the hood: FastAPI and Next.js, with Gnani for speech and Google Gemini for reasoning.

> Nothing is booked until the customer hears a read-back and says yes. Row locks prevent double bookings, and forty-four automated tests guard the behaviour.


## 2:38 — Closing

> Alaap gives every small shop a front desk that never misses a call, speaks its customers' language, and never invents a price.

> Alaap. Har call ka jawab.

