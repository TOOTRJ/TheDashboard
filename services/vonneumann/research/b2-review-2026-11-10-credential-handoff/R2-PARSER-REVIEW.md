# R2 parser correction

The original candidate stopped during installation with SQLSTATE 42601 at
the newly declared _handoff_allows_renew parameter named position.
The frozen original raw log and receipt remain separate and are pinned in
the new manifest. No original experiment files or results were rewritten.

Apply candidate-generation-stop-to-r2.patch to the exact ten-file R1
postimage. The patch changes only the helper's argument name and two
matching references, plus the fixture's exact argument name expectation
and SQL hash. It does not change any test, authorization, capacity
charge, catalog equality, operation semantics or transaction setting.
All 52 source method IDs and the three focused partitions are unchanged.
Reconstruct and bind the new 946-file snapshot before a separate launch.
The R1 review recipe still describes the case logic and limits. Static
reconstruction passed before the separate native runs recorded in the
[candidate README](README.md).
