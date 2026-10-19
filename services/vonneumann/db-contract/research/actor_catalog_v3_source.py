"""Inert B1 source loader; it never connects, installs, or accepts a native catalog.

The expected digest is an independently held bootstrap input, not authentication
conferred by this Python function. Reviewed source is deliberately a closed,
small DDL format rather than arbitrary SQL accepted by a general parser.
"""
from dataclasses import dataclass
import hashlib
import json
import re


NAMESPACE = "vn_jupiter_actor_catalog_research_v3"
ANCHOR = "vn_jupiter_b1_fixture_anchor"
OWNER = "vn_jupiter_b1_sealed_owner"
ACTORS = tuple(f"vn_jupiter_b1_{scope}_{profile}" for scope in ("a", "b")
               for profile in ("recorder", "reader", "sealer", "control"))
HEX = re.compile(r"[0-9a-f]{64}\Z")
LOCAL_SETTINGS = (
    "DateStyle=ISO, YMD", "IntervalStyle=postgres", "TimeZone=UTC",
    "client_encoding=UTF8", "row_security=on", "search_path=pg_catalog, pg_temp",
    "standard_conforming_strings=on",
)
FUNCTIONS = {
    "_c14n": (("v", "jsonb"),),
    "_binding_core": (), "_role_closure": (), "_installation_preimage": (),
    "_catalog_preimage": (),
    "_checked_actor": (("p_owner", "text"), ("p_run", "text"),
                       ("p_market", "text"), ("p_capability", "text")),
    "verify_scoped_actor": (("owner_id", "text"), ("run_id", "text"),
                            ("market_epoch", "text"), ("required_capability", "text")),
    "get_scoped_binding": (("owner_id", "text"), ("run_id", "text"),
                           ("market_epoch", "text"), ("requested_binding_id", "text")),
}
TABLES = (
    (ANCHOR, "installer_reference"), (ANCHOR, "expected_functions"),
    (NAMESPACE, "actor_bindings"), (NAMESPACE, "accepted_pins"),
)


class SourceRefusal(ValueError):
    """Fixed diagnostic; no rejected original source or paths are copied out."""


@dataclass(frozen=True)
class ReviewedSource:
    package_sha256: str
    policy_sha256: str
    functions_json: str
    tables_json: str
    installer_sql: str
    anchor_sql: str

    def functions(self):
        return json.loads(self.functions_json)

    def tables(self):
        return json.loads(self.tables_json)


def _refuse():
    raise SourceRefusal("b1_source_refused") from None


def function_header(name):
    """Exact allowed header built independently from this closed declaration map."""
    args = ", ".join(f"{arg} pg_catalog.{typ}" for arg, typ in FUNCTIONS[name])
    output = "text" if name == "_c14n" else "jsonb"
    mode = "DEFINER" if name in ("verify_scoped_actor", "get_scoped_binding") else "INVOKER"
    volatility = "IMMUTABLE" if name == "_c14n" else "VOLATILE"
    return (
        f"CREATE FUNCTION {NAMESPACE}.{name}({args})\n"
        f"RETURNS pg_catalog.{output}\nLANGUAGE plpgsql {volatility} SECURITY {mode}\n"
        "CALLED ON NULL INPUT PARALLEL UNSAFE COST 100\n"
        "SET DateStyle = 'ISO, YMD'\nSET IntervalStyle = 'postgres'\n"
        "SET TimeZone = 'UTC'\nSET client_encoding = 'UTF8'\nSET row_security = 'on'\n"
        "SET search_path = 'pg_catalog', 'pg_temp'\n"
        "SET standard_conforming_strings = 'on'\nAS $b1$"
    )


def extract_source(raw, *, expected_package_sha256, expected_policy_sha256):
    """Derive exact body/header/table expectations from held source, not pg_proc.

    This validates source shape and hashes only. Native constructor comparison,
    roles, ownership/ACL checks and independent bootstrap acceptance are separate.
    No resulting value is an installed-function or database authentication proof.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 262144:
        _refuse()
    if (type(expected_package_sha256) is not str or not HEX.fullmatch(expected_package_sha256)
            or type(expected_policy_sha256) is not str or not HEX.fullmatch(expected_policy_sha256)):
        _refuse()
    if hashlib.sha256(raw).hexdigest() != expected_package_sha256:
        _refuse()
    try:
        source = raw.decode("utf-8", "strict")
    except UnicodeError:
        _refuse()
    if "\x00" in source or "\r" in source:
        _refuse()
    prefix = (
        "-- B1 actor/catalog-only research; no source/native/model/trading authority.\n"
        f"-- policy-sha256: {expected_policy_sha256}\n"
        "-- Execute only split source-bound sections after owned-fixture review.\n"
    )
    if not source.startswith(prefix):
        _refuse()
    remaining = source[len(prefix):]
    table_rows = []
    anchor_parts, installer_parts = [], []
    for namespace, name in TABLES:
        marker = f"-- TABLE {namespace}.{name}\n"
        start = f"CREATE TABLE {namespace}.{name} (\n"
        if not remaining.startswith(marker + start):
            _refuse()
        end = remaining.find("\n);\n\n", len(marker + start))
        if end < 0:
            _refuse()
        ddl = remaining[len(marker):end + 4]
        body = ddl[len(start):-3]
        # These closed bodies declare columns/constraints only; never additional
        # statement, comment, function, string delimiter or constructor command.
        if any(token in body for token in (";", "--", "/*", "*/", "$b1$", "\\")):
            _refuse()
        table_rows.append({"namespace": namespace, "name": name, "ddl": ddl,
                           "body_sha256": hashlib.sha256(body.encode()).hexdigest()})
        (anchor_parts if namespace == ANCHOR else installer_parts).append(ddl)
        remaining = remaining[end + 5:]
    specs = []
    for name in FUNCTIONS:
        marker = f"-- FUNCTION {name}\n"
        header = function_header(name)
        if not remaining.startswith(marker + header):
            _refuse()
        end = remaining.find("$b1$;\n\n", len(marker + header))
        if end < 0:
            _refuse()
        body = remaining[len(marker + header):end]
        if not body.startswith("\n") or not body.endswith("\n") or not body.strip():
            _refuse()
        # Inner comments are allowed in reviewed function bodies. The fixed
        # delimiter and held whole-package digest prevent hidden outer DDL.
        ddl = remaining[len(marker):end + len("$b1$;")]
        args = FUNCTIONS[name]
        output = "text" if name == "_c14n" else "jsonb"
        public = name in ("verify_scoped_actor", "get_scoped_binding")
        signature = f"{NAMESPACE}.{name}({','.join('pg_catalog.' + t for _, t in args)})"
        spec = {
            "signature": signature, "argument_type_names": ["pg_catalog." + t for _, t in args],
            "argument_names": [a for a, _ in args] or None, "return_type_name": "pg_catalog." + output,
            "language": "plpgsql", "kind": "f", "owner_role_name": OWNER,
            "security_definer": public, "volatility": "i" if name == "_c14n" else "v",
            "parallel": "u", "strict": False, "leakproof": False, "returns_set": False,
            "cost_text": "100", "rows_text": "0", "support_oid_text": "0",
            "variadic_oid_text": "0", "default_argument_count_text": "0",
            "all_argument_types": None, "argument_modes": None, "transform_types": None,
            "binary": None, "sql_body": None, "local_settings": list(LOCAL_SETTINGS),
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "source_package_sha256": expected_package_sha256,
            "execute_role_names": sorted((OWNER, *ACTORS) if public else (OWNER,)),
        }
        specs.append({"signature": signature, "spec": spec})
        installer_parts.append(ddl)
        remaining = remaining[end + len("$b1$;\n\n"):]
    expected_revoke = "".join(
        f"REVOKE ALL ON FUNCTION {NAMESPACE}.{name}({','.join('pg_catalog.' + t for _, t in args)}) FROM PUBLIC;\n"
        for name, args in FUNCTIONS.items()
    )
    if remaining != expected_revoke:
        _refuse()
    installer_parts.append(expected_revoke)
    return ReviewedSource(
        expected_package_sha256, expected_policy_sha256,
        json.dumps(sorted(specs, key=lambda x: x["signature"]), sort_keys=True, separators=(",", ":")),
        json.dumps(table_rows, sort_keys=True, separators=(",", ":")),
        "\n\n".join(installer_parts), "\n\n".join(anchor_parts),
    )
