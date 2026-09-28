import logging
import textwrap

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    room_io,
)
from livekit.plugins import ai_coustics, openai, silero

import cal_tools
from cal_tools import current_datetime_context

logger = logging.getLogger("agent")

# OPENAI_API_KEY and the CAL_* settings are read from .env.local through the environment
load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            # Voice model instructions (GPT-Live persona). These are locked once the
            # session starts, so today's date is filled in when the call begins.
            # The backend model's instructions live in `responses_options` below.
            instructions=textwrap.dedent(
                f"""\
                You are Riley, the front desk receptionist at Northside Dental, a dental practice. You answer the phone for the practice.

                {current_datetime_context()} Use this when the caller says things like "tomorrow" or "next Tuesday".

                You sound warm, calm and friendly, like an experienced receptionist who is happy to help. Speak at a relaxed pace.

                Keep every answer short and spoken: one or two sentences, one question at a time. Never use lists, headings or any kind of formatting.

                Answer greetings, small talk and simple questions about what the caller has told you yourself. Hand anything that needs practice information, such as appointments, availability, prices or opening hours, to the backend. Never make up open times.

                Before you wait on the backend, say a short natural line such as "one moment while I check the calendar", then keep talking naturally while you wait. Don't go silent.

                To book, you need the caller's full name, their email address and the time they want. When the caller gives their email, spell it back one letter at a time, for example "j, o, h, n, at, g, m, a, i, l, dot, c, o, m", and ask if that's right before you use it. Then read back the name, email and time together and get a clear yes before the booking is made.

                If the caller asks you to switch to another language or accent, switch right away and stay in it until they ask you to change back.
                """
            ),
            # Cal.com tools: the backend model calls these, the voice model doesn't see them
            tools=cal_tools.TOOLS,
        )

    async def on_enter(self) -> None:
        # GPT-Live treats this as a suggestion and can decline to speak
        handle = self.session.generate_reply(
            instructions=(
                "Greet the caller as Riley from Northside Dental and ask how you can help."
            )
        )
        await handle
        if handle.exception() is not None:
            logger.info("the model declined to greet the caller")

    # To add tools, use the @function_tool decorator.
    # Here's an example that adds a simple weather tool.
    # You also have to add `from livekit.agents import function_tool, RunContext` to the top of this file
    # @function_tool
    # async def lookup_weather(self, context: RunContext, location: str):
    #     """Use this tool to look up current weather information in the given location.
    #
    #     If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.
    #
    #     Args:
    #         location: The location to look up weather information for (e.g. city name)
    #     """
    #
    #     logger.info(f"Looking up weather for {location}")
    #
    #     return "sunny with a temperature of 70 degrees."


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # OpenAI GPT-Live speech-to-speech model, using OPENAI_API_KEY from the environment.
    # The model handles listening, speaking and turn-taking itself, so there is no
    # STT, TTS or turn detector. See https://docs.livekit.io/agents/models/realtime/plugins/gpt-live/
    session = AgentSession(
        llm=openai.realtime.GPTLiveModel(
            voice="marin",
            delegation="responses",
            # Backend Responses model that handles delegated work and calls the tools
            responses_options={
                "instructions": textwrap.dedent(
                    f"""\
                    You handle the work the voice model delegates for Northside Dental, a dental practice.

                    {current_datetime_context()} Turn words like "tomorrow" or "next Tuesday" into dates from this.

                    Always call check_availability before offering any times, and only offer times it returned.

                    Never call book_appointment until you have the caller's full name, their email address and the exact time, and the caller has confirmed all three. If anything is missing or unconfirmed, say what still needs to be asked.

                    If a booking fails, check availability again and offer another time.

                    For anything else, answer only from what the caller has said. Reply with a short plain result the voice model can say aloud, with no lists or formatting.
                    """
                ),
            },
        ),
        # GPT-Live drops the session's default VAD, and barge-in needs one
        # to stop playback when the caller talks over the agent
        vad=ctx.proc.userdata["vad"],
    )

    # Start the session, which connects to GPT-Live
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = anam.AvatarSession(
    #     persona_config=anam.PersonaConfig(
    #         name="...",
    #         avatarId="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/anam
    #     ),
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
