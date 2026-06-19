# Caseflow Studio – AI simulation proxy (Val Town, free)

The simplest way to host the proxy from a phone: paste one file, get an instant
public URL, no build/deploy step, no paid plan.

## Setup (≈3 minutes, works on iPhone Safari)

1. Open **https://www.val.town** and sign in (Google login is easiest).
2. Click **New** → **HTTP val**.
3. Delete the sample code and paste the entire contents of **`main.tsx`**.
4. Open the val's **settings → Environment Variables** and add:
   - `GEMINI_API_KEY` = your Google AI Studio key (`AIza...`)
5. The val deploys automatically. Copy its public URL — it looks like
   `https://<username>-<valname>.web.val.run`.

## Connect it to the app

Open the URL in a browser tab first to confirm it answers
`{"ok":true,"provider":"gemini",...}`.

Then in Simulation Studio → result screen → **AI backend** field, paste the URL
(the app appends `/simulate` automatically; the val ignores the path).

## Notes

- CORS is wide open so the browser app can call it from any origin.
- The URL is effectively a shared secret — anyone who has it can spend your
  Gemini quota. Keep it private; add a token check later if needed.
- Patient photos are sent to Google's Gemini API. Obtain patient consent. The
  output is a reference image for explanation only — not a treatment guarantee.
