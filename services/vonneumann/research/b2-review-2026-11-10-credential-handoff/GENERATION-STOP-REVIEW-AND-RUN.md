# One-recorder credential handoff with durable Stop intent

This packet implements a separate one-scope direct-SCRAM laboratory profile.
The scope installs, acquires its first fence and opens at Resume3 using its
original recorder. A trusted permit binds the original Install, catalog K1,
exact scope, head and old fence, recorder identity, successor issuance,
authorized Renew4, and reserved Stop. The limited issuer stages only under
the existing package, binding and scope lock order. Its separate role DDL
creates one fixed NOLOGIN role, retires the old recorder and enables the
successor in the same transaction. The native owner grants only schema
USAGE and exact submit/getter EXECUTE. The anchor owner stores the successor
binding and marker. An incomplete or early transaction cannot commit.

The new seal compares a narrowly predicted inverse to K1. It restores the
one old LOGIN bit, removes the one exact new role and creator tuple, and
removes only the pinned native schema and two entry-function ACL atoms and
their three shared dependency rows. Other catalog entries stay in original
order and must hash to the held K1. The focused fixture also independently
constructs the forward K2 catalog in Python from the K1 preimage, assigned
role/creator identities and the exact expected grants and shared dependencies.
The code checks raw K2 during normal authorization, with separate finite
writer and reader windows. The first successor renewal uses the same exact
head and old-fence bytes. Its result records the new holder. Older receipt
and wire bytes retain K1. Issuance material remains within the synthetic
fixture. It opens the successor connection only after an independent
positive marker read.

The native-owner Stop intent is independent of the handoff metadata. K2
control first durably registers the exact reserved Stop command. A fresh
independent reader verifies the committed intent before dispatch. Handoff,
intent registration, successor Renew and fresh Stop observe the same lock
order and current committed head. An intent that wins prevents a later Renew.
A Renew that wins makes the previous head stale before intent registration,
so no stale Stop command is dispatched or rebased. The two admitted cases
use the same preallocated Stop ID and different first valid heads in
separate fixtures.

## Run order

Run one manifest partition in a fresh owned container per invocation.

1. credential_handoff checks package-lock refusal while the old recorder
   has a provisional command, incomplete marker refusal, early constraint
   refusal after full DCL, then real handoff. It verifies old held and fresh
   login paths, exact independent K2, preserved Install/Acquire/Resume,
   wrong successor Renew refusal, and successful exact Renew4.
2. stop_intent_wins tests a real successor blocked on the actual scope lock,
   exact intent COMMIT and independent readback, refusal of the waiting
   renewal, and the exact original Stop4.
3. successor_renew_wins tests the inverse lock order, stale registration
   refusal without dispatch, first exact Stop registration at the new head,
   and Stop5 with the original reserved ID.

The controls may fail during catalog setup if PostgreSQL deparses a new
constructor or ACL differently from the independently pinned expectation.
Retain that actual diagnostic before reviewing any forward correction. A
fixed lifecycle assertion or lock timing failure requires the same care.
The negative cases retain old receipts. The successful cases exercise the
application checks at the fixture's recognized guard points. Physical packet
delivery and service availability require separate tests.

## Reproduction and limits

Reconstruct the seven exact retirement-deadline R2 preimages and apply
candidate-retirement-deadline-to-generation-stop.patch. Static verification
matched every postimage and reversed to the exact parent. The manifest
contains 52 exact source IDs across two modules, preserves all 49 prior
method bodies, and pins the 18-function held core and ten source paths.
Compose 936 tracked PR115 blobs at f317ffc4519d5a70002279458992e54465a9821f,
tree 3eb3469b0d4eb4e4d7993d202fc54909bff9da89, and ten absent candidate
paths for 946 verified source files. Run the existing bounded CPython
3.12.14 network-none/cached PG17.6 ARM64 controller with explicit selected
IDs, the same clean child environment and normal owned cleanup. Count
both modules in the census and select exactly one case per run. No Docker,
native or hosted execution was performed during preparation.

The profile has one scope, one recorder replacement, one durable intent and
one initial transferred fence. Its finite administration charge is separate
from journal position counts and reserves 65,536 retained bytes, 98,304
staged bytes, three retained rows, six logical keys, five row writes and ten
staged key touches. Full admitted maxima, role/catalog physical storage,
all inherited regressions, post-handoff terminal retirement and replacement
after a second generation require separate evidence. No managed Supabase
issuer, Railway runtime, credential transport, continuous data gap or live
trading claim follows from this candidate.
