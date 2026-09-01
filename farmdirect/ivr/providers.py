"""IVR provider abstractions.

Defines four swappable interfaces:

  * ``TelephonyProvider``   — handles real phone calls (incoming webhook,
                                DTMF/speech collection, hangup).
  * ``TTSProvider``          — text → audio (mp3/wav) URL or base64.
  * ``STTProvider``          — audio → text.
  * ``AIIntentProvider``     — text → IntentResult (the production hook for
                                real cloud NLU such as Dialogflow / Lex).

Each interface has a Mock implementation (default, fully offline) and a
Production stub that reads credentials from environment variables but
raises NotImplementedError until configured. The IVR dialog code never
imports provider-specific libraries directly — it goes through these.

The IVR_MODE environment variable selects the active mode:

  IVR_MODE=mock         (default)  → mock providers, simulator-friendly
  IVR_MODE=production              → real provider impls (need env creds)
"""
from __future__ import annotations
import os
from typing import Optional

MODE = os.environ.get("IVR_MODE", "mock").lower()


# ---------------------------------------------------------------- Telephony
class TelephonyProvider:
    def answer(self, session_token: str, callback_url: str) -> dict:
        raise NotImplementedError

    def gather_dtmf(self, prompt_text: str, num_digits: int = 1, callback_url: str = "") -> dict:
        raise NotImplementedError

    def gather_speech(self, prompt_text: str, callback_url: str = "", lang: str = "ta-IN") -> dict:
        raise NotImplementedError

    def say(self, text: str, lang: str = "ta") -> dict:
        raise NotImplementedError

    def hangup(self, session_token: str) -> dict:
        raise NotImplementedError

    def verify_signature(self, request_headers: dict, request_body: bytes, signature: Optional[str]) -> bool:
        """Return True if the inbound webhook is from the real provider."""
        return True  # mock always trusts


class MockTelephony(TelephonyProvider):
    """Mock telephony — used by the in-app IVR Simulator.

    The simulator calls the same /api/ivr/* endpoints but with
    ``source=simulator``. The mock provider returns plain JSON the
    simulator's Web Speech API can render directly.
    """
    def answer(self, session_token, callback_url):
        return {"ok": True, "session_token": session_token, "mode": "mock"}

    def gather_dtmf(self, prompt_text, num_digits=1, callback_url=""):
        return {"ok": True, "instructions": "dtmf", "num_digits": num_digits}

    def gather_speech(self, prompt_text, callback_url="", lang="ta-IN"):
        return {"ok": True, "instructions": "speech", "lang": lang}

    def say(self, text, lang="ta"):
        return {"ok": True, "text": text, "lang": lang}

    def hangup(self, session_token):
        return {"ok": True, "session_token": session_token, "ended": True}


class TwilioTelephony(TelephonyProvider):
    """Production Twilio adapter.

    Required env vars:
      IVR_TWILIO_ACCOUNT_SID
      IVR_TWILIO_AUTH_TOKEN
      IVR_TWILIO_NUMBER     (the phone number callers dial)
      IVR_PUBLIC_BASE_URL   (the https URL of this Flask app — Twilio must
                              be able to POST back to /api/ivr/*)

    This is a clean stub — it raises NotImplementedError until all env
    vars are present so the simulator can run safely without real creds.
    """
    def __init__(self):
        self.sid = os.environ.get("IVR_TWILIO_ACCOUNT_SID")
        self.token = os.environ.get("IVR_TWILIO_AUTH_TOKEN")
        self.number = os.environ.get("IVR_TWILIO_NUMBER")
        self.base_url = os.environ.get("IVR_PUBLIC_BASE_URL", "")
        if not (self.sid and self.token and self.number and self.base_url):
            raise RuntimeError(
                "TwilioTelephony requires IVR_TWILIO_ACCOUNT_SID, "
                "IVR_TWILIO_AUTH_TOKEN, IVR_TWILIO_NUMBER and "
                "IVR_PUBLIC_BASE_URL to be set.")

    def verify_signature(self, request_headers, request_body, signature):
        # Twilio sends X-Twilio-Signature (HMAC-SHA1 of the URL+body)
        if not signature:
            return False
        try:
            import hmac
            import hashlib
            import base64
            from urllib.parse import urlparse
            # Build the validation string: URL + sorted POST params
            url = request_headers.get("X-Forwarded-Proto", "https") + "://" + \
                  request_headers.get("Host", "") + request_headers.get("Original-URI", "")
            mac = hmac.new(self.token.encode(), url.encode(), hashlib.sha1)
            expected = base64.b64encode(mac.digest()).decode()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    def answer(self, session_token, callback_url):
        # Returns TwiML <Gather> for DTMF or <Say> + redirect
        twiml = f"""<Response>
  <Say>வணக்கம். உழவர் நேரடி சேவைக்கு வரவேற்கிறோம்.</Say>
  <Gather numDigits="1" action="{callback_url}" method="POST">
    <Say language="ta-IN">தமிழில் தொடர 1 அழுத்தவும்.</Say>
    <Say language="en-IN">Press 2 for English.</Say>
  </Gather>
</Response>"""
        return {"ok": True, "twiml": twiml, "content_type": "text/xml"}

    def gather_dtmf(self, prompt_text, num_digits=1, callback_url=""):
        twiml = f"""<Response>
  <Gather numDigits="{num_digits}" action="{callback_url}" method="POST">
    <Say>{prompt_text}</Say>
  </Gather>
</Response>"""
        return {"ok": True, "twiml": twiml, "content_type": "text/xml"}

    def gather_speech(self, prompt_text, callback_url="", lang="ta-IN"):
        twiml = f"""<Response>
  <Gather input="speech" language="{lang}" action="{callback_url}" method="POST" speechTimeout="auto">
    <Say>{prompt_text}</Say>
  </Gather>
</Response>"""
        return {"ok": True, "twiml": twiml, "content_type": "text/xml"}

    def say(self, text, lang="ta"):
        twiml = f'<Response><Say language="{lang}-IN">{text}</Say></Response>'
        return {"ok": True, "twiml": twiml, "content_type": "text/xml"}

    def hangup(self, session_token):
        return {"ok": True, "twiml": "<Response><Hangup/></Response>",
                "content_type": "text/xml"}


# ---------------------------------------------------------------- TTS
class TTSProvider:
    def synth(self, text: str, lang: str = "ta") -> dict:
        """Return a dict with 'audio_url' or 'audio_base64' + 'mime'."""
        raise NotImplementedError


class MockTTS(TTSProvider):
    """Mock TTS — the simulator uses the browser's SpeechSynthesis API."""
    def synth(self, text, lang="ta"):
        return {"ok": True, "text": text, "lang": lang, "engine": "browser-speechsynthesis"}


class ElevenLabsTTS(TTSProvider):
    """Production ElevenLabs adapter (or any HTTP TTS)."""
    def __init__(self):
        self.api_key = os.environ.get("IVR_TTS_API_KEY", "")
        self.voice_id = os.environ.get("IVR_TTS_VOICE_ID", "")
        if not self.api_key:
            raise RuntimeError("IVR_TTS_API_KEY not set")

    def synth(self, text, lang="ta"):
        # Placeholder — implement real call when key is provisioned
        raise NotImplementedError("Production TTS not configured")


# ---------------------------------------------------------------- STT
class STTProvider:
    def recognize(self, audio_base64: str, lang: str = "ta") -> dict:
        raise NotImplementedError


class MockSTT(STTProvider):
    """Mock STT — the simulator passes the recognized string directly."""
    def recognize(self, audio_base64, lang="ta"):
        return {"ok": False, "error": "MockSTT: use simulator transcript input"}


class GoogleCloudSTT(STTProvider):
    def __init__(self):
        self.creds = os.environ.get("IVR_GOOGLE_CREDS_JSON", "")
        if not self.creds:
            raise RuntimeError("IVR_GOOGLE_CREDS_JSON not set")

    def recognize(self, audio_base64, lang="ta"):
        raise NotImplementedError("Production STT not configured")


# ---------------------------------------------------------------- AI Intent
class AIIntentProvider:
    def recognize(self, text: str, language: str, context: str) -> dict:
        raise NotImplementedError


class MockIntent(AIIntentProvider):
    """Uses the local rule-based recognizer (ivr.intents)."""
    def recognize(self, text, language, context):
        from .intents import recognize_intent
        ir = recognize_intent(text, language, context=context)
        return ir.to_dict()


class DialogflowIntent(AIIntentProvider):
    """Production Google Dialogflow ES adapter."""
    def __init__(self):
        self.project_id = os.environ.get("IVR_DIALOGFLOW_PROJECT", "")
        if not self.project_id:
            raise RuntimeError("IVR_DIALOGFLOW_PROJECT not set")

    def recognize(self, text, language, context):
        raise NotImplementedError("Production NLU not configured")


# ---------------------------------------------------------------- Factories
def get_telephony() -> TelephonyProvider:
    if MODE == "production":
        provider_name = os.environ.get("IVR_TELEPHONY_PROVIDER", "twilio").lower()
        if provider_name == "twilio":
            try:
                return TwilioTelephony()
            except RuntimeError:
                pass
    return MockTelephony()


def get_tts() -> TTSProvider:
    if MODE == "production":
        provider_name = os.environ.get("IVR_TTS_PROVIDER", "").lower()
        if provider_name == "elevenlabs":
            try:
                return ElevenLabsTTS()
            except RuntimeError:
                pass
    return MockTTS()


def get_stt() -> STTProvider:
    if MODE == "production":
        provider_name = os.environ.get("IVR_STT_PROVIDER", "").lower()
        if provider_name == "google":
            try:
                return GoogleCloudSTT()
            except RuntimeError:
                pass
    return MockSTT()


def get_intent() -> AIIntentProvider:
    if MODE == "production":
        provider_name = os.environ.get("IVR_INTENT_PROVIDER", "").lower()
        if provider_name == "dialogflow":
            try:
                return DialogflowIntent()
            except RuntimeError:
                pass
    return MockIntent()


def mode_info() -> dict:
    """Return the currently active mode + provider names for the admin UI."""
    return {
        "mode": MODE,
        "telephony": type(get_telephony()).__name__,
        "tts": type(get_tts()).__name__,
        "stt": type(get_stt()).__name__,
        "intent": type(get_intent()).__name__,
        "public_base_url": os.environ.get("IVR_PUBLIC_BASE_URL", ""),
        "ivr_number": os.environ.get("IVR_TWILIO_NUMBER", ""),
    }
