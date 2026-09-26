# Working Agreement – Phase 7: JobController

## Modul
src/jobcontroller/

## Verantwortung
- Orchestrierung
- State Machine
- Locking & Recovery

## Öffentlicher Contract (api.py)
- submit(pdf_path: str)

## State
NEW -> LOCKED -> PARSED -> ASSAYS_DETECTED -> EXTRACTED -> WRITTEN -> DONE
FAILED möglich

## Recovery
- zeitbasierter stale-lock
