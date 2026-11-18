# Recorded transport capacity measurements — November 9, 2026

The measured runner uses the actual disconnected provider-recorded transport with synthetic HTTP bodies. A test transport counts requests and does not keep request objects. Each body profile runs in a fresh process under the existing locked CPython 3.12.14 environment. Network access is denied. The fixture supplies only synthetic test inputs and the fixed source timestamp provides no minute eligibility. The receipts hash the measurement script, three transport and parser files, two fixture helpers and the development lock. They also report the runtime HTTP dependency versions.

| HTTP body profile | Completed | First pre-I/O refusal | Charged per packet | Retained bytes | Collect p50 / p95 / p99 |
|---|---:|---:|---:|---:|---:|
| Minimal JSON | 945 | Outside test bound | 6,606 B | 6,242,670 B | 1.648 / 1.752 / 1.907 ms |
| 4,096 B Price and two 1,024 B RPCs | 361 | 362 | 20,341 B | 7,343,101 B | 2.597 / 2.721 / 2.824 ms |
| Maximum body trio | 12 | 13 | 617,677 B | 7,412,124 B | 42.289 / 43.082 / 43.082 ms |

The local elapsed samples use nearest-rank percentiles. The maximum-body p95 and p99 are the slowest of 12 samples. Process-lifetime peak RSS was 52.51 MB, 53.54 MB and 53.90 MB respectively. Phase timings, CPU time and counts are in the measured receipts. An accepted packet can take retention beyond the 7,340,032-byte pre-I/O threshold. The next request then refuses before any I/O. Replaying the first and last originals after close made zero new synthetic calls. A preliminary run on the same source bodies and limits reproduced all bytes, call counts, refusal indices and restart outcome with different timings.

The restart case sends SIGKILL only to the owned child after it flushes a digest-only witness. A fresh transport has no retained state. In this controlled negative test, deliberate fake resubmission of the exact same plan and raw body makes different original capsule hashes because receipt clocks change. The collector therefore needs an authorized durable getter to recover the original after process loss. The existing in-process waiter-cancellation, exact replay and refusal cases pass. The test is a crash-retention witness, with no authenticated native readback, provider or hosted timing claim.

From the repository root, substitute the exact locked Python and a private temporary HOME. Run each profile in its own process.

```sh
env -i PATH=/usr/bin:/bin HOME="$private_home" PYTHON_DOTENV_DISABLED=1 \
  "$locked_python" -I -B services/vonneumann/research/paper-capacity/measure_transport.py \
  profile --body tiny --attempts 945
```

Repeat with `padded` and `max`. Use `restart` in place of the profile arguments for the child interruption witness. These observations measure rapid synthetic requests. They provide neither a real 945-minute source trace nor a throughput guarantee for economic commands, PostgreSQL, leases, relays, quotas, or Railway.

## Native journal and exact backend interruption

A separate isolated PostgreSQL 17.6 run used the pinned I2a snapshot and a single test-only overlay, `services/vonneumann/tests/postgres/test_b2_recovery_observation.py`. The first run observed that the exact backend was gone, then timed out waiting for the local psql client to finish reading stdin. It did not reach independent recovery. Its fixture and process group were removed normally. The corrected overlay closes only the tracked client after observing backend absence, with the same termination queries and deadlines. The corrected case passed in 9.378 seconds. Its separate run receipt confirms all 943 source files unchanged, normal exact fixture and process group cleanup, and no timeout or fallback. The combined receipt preserves both runs and each overlay, controller and snapshot digest. [Native observations](native-observations.json)

The fixture staged the original Install, sent literal COMMIT, and obtained an independent finalized-row witness before terminating the exact scoped backend. The writer response was not used. A fresh reader recovered the exact original and same-ID replay left every committed row unchanged. The separately staged Acquire was terminated before COMMIT. Its exact original still resolved as `observed_absent_unknown`, with the same committed snapshot. This tests actual session interruption against an owned database that remains running. It uses a trust socket, so it supplies no new SCRAM or hosted recovery result.

| Observation | Before Install | After committed Install | After interrupted Acquire |
|---|---:|---:|---:|
| Committed journal positions and originals | 0 | 1 | 1 |
| Retained rows in measured scope | 6 | 29 | 29 |
| Independently encoded canonical logical row bytes | 18,438 | 59,579 | 59,579 |
| Contract-charged logical bytes | 0 | 59,653 | 59,653 |
| Physical allocation across eight whole fixture relations | 294,912 B | 475,136 B | 507,904 B |
| Global WAL insert offset delta since prior point | — | 35,144 B | 14,296 B |

Physical allocation and WAL grew during the aborted transaction while its committed logical rows stayed unchanged. Physical totals include both fixture scopes. WAL is instance-wide and may include other fixture activity. These are observed deltas, with no general write amplification claim. Single-sample phase times were 104.323 ms for Install stage to provisional acknowledgment, 115.293 ms from sending COMMIT to the independent finalized witness, 95.275 ms for recovery and 129.859 ms for exact replay. They include local client and polling overhead where applicable. They establish neither latency tails nor recovery after a database server restart.
