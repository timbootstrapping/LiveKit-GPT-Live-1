# GPT-Live-1 Voice Agent on LiveKit

A voice agent that runs on OpenAI's **GPT-Live-1** speech-to-speech model through LiveKit, and books
real appointments into **Cal.com**. The whole thing was written by Claude Code from the LiveKit
docs, and you can run it without writing any code.

📺 **Full walkthrough on YouTube:** [VIDEO LINK]
📄 **Step-by-step guide with every command:** [GUIDE LINK]

The demo is Riley, the front desk receptionist at Northside Dental, a made-up dental practice. Riley
checks the calendar, offers open times, spells your email back to you letter by letter, and books
the appointment. You can also ask Riley to switch language or accent mid-call.

---

## How it works

A classic voice agent is three models in a row: a transcriber turns speech into text, an LLM reads
that text, and a TTS voice reads the answer out. The LLM never actually hears the caller. It reads a
note about them.

GPT-Live-1 hears the audio itself and talks back, voice in, voice out. And it splits the work into
two models that run in parallel:

| | What it does | Where its instructions live |
|---|---|---|
| **Voice model** (GPT-Live-1) | Listens, talks, handles interruptions. Says "one moment while I check the calendar" and keeps the conversation going. | `instructions=` on the `Assistant` class in `src/agent.py` |
| **Backend model** | Thinks and calls the tools. The voice model hands work off to it. | `responses_options["instructions"]` in `src/agent.py` |

The voice model never sees the tools. Only the backend does. That is why there are two prompts, and
both are locked once a call starts.

## What's in here

```
src/agent.py       the agent: GPT-Live-1 setup, both prompts, the greeting
src/cal_tools.py   the two Cal.com tools: check_availability and book_appointment
.env.example       every key the agent needs, empty
AGENTS.md          instructions that make your coding agent follow LiveKit's docs
```

---

## What you need

**Accounts**
- **OpenAI API key with GPT-Live access.** From [platform.openai.com](https://platform.openai.com/).
  You need billing set up. The free tier does not get GPT-Live.
- **LiveKit Cloud** (free tier is fine) at [cloud.livekit.io](https://cloud.livekit.io/). You still
  need it with your own OpenAI key: LiveKit carries the audio and gives you the browser playground.
- **Cal.com** at [cal.com](https://cal.com/), with one event type (for example a 30 minute
  appointment) and your availability set.
  - API key: Settings, Developer, API Keys.
  - Event type ID: the number in the event type's URL in your dashboard.

**Tools**
- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/), version 2.18.8 or later:
  - **Windows:** `winget install LiveKit.LiveKitCLI`
  - **macOS:** `brew install livekit-cli`
  - **Linux:** `curl -sSL https://get.livekit.io/cli | bash`

## Run it in five steps

**1. Clone the repo and install**

```console
git clone https://github.com/timbootstrapping/LiveKit-GPT-Live-1.git
cd LiveKit-GPT-Live-1
uv sync
```

**2. Connect LiveKit Cloud.** This logs you in and writes your LiveKit URL and keys into `.env.local`.

```console
lk cloud auth
lk app env --write --destination .env.local
```

**3. Add your other keys.** Open `.env.local` and add these lines under the LiveKit ones:

```
OPENAI_API_KEY=your-openai-key
CAL_API_KEY=your-cal-api-key
CAL_EVENT_TYPE_ID=your-event-type-id
CAL_TIMEZONE=Europe/Berlin
```

Set `CAL_TIMEZONE` to the timezone the business works in (for example `America/New_York` or
`Australia/Brisbane`). `.env.local` is gitignored, so your keys never get committed.

**4. Start the agent**

```console
lk agent dev
```

**5. Talk to it.** The terminal prints a link to the LiveKit Agent Console. Open it in your browser,
click **Start a session**, allow your microphone, and ask Riley for an appointment. The booking
shows up in your Cal.com dashboard.

Stop the agent with `Ctrl+C`.

---

## Make it yours

Everything that makes this a dental practice lives in `src/agent.py`:

- **Voice prompt** (`instructions=` in the `Assistant` class): the name, the business, how it
  sounds, when to say "one moment", the email spelling rule.
- **Backend prompt** (`responses_options["instructions"]`): when to check availability and the rules
  before it is allowed to book.
- **Greeting** (`on_enter`): the first thing it says.
- **Voice** (`voice="marin"`): swap for another GPT-Live voice from the
  [LiveKit GPT-Live docs](https://docs.livekit.io/agents/models/realtime/plugins/gpt-live/).

You don't have to edit any of it by hand. Open the folder in Claude Code (or Cursor, or Codex) and
describe the business you want. The included `AGENTS.md` tells the AI to check the LiveKit docs
instead of guessing. For example:

```
Change this agent from Northside Dental to [your business]. Update the voice prompt, the backend prompt and the greeting. Keep the booking rules and the email spell-back. Read the GPT-Live page in the LiveKit docs before changing anything.
```

## If something breaks

- **Access or model error when the call starts:** your OpenAI key is not enabled for GPT-Live yet,
  or your account is on the free tier. That is an account issue, not a code issue.
- **"The calendar isn't available right now":** `CAL_API_KEY` or `CAL_EVENT_TYPE_ID` is missing, or
  the event type ID is not a plain number.
- **It never offers any times:** check that your Cal.com event type has availability on the days you
  asked about, and that `CAL_TIMEZONE` is right.
- **Anything else:** paste the error into your coding agent and tell it to read the GPT-Live page in
  the LiveKit docs (and the Cal.com API reference if it's about booking) before changing anything.

## Limits worth knowing

- **Audio only.** No images or video.
- **A small set of voices** compared to a normal TTS provider, and no separate TTS on top, so no
  voice cloning.
- **Locked once the call starts:** the voice, both prompts and the delegation settings.
- **Cost:** OpenAI bills per minute for the voice model plus tokens for the backend model. Check
  [OpenAI's pricing page](https://openai.com/api/pricing/) for current numbers.
- **This is a demo, not a production system.** It runs in the browser. Putting it on a real phone
  line, testing it against messy real callers, monitoring it, and handling consent and AI disclosure
  are all separate work.

---

## Credits

Built on LiveKit's [agent-starter-python](https://github.com/livekit-examples/agent-starter-python)
template and [LiveKit Agents](https://github.com/livekit/agents). Built by Tim Kramny,
[ximus.io](https://ximus.io).

MIT licensed. See [LICENSE](LICENSE).
