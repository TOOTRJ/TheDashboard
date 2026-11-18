# V16 Stop reserve review and root run recipe

The private V16 candidate makes two commands distinct for the first time.
After Install at 1, Acquire at 2, Resume at 3 and Renew at 4, the original
reserved Stop at 5 references Resume as prior control and Renew as previous
head. Stop pins the renewed fence F2 directly and retains F1 through the
historical prefix. This is the smallest seven-direct-pin witness.

| Event | New retained rows | Logical writes | Logical keys | Row touches with staging | Key touches with staging |
| --- | ---: | ---: | ---: | ---: | ---: |
| Install | 23 | 24 | 48 | 25 | 51 |
| Acquire | 10 | 11 | 22 | 12 | 25 |
| Resume | 9 | 10 | 20 | 11 | 23 |
| Renew | 11 | 12 | 24 | 13 | 27 |
| Original Stop after Renew | 9 | 10 | 20 | 11 | 23 |
| Whole scope including six bootstrap rows | 68 | 67 | 134 | 72 | 149 |

For Renew, the eleven retained rows are one original, one journal, one
operation identity, one versioned domain fact and seven associations.
Stop retains one original, one journal and seven associations. It allocates
no identity or domain fact. Each event updates one existing scope row, and
the staged original adds one row and three declared key touches. Stop's
discrete charge equals the existing terminal reserve, and Renew is still
ordinary work under the unchanged budget before DML and at COMMIT. The
witness keeps one position and one revision increment available to Stop.

For Stop's bytes, the existing independent November 5 worksheet's refined
envelope applies to this admitted path. Its seven pins are bounded as follows.

- Genesis 8,192, installation Command 1,827, epoch 2,048, terminal 1,024.
- Previous-head Renew Command 16,384 and prior-control Resume Command 801.
- Renewed fence record 1,024, including its immutable original Command
  digest and fixed UUID and decimal grammar.

The existing worksheet counts double escaping per embedded wire and the
wider false Boolean, complete finalized and pending originals, signed64
clock widths, metadata and declared keys. It yields at most 75,678 logical
and 142,415 staging-inclusive encoded bytes under the stated grammars.
The unchanged 76,533 and 144,142 reserves exceed those upper bounds by 855
and 1,727 bytes. F1 remains in the getter closure only, so it does not add
another direct pin to Stop's Result or staged wire. Its association stays
charged to the earlier operations. The Renew/Stop closure counts are 14/17
and remain under the separate 70-pin cap. The test independently observes
selected row charges, encoded complete scalar plus LF, and reserve
consumption; the broader admitted maximum remains open.

## Root-owned exact composition

1. Verify the V16 manifest at SHA-256
   `2c60d6e931facaed1798a9a2bc4649f7a112ebefce6e490d16a2e52a8a558f8c`.
   Reconstruct the exact V15 postimages, apply the patch at SHA-256
   `37db1fc6077cafc331927db0792b35ed99ed6adbd342db2a5f5b2d6f0fae8b0c`
   and verify all six V16 source hashes. Direct private postimages have
   the same pins. Keep earlier candidate and receipts immutable.
2. The exact prior accepted composition uses PR113 Git commit
   `7ff9b886a2d19de5388b86a5c3985a8705567edc`, tree
   `9d6c512e6ea6f9b036cf82f7cc67199cc57dc4ae`, 930 ordinary tracked blobs.
   All six candidate destinations are absent there. Export those exact
   bytes to a fresh owned private snapshot and compose 936 files. If
   reviewing a newer accepted base, separately pin its tree and full
   composition; no working-copy or untracked overlays.
3. After independent source and controller review, follow the accepted V15
   recipe for explicit socket, cached immutable PostgreSQL 17.6 ARM64
   image, owner-only Docker configuration, network none, CPython 3.12.14,
   exact ordered IDs, narrowly normalized environment and exact owned
   cleanup. Preserve the 240-second outer deadline. Keep the statistics
   case first. This manifest orders all 35 cases. V15's 204.871-second
   run leaves 35.129 seconds of historical headroom, which is not a
   controlled upper bound. A timeout must remain in the evidence. Any
   predeclared split into separately bound case sets is a different
   experiment; each keeps its own bound, snapshot and raw receipt.
4. Accept the witness only with actual native test results, six source
   postimage checks, unchanged full snapshot and exact normal cleanup.
   The remaining work includes real late Renew expiry, repeated Renew
   and position-cap refusal, other kinds, hosted owner and physical
   capacity. The private V16 patch contains review data for these steps.
