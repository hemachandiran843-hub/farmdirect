"""IVR REST API + telephony webhooks.

Both the in-app IVR Simulator and real telephony providers (Twilio etc.)
hit the same endpoints. The only difference is the payload shape:

  Simulator  → JSON {session_token, input, dtmf, caller_number, source='simulator'}
  Twilio    → form-encoded TwiML webhook fields (From, Digits, SpeechResult, ...)

This blueprint normalizes both into a single internal API so the
dialog logic doesn't care who is calling.
"""
from __future__ import annotations
import json
import time
from datetime import datetime
from flask import Blueprint, jsonify, request, session as flask_session, render_template, abort, g

import db
from ivr import DialogManager
from ivr.session import (new_session, load_session, load_session_by_token,
                        save_session, log_event, finalize_call_log)
from ivr.providers import (get_telephony, get_tts, get_stt, get_intent,
                          mode_info)

bp = Blueprint("ivr_api", __name__)


# ------------------------------------------------------------------ helpers
def _ok_or_401():
    """Simulator endpoints allow any logged-in user; anonymous callers
    can use simulator with a chosen caller_number too (for demo)."""
    pass


def _extract_twilio_input(form) -> tuple[str | None, str | None, str | None]:
    """Return (text, dtmf, caller_number) from a Twilio webhook."""
    text = form.get("SpeechResult") or None
    dtmf = form.get("Digits") or None
    caller = form.get("From", "").lstrip("+")
    return text, dtmf, caller


def _extract_simulator_input(data) -> tuple[str | None, str | None, str | None]:
    """Return (text, dtmf, caller_number) from the in-app simulator."""
    text = data.get("input") or data.get("text") or None
    dtmf = data.get("dtmf") or None
    caller = data.get("caller_number") or data.get("caller") or None
    return text, dtmf, caller


def _start_or_resume(caller_number: str, call_id: str | None) -> dict:
    """Find the most-recent active session for this caller, or create one."""
    row = db.query(
        "SELECT * FROM ivr_sessions WHERE caller_number=? AND status='active' "
        "ORDER BY id DESC LIMIT 1", (caller_number,), one=True)
    if row:
        return load_session(row["id"])
    return new_session(caller_number, call_id)


# ------------------------------------------------------------------ /api/ivr/incoming
@bp.post("/ivr/incoming")
def ivr_incoming():
    """First contact: Twilio answers the call, simulator clicks 'Call'."""
    is_twilio = "SpeechResult" in request.form or "From" in request.form
    if is_twilio:
        text, dtmf, caller = _extract_twilio_input(request.form)
        call_id = request.form.get("CallSid")
    else:
        data = request.get_json(silent=True) or request.form.to_dict()
        text, dtmf, caller = _extract_simulator_input(data)
        call_id = data.get("call_id") or f"sim-{int(time.time())}"

    caller = caller or data.get("caller_number") if not is_twilio else caller
    if not caller:
        return jsonify({"ok": False, "error": "caller_number required"}), 400

    sess = _start_or_resume(caller, call_id)
    mgr = DialogManager(sess)

    # initial prompt — no input yet
    from ivr.i18n import WELCOME
    prompt = list(WELCOME[sess["language"]])
    save_session(sess)
    log_event(sess["id"], "prompt", response_text=" ".join(prompt))

    telephony = get_telephony()
    if is_twilio:
        answer = telephony.answer(sess["session_token"],
                                 callback_url=(mode_info()["public_base_url"] + "/api/ivr/input"))
        return (answer.get("twiml", ""), 200,
                {"Content-Type": answer.get("content_type", "application/xml")})
    return jsonify({
        "ok": True,
        "session_token": sess["session_token"],
        "session_id": sess["id"],
        "language": sess["language"],
        "current_menu": sess["current_menu"],
        "prompt": prompt,
        "mode": mode_info(),
    })


# ------------------------------------------------------------------ /api/ivr/input
@bp.post("/ivr/input")
def ivr_input():
    """Main loop endpoint: caller provides text/speech/DTMF."""
    is_twilio = "From" in request.form or "SpeechResult" in request.form or "Digits" in request.form
    if is_twilio:
        text, dtmf, caller = _extract_twilio_input(request.form)
        session_token = request.args.get("session_token")
        call_id = request.form.get("CallSid")
    else:
        data = request.get_json(silent=True) or request.form.to_dict()
        text, dtmf, caller = _extract_simulator_input(data)
        session_token = data.get("session_token")
        call_id = data.get("call_id")

    # locate session
    sess = None
    if session_token:
        sess = load_session_by_token(session_token)
    if not sess and caller:
        sess = _start_or_resume(caller, call_id)
    if not sess:
        return jsonify({"ok": False, "error": "no active session"}), 404

    mgr = DialogManager(sess)
    start_ts = time.time()
    step = mgr.process_input(text=text, dtmf=dtmf)
    duration = int(time.time() - start_ts)

    # log the event
    log_event(
        sess["id"],
        event_type="speech" if text else "dtmf",
        raw_input=dtmf or text,
        recognized_text=text,
        intent=step.intent,
        intent_payload=step.intent_payload,
        response_text=" ".join(step.prompt),
        backend_action=(step.action or {}).get("name"),
        backend_result=(step.action or {}).get("result") or (step.action or {}).get("error"),
    )

    if is_twilio:
        telephony = get_telephony()
        if step.ended:
            resp = telephony.hangup(sess["session_token"])
        else:
            # Twilio needs TwiML — combine prompts into one Say
            prompt_text = " ".join(step.prompt) or "Please continue."
            cb_url = mode_info()["public_base_url"] + f"/api/ivr/input?session_token={sess['session_token']}"
            resp = telephony.gather_speech(prompt_text, callback_url=cb_url,
                                          lang="ta-IN" if sess["language"] == "ta" else "en-IN")
        return (resp.get("twiml", ""), 200,
                {"Content-Type": resp.get("content_type", "application/xml")})

    return jsonify({
        "ok": True,
        "session_token": sess["session_token"],
        "session_id": sess["id"],
        "language": sess["language"],
        "current_menu": sess["current_menu"],
        "prompt": step.prompt,
        "intent": step.intent,
        "intent_payload": step.intent_payload,
        "action": step.action,
        "failure_count": step.failure_count,
        "ended": step.ended,
        "mode": mode_info(),
    })


# ------------------------------------------------------------------ /api/ivr/session
@bp.get("/ivr/session")
def ivr_get_session():
    """Fetch a session by token (used by the simulator to resume)."""
    token = request.args.get("session_token")
    if not token:
        return jsonify({"ok": False, "error": "session_token required"}), 400
    sess = load_session_by_token(token)
    if not sess:
        return jsonify({"ok": False, "error": "session not found"}), 404
    # latest event (last prompt)
    last = db.query(
        "SELECT * FROM ivr_events WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (sess["id"],), one=True)
    return jsonify({
        "ok": True,
        "session": _public_session(sess),
        "last_event": dict(last) if last else None,
    })


# ------------------------------------------------------------------ /api/ivr/callback
@bp.post("/ivr/callback")
def ivr_callback():
    """Provider call-status webhook (Twilio statusCallback)."""
    is_twilio = "CallSid" in request.form
    call_id = request.form.get("CallSid") if is_twilio else (request.json or {}).get("call_id")
    status = request.form.get("CallStatus") or (request.json or {}).get("status")
    sess = db.query("SELECT * FROM ivr_sessions WHERE call_id=? ORDER BY id DESC LIMIT 1",
                   (call_id,), one=True)
    if not sess:
        return jsonify({"ok": False}), 404
    if status in ("completed", "ended"):
        # finalize call log
        s = load_session(sess["id"])
        if s:
            transcript = db.query(
                "SELECT event_type, recognized_text, response_text, intent FROM ivr_events "
                "WHERE session_id=? ORDER BY id", (s["id"],))
            t = [{"role": "user" if e["event_type"] in ("speech", "dtmf") else "system",
                 "text": e["recognized_text"] or e["response_text"] or "",
                 "intent": e["intent"]} for e in transcript]
            finalize_call_log(s, intent=s.get("current_intent") or "",
                            success=(status == "completed"),
                            had_error=False, duration_sec=0, transcript=t)
            db.execute("UPDATE ivr_sessions SET status='ended' WHERE id=?", (s["id"],))
    return jsonify({"ok": True, "status": status})


# ------------------------------------------------------------------ /api/ivr/hangup
@bp.post("/ivr/hangup")
def ivr_hangup():
    """Simulator-driven hangup (and finalize call log)."""
    data = request.get_json(silent=True) or request.form.to_dict()
    token = data.get("session_token")
    sess = load_session_by_token(token) if token else None
    if not sess:
        return jsonify({"ok": False, "error": "session not found"}), 404
    transcript = db.query(
        "SELECT event_type, recognized_text, response_text, intent FROM ivr_events "
        "WHERE session_id=? ORDER BY id", (sess["id"],))
    t = [{"role": "user" if e["event_type"] in ("speech", "dtmf") else "system",
         "text": e["recognized_text"] or e["response_text"] or "",
         "intent": e["intent"]} for e in transcript]
    start_time = sess.get("created_at")
    duration = max(0, int(time.time() - (datetime.fromisoformat(start_time).timestamp()
                                         if start_time else time.time())))
    finalize_call_log(sess, intent=sess.get("current_intent") or "",
                    success=True, had_error=False,
                    duration_sec=duration, transcript=t)
    db.execute("UPDATE ivr_sessions SET status='ended' WHERE id=?", (sess["id"],))
    return jsonify({"ok": True})


# ------------------------------------------------------------------ /api/ivr/admin/stats
@bp.get("/ivr/admin/stats")
def ivr_admin_stats():
    """Aggregated IVR analytics for the admin dashboard."""
    if not g.user or g.role != "admin":
        return jsonify({"ok": False, "error": "admin only"}), 403
    stats = {
        "total_calls": db.query("SELECT COUNT(*) n FROM ivr_call_logs", one=True)["n"],
        "successful": db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE success=1", one=True)["n"],
        "failed": db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE had_error=1 OR success=0", one=True)["n"],
        "tamil_calls": db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE language='ta'", one=True)["n"],
        "english_calls": db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE language='en'", one=True)["n"],
        "avg_duration": db.query("SELECT COALESCE(AVG(duration_sec),0) v FROM ivr_call_logs", one=True)["v"],
        "listings_created": db.query("SELECT COALESCE(SUM(listings_created),0) v FROM ivr_call_logs", one=True)["v"],
        "bulk_accepted": db.query("SELECT COALESCE(SUM(bulk_accepted),0) v FROM ivr_call_logs", one=True)["v"],
        "price_requests": db.query("SELECT COALESCE(SUM(price_requests),0) v FROM ivr_call_logs", one=True)["v"],
        "order_requests": db.query("SELECT COALESCE(SUM(order_requests),0) v FROM ivr_call_logs", one=True)["v"],
        "earnings_requests": db.query("SELECT COALESCE(SUM(earnings_requests),0) v FROM ivr_call_logs", one=True)["v"],
        "active_sessions": db.query("SELECT COUNT(*) n FROM ivr_sessions WHERE status='active'", one=True)["n"],
    }
    # top intents
    top_intents = db.query(
        "SELECT current_intent AS intent, COUNT(*) n FROM ivr_sessions "
        "WHERE current_intent IS NOT NULL GROUP BY current_intent ORDER BY n DESC LIMIT 10")
    # recent events with errors
    error_count = db.query("SELECT COUNT(*) n FROM ivr_events WHERE error IS NOT NULL OR event_type='error'",
                          one=True)["n"]
    # intent distribution from events
    intent_dist = db.query(
        "SELECT intent, COUNT(*) n FROM ivr_events WHERE intent IS NOT NULL "
        "AND intent<>'UNKNOWN' GROUP BY intent ORDER BY n DESC LIMIT 10")
    return jsonify({
        "ok": True, "stats": stats,
        "top_intents": [dict(r) for r in top_intents],
        "intent_dist": [dict(r) for r in intent_dist],
        "error_count": error_count,
        "mode": mode_info(),
    })


@bp.get("/ivr/admin/calls")
def ivr_admin_calls():
    """List recent IVR calls with details."""
    if not g.user or g.role != "admin":
        return jsonify({"ok": False, "error": "admin only"}), 403
    rows = db.query(
        "SELECT c.*, s.caller_number, s.language AS session_language "
        "FROM ivr_call_logs c JOIN ivr_sessions s ON s.id=c.session_id "
        "ORDER BY c.id DESC LIMIT 50")
    return jsonify({"ok": True, "calls": [dict(r) for r in rows]})


@bp.get("/ivr/admin/call/<int:call_id>")
def ivr_admin_call_detail(call_id):
    if not g.user or g.role != "admin":
        return jsonify({"ok": False, "error": "admin only"}), 403
    call = db.query("SELECT * FROM ivr_call_logs WHERE id=?", (call_id,), one=True)
    if not call:
        return jsonify({"ok": False, "error": "not found"}), 404
    events = db.query("SELECT * FROM ivr_events WHERE session_id=? ORDER BY id",
                     (call["session_id"],))
    transcript = []
    if call["transcript"]:
        try:
            transcript = json.loads(call["transcript"])
        except json.JSONDecodeError:
            transcript = []
    return jsonify({
        "ok": True,
        "call": dict(call),
        "events": [dict(e) for e in events],
        "transcript": transcript,
    })


# ------------------------------------------------------------------ /api/ivr/mode
@bp.get("/ivr/mode")
def ivr_mode():
    return jsonify({"ok": True, **mode_info()})


# ------------------------------------------------------------------ helpers
def _public_session(sess: dict) -> dict:
    return {
        "id": sess["id"],
        "session_token": sess["session_token"],
        "caller_number": sess["caller_number"],
        "language": sess["language"],
        "current_menu": sess["current_menu"],
        "current_intent": sess.get("current_intent"),
        "auth_status": sess.get("auth_status"),
        "status": sess["status"],
        "user_id": sess.get("user_id"),
        "farmer_id": sess.get("farmer_id"),
        "failure_count": sess.get("failure_count", 0),
        "created_at": sess["created_at"],
        "updated_at": sess["updated_at"],
    }
