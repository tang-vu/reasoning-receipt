# Founder pitch — 60-90 second script

The product-demo video is recorded autonomously by `scripts/record-demo.py`. **This pitch video is the one piece Harvey records himself** — face + voice, single take, hand-held phone is fine. Target 75 seconds.

## Beats (timing in seconds, total 75)

### 0–10 · Who + what

> "Hi, I'm Vu Minh Tang. I built **ReasoningReceipt** — an on-chain oracle for prediction markets where every price ships with a hashed, byte-verifiable reasoning trace."

(Speak slowly enough that "byte-verifiable" registers.)

### 10–25 · Why it had to be Arc

> "A one-cent oracle call is uneconomical on any classical L1 — gas alone exceeds the price of the answer. Arc inverts that: each receipt costs **less than the information it commits to**. Our measured per-receipt gas is about one-fifteenth of a cent. That margin is what lets us sell *reasoning* — not just *predictions* — and it's why this product shape was impossible until Arc."

### 25–45 · How — the 5-agent ensemble

> "Each market goes through a five-agent debate. **Bull** argues yes. **Bear** argues no. **Edge** surfaces tail risks both partisans miss. A **Supervisor** weighs their drafts with weighted-Bayesian synthesis and mandates a falsifiable claim — a dated, concrete observable that would invalidate the prediction. A **Critic** audits the result across six rigor dimensions: evidence relevance, falsifiability, scope, coherence, exploration integrity, methodology. Receipts that fail audit never reach the chain."

### 45–60 · The wedge — Merkle DAG

> "The structural innovation is that every node of the reasoning DAG — every counter-argument, every cited evidence URL, every sensitivity factor — gets its own SHA-256, and we commit a Merkle root over all of them on Arc. Anyone can prove a single piece of evidence was part of the on-chain commitment with a two-hundred-byte inclusion proof. You don't have to trust me. You don't have to download the trace. You verify the part you care about."

### 60–75 · Traction + close

> "Forty-five hundred-plus receipts on Arc today, across nineteen distinct consumer wallets — the agent eats its own cooking. Live at rrtrace.xyz. Source on GitHub. Thanks."

## Production notes

- Total: ~75 seconds at 145-160 wpm pace
- One-take handheld phone, well-lit, plain background
- Speak directly to camera, no notes visible
- Avoid the word "we" — solo project, say "I built"
- Avoid the word "AI" except once; the product is reasoning + verification, the AI is the tool
- Do NOT mention Claude, Anthropic, Gemini brand names, or any specific LLM — keep the narrative product-first

## Tech checks before recording

- Phone in landscape, 1080p, 30fps
- Mic ≤ 30cm from mouth
- Test playback for clipping
- Have rrtrace.xyz open on a second screen so you can glance + say "live at rrtrace.xyz" with confidence

## Upload + paste into submission

- Upload `pitch.mp4` to YouTube as **unlisted** (phone or browser, ~2 min) —
  title: `ReasoningReceipt — Founder Pitch (Agora hackathon)`.
- Paste the URL into `docs/SUBMISSION.md` → Links section.
- Confirm it plays in an incognito window before submitting.
