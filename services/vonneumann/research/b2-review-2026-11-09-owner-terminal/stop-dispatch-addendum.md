# Stop dispatch ordering at handoff

The initial one-recorder handoff note specifies two isolated laboratory
branches. Use them only where the experiment controls whether a Stop was
ever dispatched. The package lock by itself cannot prove that an already
dispatched Stop4 request has arrived or acquired the lock. Renew4 could win
before that request reaches the server, leaving its exact Stop4 stale.
Changing its expected head to manufacture Stop5 is unsafe under the original
ID contract.

Before claiming continuing-run Stop liveness, add a durable exact Stop
intent. An authorized control operation records the preallocated Stop ID,
canonical Stop wire and hash, installation, generation and current head
under package then scope lock, with independent reconciliation before
dispatch. The scope transaction must refuse ordinary successor Renew while
that intent exists. The identical Stop is the only permitted completion.
If Renew wins before the intent was recorded, the intended transaction
refuses stale prior to any dispatch, and the control may build its first
Stop against the verified new head. Keep intents append-only until
definitive receipt or separate reviewed recovery. An uncertain intent or
Stop response needs original-ID reconciliation and keeps successor admission
closed. Extend the one-time admin reserve, include intent in the protocol
and add the real delayed dispatch versus Renew race before this production
claim. The deadline-only candidate has no intent or handoff SQL.
