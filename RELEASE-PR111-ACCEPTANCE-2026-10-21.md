# PR111 release acceptance — October 21, 2026

[PR111](https://github.com/TOOTRJ/TheDashboard/pull/111) is merged and released. All eight jobs in [run39708763776](https://github.com/TOOTRJ/TheDashboard/actions/runs/39708763776) pass. The PR head `764d00a1d0fb149269ff752be99d8965a70272df`, tested checkout `ebe02c7beb2199c36183ac9014971a7db663eb6e`, and actual merge `1fcbf0c84f4fcb5f8b06095e498df1a3965adea6` have the same tree `aa7576cebc2608122324a8a8bba0d14d1f0c498c`. The scoped GitHub helper verifies the canonical repository and immutable repository/account IDs; a fresh scoped fetch confirms the actual merged tree.

The signed-in Vercel browser verifies team `team_8iNNxiNjrOseD4gdSCHkQEzF` / `orderoftheredjester` and project `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` / `the-dashboard`. Exact production [deployment dpl_Gs8rhCg6i9PNgwS1pRXipUtdZ9hG](https://vercel.com/orderoftheredjester/the-dashboard/Gs8rhCg6i9PNgwS1pRXipUtdZ9hG) is READY in 17 seconds, lists the actual merge as its source and currently serves `the-dashboard-chi.vercel.app`. No shared CLI profile or alternate author/upload is used.

Four bounded HTTPS read-only smokes pass: `/login` 200; anonymous `/` 307 to `/login`; anonymous `/api/v1/test?limit=0` 401; authenticated same-path 200 with success and zero rows. Credentials remain in memory, redirects are refused, and writes are zero. These observations were recorded at 2026-10-22T02:55:31.586Z.

This accepts PR111’s documentation and V11b review archive. It does not accept the newer uncommitted parallel batch, the later V12 archive as runtime source, hosted worker restoration, continuous paper operation, or live trading. No Supabase, Railway, provider-key or account-wide mutation accompanies this release. The preceding production rollback candidate is PR110 merge `02f90563c5ececd4f89a3dd92796601b9abdce7b` / deployment `dpl_4DiPn3ojEE4pfLftypmeL4dXRTHk`; use a separately verified project-scoped revert/redeployment if needed.

[Machine-readable source, CI, target and smoke receipt](RELEASE-PR111-ACCEPTANCE-2026-10-21.json).
