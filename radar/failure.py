from __future__ import annotations
from pathlib import Path
from .config import APP_HOME
from .db import connect, emit_event
from .receipts import write_receipt

def record_workaround(original_target:str, original_blocker:str, failed_gate:str, attempt_history:list,
                      workaround_chain:list, bypass_point=None, behavioral_differences=None,
                      remaining_limitations=None, rollback_path=None, verification_result=None,
                      home:Path=APP_HOME):
    payload={
      "original_target":original_target,"original_blocker":original_blocker,"failed_gate":failed_gate,
      "attempt_history":attempt_history,"workaround_chain":workaround_chain,"bypass_point":bypass_point,
      "behavioral_differences":behavioral_differences or [],"remaining_limitations":remaining_limitations or [],
      "rollback_path":rollback_path,"verification_result":verification_result,
    }
    op="bypass.verify" if bypass_point else "workaround.attempt"
    status="OK" if bypass_point and verification_result in {"PASS","OK","LIVE","BYPASS_LIVE"} else "HOLD"
    receipt=write_receipt(op,inputs={"original_target":original_target},result=payload,status=status,home=home)
    with connect(home) as con:
        emit_event(con,"BYPASS VERIFY" if bypass_point else "WORKAROUND ATTEMPT",failed_gate,None,payload,receipt["receipt_id"])
    return {"status":status,"receipt":receipt,"record":payload}
