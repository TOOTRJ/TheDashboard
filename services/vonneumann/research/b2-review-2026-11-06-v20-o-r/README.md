# V20-O-R terminal retirement races

Two focused native cases passed in 15.533 seconds in isolated PostgreSQL 17.6.
The first observed a live lock wait on the recorder's role row. The existing
retirement transaction reached its second `ALTER ROLE` and failed with
`55P03`. Both original login flags, the absent marker, the committed rows and
the reader's exact original survived rollback.

The second observed an actual provisional Renew and a retirement refusal while
the writer held its locks. After Renew committed at position four, the same
retirement request refused the stale head. Both writers stayed enabled, the
marker remained absent and the reader recovered the committed Renew. The stale
Stop could neither submit nor resolve as committed.

Apply the [test-only patch](candidate-v20-o-to-v20-o-r-test-only.patch) to the
reconstructed [V20-O candidate](../b2-review-2026-11-06-v20-o/README.md). The
[manifest](candidate-manifest-v20-o-r.json) and [native receipt](native-receipt.json)
pin the two cases and exact 942-file PR115 snapshot. The prior 41 test bodies
and the SQL are byte identical. The full 41-case receipt belongs to V20-O.
