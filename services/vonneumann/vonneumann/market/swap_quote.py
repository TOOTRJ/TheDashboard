"""Bounded, quote-only Jupiter Swap V2 evidence; never an execution payload.

Contract reviewed against the official V2 OpenAPI on 2026-09-30:
https://developers.jup.ag/docs/openapi-spec/swap/v2/swap.yaml
https://developers.jup.ag/docs/swap/order-and-execute

Amounts are integer atomic token units, not SOL lamports unless the input mint
is SOL. Syntactic public-key validation does not establish token ownership,
decimals, liquidity, or mint safety. No human-unit conversion occurs here.

An order without a taker is an indicative quote. Its receipt timestamps are
local observations, not source block times or freshness guarantees. Its amounts
and threshold are provider-reported estimates, not USD reference marks, fills,
net wallet flows, or a guarantee that a transaction can be built or executed.
Execution would require a separate, explicitly authorized integration and
reconciliation of wallet flows, fees, and transaction outcome.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass

UINT64_MAX = 2**64 - 1
MAX_QUOTE_BYTES = 256 * 1024
QUOTE_TIMEOUT_SECONDS = 5
SWAP_ORDER_URL = "https://api.jup.ag/swap/v2/order"
_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_DIGITS = {char: value for value, char in enumerate(_BASE58)}
_ATOMIC = re.compile(r"(?:0|[1-9][0-9]{0,19})\Z", re.ASCII)
_ERROR_CODES = frozenset({
    "swap_quote_invalid_request", "swap_quote_invalid", "swap_quote_too_large",
    "swap_quote_not_read_only", "swap_quote_provider_rejected",
    "swap_quote_auth_failed", "swap_quote_rate_limited",
    "swap_quote_redirect_rejected", "swap_quote_timeout", "swap_quote_unavailable",
})


class SwapQuoteError(RuntimeError):
    """Only local allowlisted codes/messages; no provider text or request URLs."""

    def __init__(self, code: str):
        self.code = code if code in _ERROR_CODES else "swap_quote_unavailable"
        super().__init__("A validated read-only swap quote is unavailable.")


@dataclass(frozen=True)
class SwapQuote:
    """Small immutable projection that cannot be passed to an execute endpoint."""

    input_mint: str
    output_mint: str
    input_amount_atomic: int
    output_amount_atomic: int
    minimum_output_amount_atomic: int  # May be zero for tiny amounts/high slippage.
    slippage_bps: int
    requested_slippage_bps: int | None
    router: str
    mode: str
    received_at: float
    received_monotonic: float
    response_sha256: str
    provider: str = "jupiter-swap-v2-order"
    semantics: str = "indicative-exact-in-quote-only-v1"


def _valid_mint(value: object) -> bool:
    if not isinstance(value, str) or not 32 <= len(value) <= 44:
        return False
    number = 0
    for char in value:
        digit = _BASE58_DIGITS.get(char)
        if digit is None:
            return False
        number = number * 58 + digit
    # Leading '1' characters encode leading zero bytes; require exactly 32 bytes.
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return leading_zeroes + (number.bit_length() + 7) // 8 == 32


def quote_parameters(input_mint: str, output_mint: str, amount_atomic: int,
                     slippage_bps: int | None) -> dict[str, str]:
    """Validate before HTTP/session creation. No arbitrary query options allowed.

    Omitted slippage preserves Jupiter's managed selection. An explicit override
    opts into manual behavior and may alter routing; it is not a free constraint
    on the same route. None is intentionally distinct from explicit zero.
    """
    if (not _valid_mint(input_mint) or not _valid_mint(output_mint)
            or input_mint == output_mint or type(amount_atomic) is not int
            or not 1 <= amount_atomic <= UINT64_MAX
            or (slippage_bps is not None
                and (type(slippage_bps) is not int or not 0 <= slippage_bps <= 10000))):
        raise SwapQuoteError("swap_quote_invalid_request")
    params = {"inputMint": input_mint, "outputMint": output_mint,
              "amount": str(amount_atomic)}
    if slippage_bps is not None:
        params["slippageBps"] = str(slippage_bps)
    return params


def _atomic(value: object, *, allow_zero: bool = False) -> int:
    if not isinstance(value, str) or not _ATOMIC.fullmatch(value):
        raise SwapQuoteError("swap_quote_invalid")
    parsed = int(value)
    if not (0 if allow_zero else 1) <= parsed <= UINT64_MAX:
        raise SwapQuoteError("swap_quote_invalid")
    return parsed


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Ambiguous JSON")
        result[key] = value
    return result


def _invalid_constant(_: str):
    raise ValueError("Nonfinite JSON")


def parse_swap_quote(body: bytes, *, input_mint: str, output_mint: str,
                     amount_atomic: int, slippage_bps: int | None,
                     received_at: float, received_monotonic: float) -> SwapQuote:
    """Validate only the fields projected into the versioned quote-only model.

    Unknown metadata is discarded, including request IDs, route internals,
    provider error messages, wallet-fee estimates, and execution-related fields.
    A non-null transaction/taker is rejected, never returned or decoded.
    """
    quote_parameters(input_mint, output_mint, amount_atomic, slippage_bps)
    if len(body) > MAX_QUOTE_BYTES:
        raise SwapQuoteError("swap_quote_too_large")
    try:
        data = json.loads(body.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=_invalid_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise SwapQuoteError("swap_quote_invalid") from None
    if not isinstance(data, dict):
        raise SwapQuoteError("swap_quote_invalid")
    if "transaction" not in data:
        raise SwapQuoteError("swap_quote_invalid")
    if data["transaction"] is not None or data.get("taker") is not None:
        raise SwapQuoteError("swap_quote_not_read_only")
    if any(data.get(key) is not None for key in ("error", "errorCode", "errorMessage")):
        raise SwapQuoteError("swap_quote_provider_rejected")
    if (data.get("inputMint") != input_mint or data.get("outputMint") != output_mint
            or data.get("swapMode") != "ExactIn"
            or data.get("router") not in ("metis", "jupiterz", "dflow", "okx")
            or data.get("mode") not in ("ultra", "manual")):
        raise SwapQuoteError("swap_quote_invalid")
    amount_in = _atomic(data.get("inAmount"))
    amount_out = _atomic(data.get("outAmount"))
    threshold = _atomic(data.get("otherAmountThreshold"), allow_zero=True)
    reported_slippage = data.get("slippageBps")
    if (type(reported_slippage) not in (int, float)
            or not 0 <= reported_slippage <= 10000
            or not math.isfinite(reported_slippage)
            or int(reported_slippage) != reported_slippage
            or (slippage_bps is not None and reported_slippage != slippage_bps)
            or amount_in != amount_atomic or threshold > amount_out):
        raise SwapQuoteError("swap_quote_invalid")
    if any(type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0
           for stamp in (received_at, received_monotonic)):
        raise SwapQuoteError("swap_quote_invalid")
    return SwapQuote(input_mint, output_mint, amount_in, amount_out, threshold,
                     int(reported_slippage), slippage_bps, data["router"], data["mode"],
                     received_at, received_monotonic, hashlib.sha256(body).hexdigest())


async def bounded_quote_body(response) -> bytes:
    """Bound decompressed bytes even without Content-Length (or with a lie)."""
    if response.content_length is not None and response.content_length > MAX_QUOTE_BYTES:
        raise SwapQuoteError("swap_quote_too_large")
    body = bytearray()
    async for chunk in response.content.iter_chunked(16 * 1024):
        if len(body) + len(chunk) > MAX_QUOTE_BYTES:
            raise SwapQuoteError("swap_quote_too_large")
        body.extend(chunk)
    return bytes(body)
