"""Webhooks Router — Twilio TwiML, platform callbacks"""
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()


@router.post("/twiml/connect")
async def twiml_call_connect(request: Request):
    """
    TwiML for Twilio call connect.
    Answers the agent's phone, plays a message, then bridges to the lead.
    """
    params = request.query_params
    lead_phone = params.get("lead_phone", "")
    lead_name = params.get("lead_name", "your lead")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">
    You have a hot lead alert from RealBoost AI.
    {lead_name} is on the line and ready to talk.
    Connecting you now.
  </Say>
  <Dial>
    <Number>{lead_phone}</Number>
  </Dial>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.get("/twiml/connect")
async def twiml_call_connect_get(request: Request):
    return await twiml_call_connect(request)
