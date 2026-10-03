"""Validation of the bounded v3 rehearsal envelope, not runtime authority.

The SQL fixture independently binds the prior checkpoint and checks projected
economic rows. Solver evidence records exact binary64 state but PostgreSQL does
not recompute an optimizer. There is deliberately no legacy-state importer.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math

from ..core.decision_inputs import DecisionInputs, DecisionInputError

from ..core.decimal_execution import (
    CASH_SCALE, PRICE_SCALE, DecimalExecutionConfig, DecimalExecutionError,
    EntryPlan, ExitPlan, _text, _units, credit_cash, debit_cash,
)
from .command_protocol import (
    CommandValidationError, _keys, bounded_integer, canonical_json,
    canonical_uuid,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CommandValidationError(message)


def _amount(value: object, scale: int = CASH_SCALE, *, positive: bool = False) -> str:
    try:
        parsed = _units(value, scale, positive=positive)
        _require(_text(parsed, scale) == value, "Rehearsal amounts require canonical decimal spelling")
    except DecimalExecutionError as exc:
        raise CommandValidationError(str(exc)) from None
    return value


def _same(one: object, two: object) -> bool:
    return canonical_json(one) == canonical_json(two)


def validate_configuration(config: dict, owner_id: str, run_id: str, initial_cash: str) -> None:
    """Validate the narrow admitted profile before constructing a create RPC."""
    _keys(config, {"durability_contract_version", "execution", "rehearsal"})
    _require(type(config["durability_contract_version"]) is int and
             config["durability_contract_version"] == 3, "Rehearsal requires contract v3")
    policy = config["rehearsal"]
    _keys(policy, {"profile", "code_version", "source", "strategy", "asset", "initial_cash",
                   "seed_capital", "search_seed", "execution", "population", "horizon_seconds",
                   "candle_seconds", "max_generations", "max_positions"})
    _require(policy["profile"] == "ema-baseline-exact-rehearsal-v1" and
             policy["code_version"] == "bounded-exact-rehearsal-v1" and
             policy["source"] == "synthetic-exact-fixture-v1", "Unsupported rehearsal evidence policy")
    for key, required in {"population": 8, "horizon_seconds": 3600, "candle_seconds": 900,
                           "max_generations": 3, "max_positions": 64}.items():
        _require(type(policy[key]) is int and policy[key] == required,
                 "Configuration exceeds the reviewed rehearsal profile")
    _require(type(policy["asset"]) is str and 1 <= len(policy["asset"]) <= 64,
             "Missing single-asset identity")
    _require(type(policy["search_seed"]) is str and 1 <= len(policy["search_seed"]) <= 20 and
             policy["search_seed"].isascii() and policy["search_seed"].isdigit() and
             str(int(policy["search_seed"])) == policy["search_seed"] and
             int(policy["search_seed"]) < 2**64, "Invalid deterministic search seed")
    _amount(policy["seed_capital"], positive=True)
    _amount(initial_cash, positive=True)
    _require(_units(policy["seed_capital"], CASH_SCALE) >= 10**CASH_SCALE and
             _units(initial_cash, CASH_SCALE) >= 8 * _units(policy["seed_capital"], CASH_SCALE),
             "The fresh run must fund all eight accounts")
    _require(policy.get("initial_cash") == initial_cash and
             _same(policy.get("execution"), config["execution"]),
             "Rehearsal funding/execution configuration mismatch")
    _require(policy.get("population") == 8 and type(policy.get("population")) is int,
             "Only eight-member rehearsals are admitted")
    _require(policy.get("strategy") in {"genetic_algorithm", "differential_evolution",
                                       "particle_swarm", "cma_es"}, "Unsupported rehearsal solver")
    canonical_uuid(owner_id)
    canonical_uuid(run_id)


def _state(value: object, owner_id: str, run_id: str, revision: int) -> None:
    _keys(value, {"version", "owner_id", "run_id", "revision", "status", "reserve",
                  "accounts", "positions", "engine"})
    _require(type(value["version"]) is int and value["version"] == 1,
             "Unsupported exact state schema")
    _require(value["owner_id"] == owner_id and value["run_id"] == run_id,
             "Exact state belongs to another owner/run")
    _require(type(value["revision"]) is int and value["revision"] == revision,
             "Exact state revision mismatch")
    _require(value["status"] == "running", "Bounded rehearsal state must be running")
    _amount(value["reserve"])
    accounts, positions = value["accounts"], value["positions"]
    _require(type(accounts) is list and 8 <= len(accounts) <= 32,
             "Exact account retention bound exceeded")
    _require(type(positions) is list and len(positions) <= 64,
             "Exact position retention bound exceeded")
    identities = []
    for account in accounts:
        _keys(account, {"id", "cash", "initial_cash", "retired"})
        identities.append(canonical_uuid(account["id"]))
        _amount(account["cash"])
        _amount(account["initial_cash"], positive=True)
        _require(type(account["retired"]) is bool, "Retired flag must be a boolean")
        _require(not account["retired"] or account["cash"] == "0", "Retired cash must be zero")
    _require(identities == sorted(set(identities)), "Accounts must have sorted unique identities")
    accounts_by_id = {item["id"]: item for item in accounts}
    position_ids = []
    open_accounts = set()
    for position in positions:
        _keys(position, {"id", "account_id", "asset", "entry", "exit", "closed"})
        position_ids.append(canonical_uuid(position["id"]))
        _require(position["account_id"] in accounts_by_id, "Position has a foreign account")
        _require(type(position["closed"]) is bool, "Closed flag must be a boolean")
        try:
            entry = EntryPlan.from_dict(position["entry"])
            if position["closed"]:
                exit_plan = ExitPlan.from_dict(position["exit"])
                _require(exit_plan.entry == entry and exit_plan.kind == "fill",
                         "Closed position requires its original entry and explicit fill")
            else:
                _require(position["exit"] is None, "Open position cannot contain an exit")
        except DecimalExecutionError as exc:
            raise CommandValidationError(str(exc)) from None
        if not position["closed"]:
            _require(position["account_id"] not in open_accounts and
                     not accounts_by_id[position["account_id"]]["retired"],
                     "A live account permits one open position")
            open_accounts.add(position["account_id"])
    _require(position_ids == sorted(set(position_ids)) and
             not set(position_ids).intersection(identities), "Position identities overlap or repeat")
    engine = value["engine"]
    _require(type(engine) is dict and type(engine.get("config")) is dict,
             "Exact state requires its complete engine configuration")
    config = engine["config"]
    validate_configuration({"durability_contract_version": 3, "execution": config.get("execution"),
                            "rehearsal": config}, owner_id, run_id, config.get("initial_cash"))
    _engine(engine, accounts_by_id, positions, run_id)
    for position in positions:
        _require(position["asset"] == config["asset"] and
                 _same(DecimalExecutionConfig.from_dict(position["entry"]["config"]).policy(),
                       config["execution"]), "Position violates the immutable run policy")


def _projection(before: dict | None, after: dict, operations: list[dict]) -> None:
    """Replay economic operations independently of the planner's state builder."""
    config = after["engine"]["config"]
    accounts = {} if before is None else {a["id"]: deepcopy(a) for a in before["accounts"]}
    positions = {} if before is None else {p["id"]: deepcopy(p) for p in before["positions"]}
    reserve = config["initial_cash"] if before is None else before["reserve"]
    status = "starting" if before is None else before["status"]
    try:
        for op in operations:
            kind = op["kind"]
            if kind == "birth":
                _require(op["id"] not in accounts and op["id"] not in positions,
                         "Birth reuses an economic identity")
                _require(op["cash"] == config["seed_capital"], "Birth capital differs from the fixed run policy")
                reserve = debit_cash(reserve, op["cash"])
                accounts[op["id"]] = {"id": op["id"], "cash": op["cash"],
                                       "initial_cash": op["cash"], "retired": False}
            elif kind == "open":
                account = accounts[op["account_id"]]
                _require(not account["retired"] and op["id"] not in positions and
                         op["id"] not in accounts and status == "running", "Invalid open operation")
                _require(not any(p["account_id"] == account["id"] and not p["closed"]
                                 for p in positions.values()), "Account already has a position")
                entry = EntryPlan.from_dict(op["execution"])
                _require(entry.budget == _text(_units(account["cash"], CASH_SCALE) // 4, CASH_SCALE),
                         "Entry budget must use the fixed quarter-cash policy")
                account["cash"] = debit_cash(account["cash"], entry.cash_debit)
                positions[op["id"]] = {"id": op["id"], "account_id": account["id"],
                    "asset": op["asset"], "entry": entry.to_dict(), "exit": None, "closed": False}
            elif kind == "close":
                position = positions[op["id"]]
                _require(not position["closed"], "Cannot close a retained closed position")
                exit_plan = ExitPlan.from_dict(op["execution"])
                _require(_same(position["entry"], exit_plan.entry.to_dict()) and
                         exit_plan.kind == "fill", "Close changed its entry or lacks a fill")
                account = accounts[position["account_id"]]
                account["cash"] = credit_cash(account["cash"], exit_plan.cash_credit)
                position.update(closed=True, exit=exit_plan.to_dict())
            elif kind == "retire":
                account = accounts[op["id"]]
                _require(not account["retired"] and
                         not any(p["account_id"] == op["id"] and not p["closed"]
                                 for p in positions.values()), "Retirement is incomplete or repeated")
                reserve = credit_cash(reserve, account["cash"])
                account.update(cash="0", retired=True)
            elif kind == "lifecycle":
                _require(status == "starting" and op["status"] == "running",
                         "Only bootstrap lifecycle is supported by this rehearsal")
                status = op["status"]
            elif kind != "distribution":
                raise CommandValidationError("Unsupported rehearsal operation")
    except (KeyError, DecimalExecutionError) as exc:
        raise CommandValidationError("Invalid projected economic transition") from exc
    _require(reserve == after["reserve"] and status == after["status"] and
             _same(sorted(accounts.values(), key=lambda a: a["id"]), after["accounts"]) and
             _same(sorted(positions.values(), key=lambda p: p["id"]), after["positions"]),
             "Candidate economic state differs from its complete operation list")


def validate_transition(transition: object, operations: list[dict], owner_id: str,
                        run_id: str, base_revision: int) -> None:
    _keys(transition, {"version", "before", "after", "evidence", "events"})
    _require(type(transition["version"]) is int and transition["version"] == 1,
             "Unsupported transition schema")
    before, after = transition["before"], transition["after"]
    _state(after, owner_id, run_id, base_revision + 1)
    if before is None:
        _require(base_revision == 1, "Only a fresh run may omit its prior state")
    else:
        _state(before, owner_id, run_id, base_revision)
        _require(_same(before["engine"]["config"], after["engine"]["config"]),
                 "Transition cannot change its immutable engine policy")
    _projection(before, after, operations)
    _evidence(transition, operations)
    _continuation(transition, operations)


def _evidence(transition: dict, operations: list[dict]) -> None:
    before, after, evidence, events = (transition[name] for name in ("before", "after", "evidence", "events"))
    _keys(evidence, {"kind", "inputs", "observation", "actions"})
    kind, inputs, observation, actions = (evidence[name] for name in ("kind", "inputs", "observation", "actions"))
    _require(kind in {"bootstrap", "protective", "decision"} and
             (kind == "bootstrap") == (before is None), "Invalid decision phase")
    _keys(inputs, {"event_at", "wall_at", "monotonic_at", "ids", "names"})
    try:
        _require(type(inputs["ids"]) is list and type(inputs["names"]) is list and
                 all(type(pair) is list for pair in inputs["names"]), "Invalid decision allocation evidence")
        decision = DecisionInputs(datetime.fromisoformat(inputs["event_at"]),
            datetime.fromisoformat(inputs["wall_at"]), float.fromhex(inputs["monotonic_at"]),
            tuple(inputs["ids"]), tuple(tuple(pair) for pair in inputs["names"]))
        _require(decision.event_at.isoformat() == inputs["event_at"] and
                 decision.wall_at.isoformat() == inputs["wall_at"] and
                 decision.monotonic_at.hex() == inputs["monotonic_at"], "Noncanonical decision clocks")
        _require(decision.event_at.timestamp() == int(decision.event_at.timestamp()),
                 "Decision event time must use integer source seconds")
        _timestamp(int(decision.event_at.timestamp()))
    except (TypeError, ValueError, DecisionInputError) as exc:
        raise CommandValidationError("Invalid bounded decision inputs") from exc
    if kind == "bootstrap":
        _require(observation is None, "Bootstrap cannot import market/position state")
    else:
        _keys(observation, {"timestamp", "price", "candle_end", "candle_close"})
        bounded_integer(observation["timestamp"], minimum=0, maximum=2**53 - 1)
        _amount(observation["price"], PRICE_SCALE, positive=True)
        _require((observation["candle_end"] is None) == (observation["candle_close"] is None),
                 "Candle time and exact close must be supplied together")
        if observation["candle_end"] is not None:
            bounded_integer(observation["candle_end"], maximum=2**53 - 1)
            _amount(observation["candle_close"], PRICE_SCALE, positive=True)
            _require(observation["candle_end"] % 900 == 0 and
                     observation["candle_end"] <= observation["timestamp"], "Candle must be complete")
        _require(decision.event_at.timestamp() == observation["timestamp"], "Decision event clock differs from source")
    _require(type(actions) is list and len(actions) == len(operations),
             "Each economic operation requires one causal action")
    positions = {item["id"]: item for item in after["positions"]}
    reasons = {"birth": {"founder", "birth"}, "open": {"entry_signal"},
               "close": {"exit_signal", "stop_loss", "take_profit", "cohort_liquidation"},
               "retire": {"retire"}, "distribution": {"distribution"}, "lifecycle": {"lifecycle"}}
    for index, (action, op) in enumerate(zip(actions, operations)):
        _keys(action, {"operation_index", "reason", "account_id", "position_id", "signal_at", "reference_price"})
        _require(type(action["operation_index"]) is int and action["operation_index"] == index and
                 action["reason"] in reasons[op["kind"]], "Action order/reason differs from its operation")
        for identity in (action["account_id"], action["position_id"]):
            if identity is not None:
                canonical_uuid(identity)
        if op["kind"] in {"open", "close"}:
            position = positions[op["id"]]
            _require(observation is not None and action["account_id"] == position["account_id"] and
                     action["position_id"] == position["id"] and
                     action["reference_price"] == observation["price"] == op["execution"]["reference_price"],
                     "Trade source/account/position evidence mismatch")
            reason = action["reason"]
            if reason in {"entry_signal", "exit_signal"}:
                bounded_integer(action["signal_at"], minimum=0, maximum=2**53 - 1)
                _require(kind == "decision" and action["signal_at"] < observation["timestamp"],
                         "Signal fill requires a later observation")
            else:
                _require(action["signal_at"] is None, "Nonsignal close cannot invent a signal cursor")
            if reason in {"stop_loss", "take_profit"}:
                _require(kind == "protective", "Protective close requires its own transition")
                reference = _units(position["entry"]["reference_price"], PRICE_SCALE)
                observed = _units(observation["price"], PRICE_SCALE)
                _require(observed * 100 <= reference * 97 if reason == "stop_loss" else
                         observed * 100 >= reference * 107, "Protective threshold did not trigger")
            if reason == "cohort_liquidation":
                _require(kind == "decision", "Cohort liquidation requires a full decision")
        else:
            _require(action["position_id"] is None and action["reference_price"] is None and
                     action["signal_at"] is None, "Nontrade action contains price/position evidence")
            _require(action["account_id"] == (op["id"] if op["kind"] in {"birth", "retire"} else None),
                     "Nontrade action belongs to another account")
    _require(type(events) is list and len(actions) <= len(events) <= len(actions) + 8,
             "Invalid bounded event list")
    mirrors = []
    for event in events:
        _keys(event, {"kind", "at", "account_id", "position_id", "operation_index"})
        _require(type(event["at"]) is int and event["at"] == int(decision.event_at.timestamp()),
                 "Event time differs from its decision")
        if event["operation_index"] is None:
            _require(event["kind"] == "evaluation" and kind == "decision" and
                     event["position_id"] is None, "Unbound nonoperation event")
            _require(event["account_id"] is None, "Evaluation event belongs to the complete cohort")
        else:
            bounded_integer(event["operation_index"], minimum=0, maximum=len(actions) - 1)
            action = actions[event["operation_index"]]
            _require(event["kind"] == action["reason"] and event["account_id"] == action["account_id"] and
                     event["position_id"] == action["position_id"], "Event differs from its action")
            mirrors.append(event["operation_index"])
    _require(mirrors == list(range(len(actions))), "Operation events must retain their complete order")


def _hex(value: object, *, positive: bool = False) -> float:
    _require(type(value) is str and len(value) <= 32, "A bounded binary64 hex view is required")
    try:
        result = float.fromhex(value)
    except (ValueError, OverflowError):
        raise CommandValidationError("Invalid binary64 hex view") from None
    _require(math.isfinite(result) and result.hex() == value and (not positive or result > 0),
             "Noncanonical or nonfinite binary64 view")
    return result


def _timestamp(value: object) -> None:
    bounded_integer(value, minimum=0, maximum=2**40)


def _engine(engine: dict, accounts: dict, positions: list, run_id: str) -> None:
    """Shape and cross-field checks for every supported continuation component."""
    from ..core.exact_rehearsal import ExactRehearsalConfig
    from ..core.genome import Genome, NUMERIC_GENES
    from ..core.optimizer_evidence import EVIDENCE_VERSION, OptimizerEvidenceError, validate_optimizer_evidence

    _keys(engine, {"config", "generation", "last_quote", "decision_timestamp", "members", "ema",
                   "distribution_id", "used_ids", "last_evaluation", "optimizer"})
    generation = bounded_integer(engine["generation"], minimum=0, maximum=3)
    cfg = engine["config"]
    config = ExactRehearsalConfig(cfg["strategy"], "00000000-0000-0000-0000-000000000000",
        run_id, cfg["asset"], cfg["initial_cash"], cfg["seed_capital"], cfg["search_seed"],
        DecimalExecutionConfig.from_dict(cfg["execution"]["config"])).colony_config()
    quote = engine["last_quote"]
    if quote is not None:
        _keys(quote, {"timestamp", "price"})
        _timestamp(quote["timestamp"])
        _amount(quote["price"], PRICE_SCALE, positive=True)
    if engine["decision_timestamp"] is not None:
        _timestamp(engine["decision_timestamp"])
        _require(quote is not None and engine["decision_timestamp"] <= quote["timestamp"],
                 "Decision cursor exceeds its observed quote")
    ema = engine["ema"]
    _keys(ema, {"count", "last_end", "closes", "values", "previous"})
    count = bounded_integer(ema["count"], minimum=0, maximum=4096)
    _require(type(ema["closes"]) is list and len(ema["closes"]) == min(64, count),
             "EMA close retention does not match its completed count")
    if count:
        _timestamp(ema["last_end"])
        _require(ema["last_end"] % 900 == 0 and quote is not None and
                 ema["last_end"] <= quote["timestamp"], "EMA source time is incomplete or unaligned")
    else:
        _require(ema["last_end"] is None, "An empty EMA cannot have a completed source cursor")
    for price in ema["closes"]:
        _amount(price, PRICE_SCALE, positive=True)
    for key, completed in (("values", count), ("previous", max(0, count - 1))):
        _require(type(ema[key]) is dict and set(ema[key]) ==
                 {str(period) for period in range(2, min(60, completed) + 1)},
                 "EMA evidence omits or invents a warmed period")
        for value in ema[key].values():
            _hex(value, positive=True)
    members = engine["members"]
    _require(type(members) is list and len(members) == 8, "Complete eight-member cohort required")
    member_ids = []
    for member in members:
        _keys(member, {"id", "name", "genome", "cursor", "pending", "num_trades", "peak_equity", "max_drawdown"})
        identity = canonical_uuid(member["id"])
        member_ids.append(identity)
        _require(identity in accounts and not accounts[identity]["retired"], "Member account is not active")
        name = member["name"]
        _require(type(name) is str and 0 < len(name.encode("utf-8")) <= 128 and
                 name.isprintable() and name == name.strip(), "Invalid member name")
        genome = member["genome"]
        _keys(genome, set(NUMERIC_GENES) | {"assets", "generation", "parent_ids"})
        _require(type(genome["generation"]) is int and genome["generation"] == generation and
                 genome["assets"] == [cfg["asset"]], "Member genome belongs to another cohort/profile")
        _require(type(genome["parent_ids"]) is list and len(genome["parent_ids"]) <= 100 and
                 len(set(genome["parent_ids"])) == len(genome["parent_ids"]), "Invalid parent identities")
        for parent in genome["parent_ids"]:
            _require(canonical_uuid(parent) in accounts and accounts[parent]["retired"],
                     "Parent is not a retained retired source")
        try:
            config.assert_profile_genome(Genome(**{key: _hex(genome[key]) for key in NUMERIC_GENES},
                assets=list(genome["assets"]), generation=generation, parent_ids=list(genome["parent_ids"])))
        except ValueError as exc:
            raise CommandValidationError("Genome violates the fixed two-gene profile") from exc
        bounded_integer(member["num_trades"], minimum=0, maximum=64)
        _require(member["num_trades"] == sum(p["account_id"] == identity and p["closed"] for p in positions),
                 "Member trade count omits retained closed positions")
        _amount(member["peak_equity"], positive=True)
        _keys(member["max_drawdown"], {"numerator", "denominator"})
        ratio = member["max_drawdown"]
        for number in ratio.values():
            _require(type(number) is str and len(number) <= 75 and number.isascii() and
                     number.isdigit() and str(int(number)) == number, "Invalid exact drawdown fraction")
        _require(0 <= int(ratio["numerator"]) <= int(ratio["denominator"]) and
                 int(ratio["denominator"]) > 0, "Invalid drawdown range")
        if member["cursor"] is not None:
            _timestamp(member["cursor"])
            _require(member["cursor"] == ema["last_end"], "Member cursor differs from shared completed history")
        pending = member["pending"]
        if pending is not None:
            _keys(pending, {"action", "signal_at", "position_id"})
            _timestamp(pending["signal_at"])
            _require(pending["action"] in {"entry", "exit"} and member["cursor"] is not None and
                     member["cursor"] <= pending["signal_at"] <= member["cursor"] + 900 and
                     engine["decision_timestamp"] is not None and
                     pending["signal_at"] <= engine["decision_timestamp"], "Pending signal has invalid availability")
            opened = [p for p in positions if p["account_id"] == identity and not p["closed"]]
            _require((pending["action"] == "entry" and pending["position_id"] is None and not opened) or
                     (pending["action"] == "exit" and len(opened) == 1 and pending["position_id"] == opened[0]["id"]),
                     "Pending intent differs from its owned position")
    _require(len(set(member_ids)) == 8 and set(member_ids) ==
             {key for key, account in accounts.items() if not account["retired"]},
             "Cohort must include every active account exactly once")
    used = engine["used_ids"]
    _require(type(used) is list and len(used) <= 100 and len(set(used)) == len(used),
             "Identity allocation history is incomplete or duplicated")
    for identity in used:
        canonical_uuid(identity)
    _require(set(accounts) | {p["id"] for p in positions} <= set(used), "Economic identities are not in allocation history")
    if engine["distribution_id"] is not None:
        _require(canonical_uuid(engine["distribution_id"]) in used and cfg["strategy"] == "cma_es",
                 "Invalid CMA distribution identity")
    _require((engine["last_evaluation"] is None) == (generation == 0), "Missing generation evaluation evidence")
    if engine["last_evaluation"] is not None:
        _keys(engine["last_evaluation"], {"cohort", "selection"})
        _completed_evaluation(engine["last_evaluation"], generation, run_id, accounts, positions)
    optimizer = engine["optimizer"]
    _keys(optimizer, {"version", "software", "strategy", "cohort"})
    _require(optimizer["version"] == EVIDENCE_VERSION, "Unsupported optimizer evidence")
    _keys(optimizer["software"], {"python", "numpy", "cmaes"})
    expected_class = {"genetic_algorithm": "GeneticAlgorithmStrategy", "differential_evolution": "DifferentialEvolutionStrategy",
                      "particle_swarm": "ParticleSwarmStrategy", "cma_es": "CMAEvolutionStrategy"}[cfg["strategy"]]
    _require(type(optimizer["strategy"]) is dict and optimizer["strategy"].get("class") == expected_class and
             type(optimizer["cohort"]) is dict and optimizer["cohort"].get("class") == "EvaluationCohort",
             "Missing full bound optimizer/cohort evidence")
    try:
        validate_optimizer_evidence(optimizer)
    except OptimizerEvidenceError as exc:
        raise CommandValidationError(str(exc)) from None


def _continuation(transition: dict, operations: list[dict]) -> None:
    before, after, evidence = (transition[key] for key in ("before", "after", "evidence"))
    next_engine = after["engine"]
    kind = evidence["kind"]
    new_id_ops = [op["id"] for op in operations if op["kind"] in {"birth", "open", "distribution"}]
    prior_ids = [] if before is None else before["engine"]["used_ids"]
    _require(next_engine["used_ids"][:len(prior_ids)] == prior_ids and
             set(next_engine["used_ids"][len(prior_ids):]) == set(new_id_ops) and
             next_engine["used_ids"][len(prior_ids):] == evidence["inputs"]["ids"][:len(new_id_ops)],
             "Allocated identities do not match the complete economic operations")
    births = [op for op in operations if op["kind"] == "birth"]
    born_members = {member["id"]: member for member in next_engine["members"]}
    expected_names = [[born_members[op["id"]]["genome"]["generation"], born_members[op["id"]]["name"]]
                      for op in births]
    _require(expected_names == evidence["inputs"]["names"][:len(births)] and
             all(op["lineage"]["strategy"] == next_engine["config"]["strategy"] for op in births),
             "Birth name/generation/solver differs from its supplied allocation")
    if before is None:
        _require(next_engine["generation"] == 0 and len(after["accounts"]) == 8 and
                 not after["positions"] and next_engine["last_quote"] is None and
                 next_engine["decision_timestamp"] is None and next_engine["ema"]["count"] == 0,
                 "Bootstrap must start flat with fresh cursors")
        _require([op["kind"] for op in operations] == ["birth"] * 8 + ["lifecycle"],
                 "Bootstrap must fund all founders and enter running status")
        _require(all(action["reason"] == "founder" for action in evidence["actions"][:8]),
                 "Bootstrap births must be founders")
        return
    prior = before["engine"]
    observation = evidence["observation"]
    quote = {key: observation[key] for key in ("timestamp", "price")}
    _require(next_engine["last_quote"] == quote, "Transition lost its exact source quote")
    if kind == "protective":
        _require((prior["last_quote"] is None or quote["timestamp"] > prior["last_quote"]["timestamp"]) and
                 observation["candle_end"] is None, "Protective source must advance before candle processing")
        for key in ("generation", "decision_timestamp", "ema", "distribution_id", "optimizer", "last_evaluation"):
            _require(_same(prior[key], next_engine[key]), "Protection cannot advance ordinary/optimizer state")
        _require(all(op["kind"] == "close" for op in operations), "Protection can only close positions")
        closes = {op["id"] for op in operations}
        observed = _units(quote["price"], PRICE_SCALE)
        required_closes = {position["id"] for position in before["positions"] if not position["closed"] and
            (observed * 100 <= _units(position["entry"]["reference_price"], PRICE_SCALE) * 97 or
             observed * 100 >= _units(position["entry"]["reference_price"], PRICE_SCALE) * 107)}
        _require(closes == required_closes, "Protection must close every and only triggered position")
        _require([m["id"] for m in prior["members"]] == [m["id"] for m in next_engine["members"]],
                 "Protection cannot replace or reorder its cohort")
        closed_accounts = {action["account_id"] for action in evidence["actions"]}
        for previous_member, next_member in zip(prior["members"], next_engine["members"]):
            for key in ("name", "genome", "cursor"):
                _require(_same(previous_member[key], next_member[key]),
                         "Protection cannot change member identity, phenotype or signal cursor")
            expected_pending = None if next_member["id"] in closed_accounts else previous_member["pending"]
            _require(_same(next_member["pending"], expected_pending),
                     "Protection can only clear an intent when it closes the owned position")
    else:
        _require(prior["last_quote"] == quote and next_engine["decision_timestamp"] == quote["timestamp"] and
                 (prior["decision_timestamp"] is None or quote["timestamp"] > prior["decision_timestamp"]),
                 "Ordinary decision must follow its exact unconsumed protective quote")
        _require(prior["generation"] <= next_engine["generation"] <= prior["generation"] + 1,
                 "Generation skipped or moved backward")
        changed_generation = next_engine["generation"] != prior["generation"]
        if not changed_generation:
            _require(_same(prior["optimizer"]["strategy"], next_engine["optimizer"]["strategy"]),
                     "Nonreplacement decisions cannot change optimizer/search state")
            _require(_same(prior["last_evaluation"], next_engine["last_evaluation"]) and
                     prior["distribution_id"] == next_engine["distribution_id"],
                     "Nonreplacement decisions cannot rewrite completed selection evidence")
            _require(_same(prior["optimizer"], next_engine["optimizer"]) or
                     prior["ema"]["count"] < 61 <= next_engine["ema"]["count"],
                     "Ordinary nonreplacement decisions cannot update the optimizer/cohort except warmup start")
            for previous_member, next_member in zip(prior["members"], next_engine["members"]):
                _require(_same(previous_member["genome"], next_member["genome"]) and
                         previous_member["name"] == next_member["name"],
                         "A member cannot change its phenotype/name during evaluation")
        retirees = [op["id"] for op in operations if op["kind"] == "retire"]
        children = [op["id"] for op in operations if op["kind"] == "birth"]
        _require((changed_generation and retirees == [m["id"] for m in prior["members"]] and
                  children == [m["id"] for m in next_engine["members"]]) or
                 (not changed_generation and not retirees and not children and
                  [m["id"] for m in prior["members"]] == [m["id"] for m in next_engine["members"]]),
                 "Replacement must retire and bind the complete ordered cohort")
        _require(sum(event["kind"] == "evaluation" for event in transition["events"]) == int(changed_generation),
                 "Evaluation event must match a complete replacement")
        if changed_generation:
            cohort = next_engine["last_evaluation"]["cohort"]
            _require(cohort["member_ids"] == [member["id"] for member in prior["members"]] and
                     _float_record(cohort["completed_at"]) == quote["timestamp"],
                     "Completed evaluation differs from the retired source cohort/time")
        if observation["candle_end"] is None:
            _require(_same(prior["ema"], next_engine["ema"]), "EMA changed without a completed candle")
        else:
            old_end = prior["ema"]["last_end"]
            duplicate = old_end == observation["candle_end"]
            _require(old_end is None or duplicate or observation["candle_end"] == old_end + 900,
                     "Candle skipped or moved backward")
            _require(next_engine["ema"]["count"] == prior["ema"]["count"] + int(not duplicate) and
                     next_engine["ema"]["last_end"] == observation["candle_end"] and
                     next_engine["ema"]["closes"][-1] == observation["candle_close"],
                     "Completed-candle evidence/cursor mismatch")
            if duplicate:
                _require(_same(prior["ema"], next_engine["ema"]), "Completed candle was revised")
    prior_members = {member["id"]: member for member in prior["members"]}
    for action in evidence["actions"]:
        if action["reason"] in {"entry_signal", "exit_signal"}:
            member = prior_members[action["account_id"]]
            pending = member["pending"]
            _require(type(pending) is dict and pending["signal_at"] == action["signal_at"] and
                     pending["action"] == ("entry" if action["reason"] == "entry_signal" else "exit") and
                     quote["timestamp"] <= member["cursor"] + 900 and
                     (pending["action"] == "entry" or pending["position_id"] == action["position_id"]),
                     "Trade consumes a missing, expired or mismatched pending signal")


def _float_record(value: object) -> float:
    _keys(value, {"float64"})
    return _hex(value["float64"])


def _completed_evaluation(value: dict, generation: int, run_id: str,
                          accounts: dict, positions: list) -> None:
    from ..core.evaluation import EVALUATION_POLICY

    cohort = value["cohort"]
    _keys(cohort, {"policy", "iteration_id", "phase", "member_ids", "member_count", "completed_count",
                   "horizon_seconds", "started_at", "ends_at", "completed_at", "abort_reason", "evaluations"})
    iteration = f"{run_id}:{generation - 1}"
    _require(_same(cohort["policy"], EVALUATION_POLICY) and cohort["iteration_id"] == iteration and
             cohort["phase"] == "completed" and cohort["abort_reason"] is None and
             type(cohort["member_count"]) is int and cohort["member_count"] == 8 and
             type(cohort["completed_count"]) is int and cohort["completed_count"] == 8,
             "A replacement requires the complete common-window evaluation policy")
    _require(type(cohort["member_ids"]) is list and len(cohort["member_ids"]) == 8 and
             len(set(cohort["member_ids"])) == 8 and type(cohort["evaluations"]) is list and
             len(cohort["evaluations"]) == 8, "Incomplete evaluated membership/results")
    for identity in cohort["member_ids"]:
        _require(canonical_uuid(identity) in accounts and accounts[identity]["retired"],
                 "An evaluated member must belong to a retained retired account")
    start, end, completed = (_float_record(cohort[key]) for key in ("started_at", "ends_at", "completed_at"))
    _require(_float_record(cohort["horizon_seconds"]) == 3600 and start >= 0 and
             end == start + 3600 and completed >= end and completed <= 2**40,
             "Evaluation window is incomplete or invalid")
    for index, result in enumerate(cohort["evaluations"]):
        _keys(result, {"probe_id", "evaluation_id", "iteration_id", "fitness", "roi", "num_trades",
                       "reason", "status", "cohort_complete", "window_started_at", "window_ends_at", "terminated_at"})
        identity = cohort["member_ids"][index]
        _require(result["probe_id"] == identity and result["evaluation_id"] == f"{iteration}:{index}" and
                 result["iteration_id"] == iteration and result["reason"] == "window_complete" and
                 result["status"] == "completed" and result["cohort_complete"] is True,
                 "Evaluation result is not bound to its complete ordered cohort")
        _require(_float_record(result["window_started_at"]) == start and
                 _float_record(result["window_ends_at"]) == end and
                 _float_record(result["terminated_at"]) == completed,
                 "Candidate evaluation times disagree with the common window")
        _float_record(result["fitness"])
        _float_record(result["roi"])
        bounded_integer(result["num_trades"], minimum=0, maximum=64)
        _require(result["num_trades"] == sum(p["account_id"] == identity and p["closed"] for p in positions),
                 "Evaluated trade count omits recorded liquidations")
    _require(type(value["selection"]) is dict and bool(value["selection"]),
             "Complete solver selection evidence is required")
