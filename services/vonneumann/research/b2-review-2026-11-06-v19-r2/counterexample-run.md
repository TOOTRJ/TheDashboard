# V19-R2 exact counterexample recipe

The candidate adds one test to the exact accepted V19 source. The six-file
reconstruction passed static hash verification. All 38 V19 methods and
the other five files are byte identical. V19 passed 38 actual methods
in three accepted runs. This one new case has yet to execute.

Verify [the manifest](candidate-manifest.json) SHA-256
`c6147287851ab67c6503838b34db25b86910e18908d59f58aa4498a185ba8f9c`
and [the patch](candidate-forward.patch) SHA-256
`057f9ef7b2f0426f34a316282942cde42e1fc584019a20f2bc37956a4149f130`.
Compose the prior exact PR113 930 tracked blobs and six private postimages
in a fresh owned temporary snapshot. The manifest binds its 936 files
composition, exact V19 preimages and one test ID. Use the existing local
Unix socket, cached approved PostgreSQL ARM64 image, network-none runner,
allowlisted environment and CPython 3.12.14. Keep the existing 240-second
outer bound, exact before/after hashes and normal owned cleanup.

The case uses only disposable fixture roles. It obtains an exact provisional
Stop before controlled drift and explicitly rolls it back. One NOLOGIN
blocks Stop. Two block both known writer-original readbacks and Stop even
though actual reader and control sessions remain available. Require the
exact package refusal and unchanged committed snapshots. A synthetic
restoration allows the original bytes to be compared with the initial
readback. Root owns independent review and any execution.
