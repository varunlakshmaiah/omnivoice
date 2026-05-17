"""
Alexa LLM Skill — OmniVoice
A custom Alexa skill that routes user speech to an LLM via OpenRouter.

Architecture:
    User → Alexa → AWS Lambda → OpenRouter (DeepSeek) → Response → Alexa → User

Features:
    - Free-form text capture via AMAZON.SearchQuery + FallbackIntent
    - Progressive responses ("Working on it, Sir...") to handle LLM latency
    - Session-based conversation history with sliding window
    - Dynamic temperature based on query type
    - Time-aware system prompt (IST)
"""

import os
import logging
import json
import requests
from datetime import datetime, timezone, timedelta

# --- Simple .env Loader ---
def load_env(file_path=".env"):
    """Load environment variables from a file if it exists."""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

# Try to load from .env file in the same directory
load_env(os.path.join(os.path.dirname(__file__), ".env"))

from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.api_client import DefaultApiClient
from ask_sdk_core.dispatch_components import (
    AbstractRequestHandler,
    AbstractExceptionHandler,
    AbstractRequestInterceptor,
)
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_request_type, is_intent_name, get_slot_value
from ask_sdk_model import Response
from ask_sdk_model.services.directive import (
    SendDirectiveRequest,
    Header,
    SpeakDirective,
)

# ─── Configuration ───────────────────────────────────────────────────────────

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get(
    "LLM_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"
)
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek/deepseek-v4-flash")
LLM_MAX_HISTORY_TURNS = int(os.environ.get("LLM_MAX_HISTORY_TURNS", "10"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "200"))
LLM_UTC_OFFSET = float(os.environ.get("LLM_UTC_OFFSET", "5.5"))

# ─── Logging ─────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ─── System Prompt ───────────────────────────────────────────────────────────


def build_system_prompt():
    """Build the OmniVoice system prompt with current date/time."""
    utc_offset = timedelta(hours=LLM_UTC_OFFSET)
    now = datetime.now(timezone(utc_offset))
    current_datetime = now.strftime("%A, %B %d %Y, %I:%M %p")

    return (
        f"You are OmniVoice, an AI assistant with a dry wit and subtle sarcasm — "
        f"think Alfred meets Tony Stark. "
        f"You are highly intelligent, slightly sardonic, but always ultimately helpful. "
        f"Always address the user as Sir. "
        f"Never use filler phrases like Certainly, Of course, or Great question. "
        f"Get straight to the point. "
        f"If you do not know something, say so in one short sentence and stop. "
        f"Do not guess or fabricate. "
        f"Follow these strict response length rules: "
        f"For simple facts, answer in exactly one sentence. "
        f"For explanations or how something works, use three sentences maximum. "
        f"For opinions or recommendations, use two sentences maximum. "
        f"If the user explicitly asks for a deep dive, breakdown, or to expand, "
        f"ignore the sentence limits. Deliver a comprehensive, detailed analysis "
        f"using continuous, conversational paragraphs. "
        f"Never use lists, bullet points, numbered points, or markdown of any kind. "
        f"Never structure a response as multiple separate points — "
        f"always flow as natural speech. "
        f"Spell out all numbers, units and symbols in full since your response "
        f"will be spoken aloud by Alexa. "
        f"The current date and time is {current_datetime}."
    )


# ─── LLM Service ────────────────────────────────────────────────────────────


def detect_temperature(question):
    """Dynamically tune temperature based on question type."""
    question_lower = question.lower()

    creative_keywords = [
        "story", "poem", "joke", "imagine", "creative",
        "write", "invent", "pretend", "compose", "song",
    ]
    factual_keywords = [
        "what", "who", "when", "where", "how many", "how much",
        "define", "explain", "calculate", "convert",
    ]

    if any(word in question_lower for word in creative_keywords):
        return 0.9
    elif any(word in question_lower for word in factual_keywords):
        return 0.2
    else:
        return 0.5


def generate_response(chat_history, question):
    """Send the conversation to the LLM and return the response."""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    # Build messages array
    messages = [{"role": "system", "content": build_system_prompt()}]

    # Append conversation history (sliding window — last N turns)
    for user_msg, assistant_msg in chat_history[-LLM_MAX_HISTORY_TURNS:]:
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": assistant_msg})

    messages.append({"role": "user", "content": question})

    temperature = detect_temperature(question)

    data = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": temperature,
    }

    try:
        response = requests.post(
            LLM_BASE_URL,
            headers=headers,
            data=json.dumps(data),
            timeout=7,  # Leave headroom within Alexa's 8-second limit
        )
        response_data = response.json()

        if response.ok:
            content = response_data["choices"][0]["message"]["content"]
            return content.strip()
        else:
            error_msg = response_data.get("error", {}).get("message", "Unknown error")
            logger.error(f"API error: {error_msg}")
            return "Apologies Sir, my neural networks are experiencing interference. Please try again."

    except requests.exceptions.Timeout:
        logger.error("LLM API timeout")
        return "I'm afraid that query took longer than expected, Sir. Could you try a simpler question?"

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}", exc_info=True)
        return "Something went wrong on my end, Sir. Please try again."


# ─── Progressive Response ────────────────────────────────────────────────────


def send_progressive_response(handler_input, speech=None):
    """
    Send a progressive response to keep the user engaged while the LLM processes.
    Requires CustomSkillBuilder with DefaultApiClient.
    """
    thinking_phrases = [
        "Working on it, Sir.",
        "One moment, Sir.",
        "Let me think about that, Sir.",
        "Processing, Sir.",
        "Analyzing your query, Sir.",
    ]

    if speech is None:
        import random
        speech = random.choice(thinking_phrases)

    try:
        request_id = handler_input.request_envelope.request.request_id
        directive_header = Header(request_id=request_id)
        speech_directive = SpeakDirective(speech=speech)
        directive_request = SendDirectiveRequest(
            header=directive_header, directive=speech_directive
        )

        directive_client = (
            handler_input.service_client_factory.get_directive_service()
        )
        directive_client.enqueue(directive_request)
        logger.info(f"Progressive response sent: {speech}")

    except Exception as e:
        # Progressive responses are best-effort — don't fail the skill
        logger.warning(f"Progressive response failed (non-fatal): {str(e)}")


# ─── Request Handlers ────────────────────────────────────────────────────────


class LaunchRequestHandler(AbstractRequestHandler):
    """Handle skill launch — 'Alexa, open Omni Voice'."""

    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        session_attr = handler_input.attributes_manager.session_attributes
        session_attr["chat_history"] = []

        speech = (
            '<audio src="soundbank://soundlibrary/computers/beeps_tones/'
            'beeps_tones_13"/>'
            "OmniVoice activated. How may I assist you, Sir?"
        )

        return (
            handler_input.response_builder
            .speak(speech)
            .ask("Go ahead, Sir.")
            .response
        )


class LlmQueryIntentHandler(AbstractRequestHandler):
    """Handle ChatIntent — captures user query via AMAZON.SearchQuery slot."""

    def can_handle(self, handler_input):
        return is_intent_name("LLMQueryIntent")(handler_input)

    def handle(self, handler_input):
        query = get_slot_value(handler_input=handler_input, slot_name="query")

        if not query or not query.strip():
            return (
                handler_input.response_builder
                .speak("I didn't catch that, Sir. Could you repeat your question?")
                .ask("Go ahead, Sir.")
                .response
            )

        logger.info(f"[LLMQueryIntent] User query: {query}")

        # Send progressive response while LLM processes
        send_progressive_response(handler_input)

        # Get conversation history
        session_attr = handler_input.attributes_manager.session_attributes
        if "chat_history" not in session_attr:
            session_attr["chat_history"] = []

        # Call the LLM
        response = generate_response(session_attr["chat_history"], query)

        # Save to conversation history
        session_attr["chat_history"].append([query, response])
        
        # Trim history to stay under Alexa's 24KB response limit
        session_attr["chat_history"] = session_attr["chat_history"][-LLM_MAX_HISTORY_TURNS:]
        
        # Explicitly save attributes back to the manager
        handler_input.attributes_manager.session_attributes = session_attr

        logger.info(f"[LLMQueryIntent] Response: {response[:100]}...")

        return (
            handler_input.response_builder
            .speak(response)
            .ask("Anything else, Sir?")
            .response
        )


class FallbackIntentHandler(AbstractRequestHandler):
    """
    Handle AMAZON.FallbackIntent — catches unmatched utterances and routes to LLM.
    This ensures even queries that miss the SearchQuery slot still get answered.
    """

    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # Try to extract what the user actually said
        request = handler_input.request_envelope.request

        # Attempt to get raw input from various possible locations
        user_input = None

        # Check if there are any slot values (sometimes FallbackIntent carries them)
        if hasattr(request, "intent") and request.intent and request.intent.slots:
            for slot_name, slot in request.intent.slots.items():
                if slot.value:
                    user_input = slot.value
                    break

        if user_input and user_input.strip():
            logger.info(f"[FallbackIntent] Captured utterance: {user_input}")

            send_progressive_response(handler_input)

            session_attr = handler_input.attributes_manager.session_attributes
            if "chat_history" not in session_attr:
                session_attr["chat_history"] = []

            response = generate_response(session_attr["chat_history"], user_input)
            session_attr["chat_history"].append([user_input, response])
            
            # Trim history
            session_attr["chat_history"] = session_attr["chat_history"][-LLM_MAX_HISTORY_TURNS:]
            
            # Explicitly save attributes
            handler_input.attributes_manager.session_attributes = session_attr

            return (
                handler_input.response_builder
                .speak(response)
                .ask("Anything else, Sir?")
                .response
            )

        # If we couldn't extract input, provide guidance
        speech = (
            "I'm sorry Sir, I didn't catch that. "
            "Try starting your question with words like 'What is', 'How does', or simply 'And...' "
            "to help me process it."
        )
        return (
            handler_input.response_builder
            .speak(speech)
            .ask("How can I help, Sir?")
            .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    """Handle AMAZON.HelpIntent."""

    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speech = (
            "I'm OmniVoice, your AI assistant. You can ask me any question — "
            "from explaining quantum physics to writing a poem. "
            "Just speak naturally and I'll do my best to assist you, Sir."
        )

        return (
            handler_input.response_builder
            .speak(speech)
            .ask("What would you like to know, Sir?")
            .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Handle AMAZON.CancelIntent and AMAZON.StopIntent."""

    def can_handle(self, handler_input):
        return (
            is_intent_name("AMAZON.CancelIntent")(handler_input)
            or is_intent_name("AMAZON.StopIntent")(handler_input)
            or is_intent_name("AMAZON.NavigateHomeIntent")(handler_input)
        )

    def handle(self, handler_input):
        import random

        goodbyes = [
            "Goodbye, Sir. I'll be here when you need me.",
            "Until next time, Sir.",
            "Signing off, Sir. Do try not to break anything while I'm away.",
            "Very well, Sir. OmniVoice out.",
        ]

        return (
            handler_input.response_builder
            .speak(random.choice(goodbyes))
            .set_should_end_session(True)
            .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handle SessionEndedRequest — cleanup and logging."""

    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        reason = handler_input.request_envelope.request.reason
        logger.info(f"[SessionEnded] Reason: {reason}")

        if hasattr(handler_input.request_envelope.request, "error"):
            error = handler_input.request_envelope.request.error
            if error:
                logger.error(f"[SessionEnded] Error: {error}")

        return handler_input.response_builder.response


# ─── Exception Handler ───────────────────────────────────────────────────────


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Global exception handler — catches everything."""

    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(f"Unhandled exception: {exception}", exc_info=True)

        return (
            handler_input.response_builder
            .speak(
                "My apologies, Sir. Something went wrong internally. "
                "Please try again."
            )
            .ask("Please try again, Sir.")
            .response
        )


# ─── Request Interceptor (Logging) ───────────────────────────────────────────


class LoggingRequestInterceptor(AbstractRequestInterceptor):
    """Log incoming requests for debugging."""

    def process(self, handler_input):
        request = handler_input.request_envelope.request
        logger.info(f"[Request] Type: {request.object_type}")
        if hasattr(request, "intent") and request.intent:
            logger.info(f"[Request] Intent: {request.intent.name}")


# ─── Skill Builder ───────────────────────────────────────────────────────────

# CustomSkillBuilder with DefaultApiClient is REQUIRED for progressive responses
sb = CustomSkillBuilder(api_client=DefaultApiClient())

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(LlmQueryIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())

sb.add_exception_handler(CatchAllExceptionHandler())
sb.add_global_request_interceptor(LoggingRequestInterceptor())

lambda_handler = sb.lambda_handler()
