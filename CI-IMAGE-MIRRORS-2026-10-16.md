# Exact-content official image mirrors — 2026-10-16

Public registry metadata confirms that Docker Hub serves the two original Linux AMD64 fixture manifests and image configs under the official publisher namespaces below. This supports a small rate-limit fallback while retaining the original image content. No Docker command, pull, load, layer download, tag mutation or native test was performed for this observation.

The selected original observations and independent comparisons are retained in [scripts/check-ci-image-mirrors-evidence.json](scripts/check-ci-image-mirrors-evidence.json), SHA-256 `39c5881f9b76748e5fb013b72a8dbf0e3009910987c6e9e2940fe2035f41a93b`. Exact request wall timestamps and original raw manifest/config bodies were not archived. The observation date is the task date; no timestamp was reconstructed.

## Publisher references and rejected alias

Supabase's [official Compose file](https://raw.githubusercontent.com/supabase/supabase/master/docker/docker-compose.yml) uses the `supabase/postgres` and `postgrest/postgrest` Docker Hub namespaces. Its current tags are newer than the project's pins; they were not adopted. The [official version history](https://github.com/supabase/supabase/blob/master/docker/versions.md) explicitly records `postgrest/postgrest:v14.5` on February16,2026. The [hosting documentation](https://supabase.com/docs/guides/self-hosting/docker) also links Supabase's Docker Hub organization and Compose updates. These references establish publisher provenance; raw-byte equality establishes content identity.

`docker.io/supabase/postgrest:v14.5` returned **404** after a valid anonymous registry challenge/token exchange. It is **rejected**, not an allowed alias. This result concerns that requested tag and does not claim that every tag or the whole repository is nonexistent.

## Actual original-content comparisons

| Candidate | Tag index raw SHA-256 | Original AMD64 manifest | Original config |
| --- | --- | --- | --- |
| `docker.io/supabase/postgres:17.6.1.095` | `965e2dfb5a23a0d6541b6106541e777b303656ebabd4e878746b189d550c0a66` | `4c087262afbfbb47da86e2863a52d7e424eb21ab589f732d77eeaab51be8e521` | `972aabc75779f6e535f87e1669f36edbab02cdf8bf3f47d13579963c119adefb` |
| `docker.io/postgrest/postgrest:v14.5` | `b574528fe109c8343c1247155734d03df8c34b462f342dca0ccc20244fc36ef9` | `bb289d00570b569525e1e22fb77c49cd17c17ca3f41da9ee2b4351a35027551b` | `af0a6dad76305650c215449d905a124ae5ad3bcd0f04c01845a0cea17d4e0960` |

Both tag requests returned200 and had exactly one Linux AMD64 descriptor. The selected descriptors matched the original manifest constants already held from `scripts/check-ci-images.py`. Subsequent immutable-manifest requests returned200; their calculated raw-byte SHA-256 values and `Docker-Content-Digest` headers exactly equaled those independently held constants. Each original config descriptor equaled the independent original config pin, and the separately downloaded config bytes hashed to that pin with the exact declared size and `linux`/`amd64` fields.

PostgreSQL: tag index1609bytes; original manifest5775bytes; original config13529bytes;29 layer descriptors and29 config DiffIDs. PostgREST: tag index1137bytes; original manifest527bytes; original config485bytes;1 layer descriptor and1 config DiffID. No config `Env` or other raw config fields were published. Layer descriptor counts and config DiffID counts are observations; the layer payloads themselves were not fetched or decompressed.

The independent pin-source file before mirror implementation is SHA-256 `1d28e16d3db54c5ed5f709c872f0e0b6470e2c85a2a9cdda8d02b2618efc3d5f`. Its literal three-image `PINS` tuple was read separately from the candidate metadata. The Python image remains unchanged and was not re-queried. The original expected manifest/config values were not derived from whichever tag the registry returned.

## Read-only request isolation

Requests used an empty child environment, verified HTTPS with hostname checking and TLS1.2 minimum, no inherited proxy or key-log context,15-second request timeouts and1MiB response caps. The initial401 challenge had to match `auth.docker.io/token`, service `registry.docker.io`, and the exact candidate repository's read scope. Short-lived anonymous JWTs stayed only in memory; no shared Docker login/configuration or private account credential was used. Original config requests redirected to `production.cloudfront.docker.com`; Authorization was stripped before that request, and signed redirect URLs were not published. No global/shared credential or configuration was changed.

## Narrow implementation boundary

The separately approved fallback proposal permits a source change only after a classified rate-limit. Across both sources it retains **five total pull attempts** and **one240-second pull-phase deadline** per image, including initial staggering and retry backoff. Subsequent inspect/tag/inspect commands retain their existing30-second limit each;240seconds is not a whole-helper deadline. The proposal preserves the original manifest/config tuples, canonical fixture tags and harnesses. Pull the exact original digest from the separately reviewed mirror repository, verify the actual mirror RepoDigest and existing immutable-ID/config/platform predicate, then assign the existing local fixture tag. A local tag is not an ECR RepoDigest; no ECR registry metadata may be fabricated.

Do not use the rejected `supabase/postgrest` alias, mutable tag resolution as pull authority, a reset deadline or five attempts per registry. Other recognized transient failures, such as503responses or timeouts, retain the existing bounded retries against the currently selected source; they do not permit a mirror transition. Permanent authorization/manifest/daemon failures, unknown errors and identity mismatches remain refusals. The third Python pin, SQL inventory, mandatory four shards and native test deadlines remain unchanged.

This document records completed metadata research. It does not claim Docker Hub availability from GitHub runners, actual Docker pull or load acceptance, post-pull RepoDigest spelling, or a passing required SQL run. Those implementation and CI gates remain open until actually observed. No production app, database, hosted worker or trading readiness follows from this evidence.
