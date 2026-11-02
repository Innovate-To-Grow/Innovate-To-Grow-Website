"""The stateful side of request limits: counters (``store``), process heartbeats (``heartbeat``), the policy cache
(``registry``), signal windows and in-flight slots (``signals``), abuse escalation (``abuse``) and applying Smart
decisions (``smart``). Nothing here writes to the database per request."""
