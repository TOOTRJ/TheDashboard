# V20-O-R-I2a limited creator membership

The corrected focused test passed in 9.735 seconds in isolated PostgreSQL 17.6.
An actual non-superuser `CREATEROLE` issuer created eight actors. The fixture
accepted the exact creator tuples and pinned the actor, issuer and bootstrap
grantor OIDs. The installer committed an original and the independent reader
recovered the exact result. The issuer could neither assume nor administer
either owner.

The reader refused three witnessed catalog changes: an inert incoming actor
grant, an outgoing actor `SET` grant, and an unrelated `SET` grant to the issuer.
The last grant is covered by the corrected incident-membership seal. Rollback
restored the original read and preserved the committed rows.

The first I2 run stopped in fixture setup at SQLSTATE `42601` before executing
a case. I2a parenthesizes the existing `CASE` comparison and repins the SQL
checksum. Its test source is identical. The [native receipts](native-receipts.json)
preserve both runs, including exact 942-file source equality and normal cleanup.

Reconstruct from [V20-O-R](../b2-review-2026-11-06-v20-o-r/README.md). Apply the
[creator patch](candidate-v20-o-r-to-v20-o-r-i.patch), the
[issuer incident-membership patch](candidate-v20-o-r-i-to-v20-o-r-i2.patch)
and the [parser correction](candidate-v20-o-r-i2-to-v20-o-r-i2a.patch) in order.
Verify the [I manifest](candidate-manifest-v20-o-r-i.json),
[I2 manifest](candidate-manifest-v20-o-r-i2.json) and
[I2a manifest](candidate-manifest-v20-o-r-i2a.json) at each stage.

The case uses an isolated trust socket. Real SCRAM transport, credential time,
issuer-controlled terminal recording, managed installation and the full
regression suite on this source remain open.
