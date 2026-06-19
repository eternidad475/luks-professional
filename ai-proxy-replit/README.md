# Caseflow Studio – AI simulation proxy (Replit)

A tiny server that keeps your image-API key **off the client** and turns one
request into a generated dental after-image.

```
POST /simulate   { image: dataURL, prompt, params, concept, targets }
              ->  { image: dataURL }
```

Default provider is **Google Gemini Flash Image** ("Nano Banana"): cheapest and
best at identity-preserving instructed edits. Set `PROVIDER=openai` to use
**OpenAI gpt-image-1** instead. Patient identity is additionally guaranteed in
the app, which composites only the **mouth region** of the AI result back onto
the original photo — so the rest of the face/photo is always the untouched
original. (That's also why this proxy needs no image-processing libraries.)

## Setup on Replit (≈5 minutes)

1. Create a new **Node.js** Repl and add these three files
   (`index.js`, `package.json`, `.env.example`).
2. **Tools → Secrets**, add:
   - `PROVIDER` = `gemini` (or `openai`)
   - `GEMINI_API_KEY` = your Google AI Studio key *(if using Gemini)*
   - `OPENAI_API_KEY` = your OpenAI key *(if using OpenAI)*
   - *(optional)* `GEMINI_MODEL`, `OPENAI_MODEL`, `ALLOW_ORIGIN`
3. Press **Run** to test, then **Deploy → Autoscale** (scales to zero, so you
   pay per request — ideal for low-volume consultation use).
4. Copy the deployment URL (e.g. `https://your-app.replit.app`).

## Connect it to the app

In Simulation Studio → result screen → **AI backend** field, paste the URL.
The app appends `/simulate` automatically and switches to AI generation.
(You can also run `caseflowSetAIEndpoint('https://your-app.replit.app')` in the
browser console.)

## Cost notes

- Use **Autoscale** (not a Reserved VM) so idle time costs nothing.
- Gemini Flash Image is a few yen per image; OpenAI gpt-image-1 is somewhat more
  and varies with the quality setting. Verify current pricing with each vendor.

## Privacy / consent

Patient photos are sent to a third-party API. Obtain patient consent and confirm
your clinic's data-handling policy (e.g. Japan's APPI) before enabling AI mode.
The output is a **reference image for explanation only — not a treatment
guarantee or diagnosis.**

## Quick local test

```bash
npm install
PROVIDER=gemini GEMINI_API_KEY=... npm start
# then POST a small dataURL to http://localhost:3000/simulate
```
