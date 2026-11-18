# Next native B2 proofs

## Renew across the real expiry boundary

Use the exact V16 SQL. Install, acquire F1, then Resume after enough database
time has passed to put the earliest possible expiry of F2 later than F1's
expiry. Submit Renew before F1 expires and require a provisional result.
From another session, check that the Renew original is invisible. Send
literal COMMIT after F1's retained deadline but before the earliest possible
F2 expiry. Require the exact fence-clock refusal and unchanged committed
scope rows, associations, fence facts and original-command receipts. A fresh
Renew against expired F1 must also refuse. The original reserved open Stop
must still commit at position 4. Keep the actual clock and existing writer
and outer time bounds. A missed timing window is an incomplete proof.

## Repeated Renew through the position cap

This requires a forward change. Each Renew binds the immediate prior head
and the two relevant fence versions. Stop needs separate explicit selection
of the prior Resume control, latest Renew head and latest fence version.
After the second Renew, inheriting the immediately previous Result's pins
would lose the earlier Resume command. Keep older versions in the readback
closure.

1. Commit distinct Renew originals at positions 4 through 15. Verify each
   from its original ID and exact readback. The position-15 closure should
   have 58 pins.
2. Submit an otherwise valid ordinary Renew at 16. Verify from independently
   counted fixtures that all non-position reserve checks fit, including
   112 dependency associations with the reserve and the encoded wire
   limits. The position check must be the decisive refusal. Confirm no
   committed writes or new original for the refused operation.
3. Submit the original reserved Stop at position 16. Verify seven distinct
   direct pins, a 61-pin readback closure, exact replay and canonical scalar
   framing with its final LF. Expected completed scope: 189 retained rows,
   199 logical writes and 398 logical keys; 215 row touches and 446 key
   touches with staging. Measure actual admitted charges against the
   existing reserve. This reaches two-digit position and revision widths
   without padding or altering trusted rows.

The closed UUID, digest and decimal grammar cannot fill the general
16,384-byte prior-command cap. Keep the structural worst-width calculation
as a separate bound and extend the native witness when additional admitted
command shapes can reach it. Neither test establishes production ownership,
physical storage limits or hosted readiness.
