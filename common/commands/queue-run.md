---
description: New name of the batch runner (what `cepa run` dispatches for each item). Transitional entry until the command files are renamed (reforma-de-nomes CS-3); runs /common:drain-plan with the same arguments.
argument-hint: <name> [same arguments as /common:drain-plan]
interaction: conversational
---

# /common:queue-run

This is the new name of `/common:drain-plan`, the batch runner of the repo's
single-track queue (`cepa run <queue>` starts one `claude -p` per item with
`/common:queue-run <queue> --max 1`).

Until the command files themselves are renamed (item CS-3 of the queue
`reforma-de-nomes`), say so in one line, then run `/common:drain-plan` with
exactly the same arguments (`$ARGUMENTS`) and follow its workflow from the top.
Do not keep a second copy of the steps here.
