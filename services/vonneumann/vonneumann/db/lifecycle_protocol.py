"""Validation of the bounded v4 lifecycle envelope, not runtime authority.

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
             config["durability_contract_version"] == 4, "Lifecycle requires contract v4")
    policy = config["rehearsal"]
    _keys(policy, {"profile", "code_version", "source", "strategy", "asset", "initial_cash",
                   "seed_capital", "search_seed", "execution", "population", "horizon_seconds",
                   "candle_seconds", "max_generations", "max_positions", "lifecycle_policy"})
    _require(policy["profile"] == "ema-baseline-exact-lifecycle-v1" and
             policy["code_version"] == "bounded-exact-lifecycle-v1" and
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
    _keys(policy["lifecycle_policy"], {"version", "account_loss_bps", "death_drawdown_bps", "max_lifespan_seconds"})
    from ..core.exact_lifecycle import ExactLifecycleConfig
    expected = ExactLifecycleConfig(policy["strategy"], owner_id, run_id, policy["asset"],
        initial_cash, policy["seed_capital"], policy["search_seed"],
        DecimalExecutionConfig.from_dict(config["execution"]["config"]),
        policy["lifecycle_policy"]["account_loss_bps"]).to_dict()
    _require(_same(policy, expected), "Unsupported lifecycle policy")
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
    _require(value["status"] in {"running", "paused", "risk_halted", "stopped"}, "Unsupported lifecycle state")
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
    validate_configuration({"durability_contract_version": 4, "execution": config.get("execution"),
                            "rehearsal": config}, owner_id, run_id, config.get("initial_cash"))
    _engine(engine, accounts_by_id, positions, run_id)
    _lifecycle_state(value)
    for position in positions:
        _require(position["asset"] == config["asset"] and
                 _same(DecimalExecutionConfig.from_dict(position["entry"]["config"]).policy(),
                       config["execution"]), "Position violates the immutable run policy")


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
    reclaimed = _projection(before, after, operations)
    _evidence(transition, operations)
    _continuation(transition, operations, reclaimed)


def _evidence(transition: dict, operations: list[dict]) -> None:
    before, after, evidence, events = (transition[name] for name in ("before", "after", "evidence", "events"))
    _keys(evidence, {"kind", "inputs", "observation", "actions", "control"})
    kind, inputs, observation, actions = (evidence[name] for name in ("kind", "inputs", "observation", "actions"))
    _require(kind in {"bootstrap", "protective", "decision", "control"} and
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
    control = evidence["control"]
    if kind == "control":
        _keys(control, {"action", "trip_id"})
        _require(control["action"] in {"pause", "resume", "stop", "recover"}, "Unknown lifecycle control")
        if control["action"] == "recover":
            canonical_uuid(control["trip_id"])
        else:
            _require(control["trip_id"] is None, "Only recovery identifies a risk trip")
    else:
        _require(control is None, "Control evidence requires a control phase")
    if kind == "bootstrap" or (kind == "control" and control["action"] != "recover"):
        _require(observation is None, "This lifecycle phase cannot import market state")
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
    reasons = {"birth": {"founder", "birth", "restart_birth"}, "open": {"entry_signal"},
               "close": {"exit_signal", "stop_loss", "take_profit", "cohort_liquidation", "death_liquidation", "restart_liquidation"},
               "retire": {"retire", "terminal", "restart_retire"}, "distribution": {"distribution"}, "lifecycle": {"lifecycle", "risk_halt", "pause", "resume", "stop", "recover"}}
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
            _require(event["kind"] in {"evaluation", "evaluation_aborted"} and
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
                   "distribution_id", "used_ids", "last_evaluation", "optimizer", "lifecycle", "cohort"})
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
        _keys(member, {"id", "name", "genome", "cursor", "pending", "num_trades", "peak_equity", "max_drawdown", "terminal"})
        identity = canonical_uuid(member["id"])
        member_ids.append(identity)
        _require(identity in accounts, "Member account is missing")
        terminal = member["terminal"]
        _require(accounts[identity]["retired"] == (terminal is not None), "Member retirement requires terminal evidence")
        if terminal is not None:
            _keys(terminal, {"reason", "at", "cash"})
            _require(terminal["reason"] == "drawdown" and member["pending"] is None, "Invalid terminal policy")
            _timestamp(terminal["at"])
            _amount(terminal["cash"])
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
            _require(ema["last_end"] is not None and member["cursor"] <= ema["last_end"],
                     "Member cursor exceeds shared completed history")
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
    _require(len(set(member_ids)) == 8 and {m["id"] for m in members if m["terminal"] is None} ==
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
    _cohort(engine["cohort"], accounts, positions, run_id, generation)
    _require(engine["cohort"]["member_ids"] == member_ids, "Cohort mirror differs from current ordered members")
    if engine["last_evaluation"] is not None:
        _keys(engine["last_evaluation"], {"cohort", "selection"})
        last = engine["last_evaluation"]
        suffix = last["cohort"]["iteration_id"].removeprefix(run_id + ":")
        _require(suffix.isascii() and suffix.isdigit() and str(int(suffix)) == suffix and
                 int(suffix) <= generation, "Invalid prior evaluation identity")
        _cohort(last["cohort"], accounts, positions, run_id, int(suffix))
        _require((last["cohort"]["phase"] == "aborted" and last["selection"] is None) or
                 (last["cohort"]["phase"] == "completed" and type(last["selection"]) is dict and bool(last["selection"])),
                 "Only completed windows carry optimizer selection")
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


def _float_record(value: object) -> float:
    _keys(value, {"float64"})
    return _hex(value["float64"])




def _cohort(cohort, accounts, positions, run_id, generation):
    from ..core.evaluation import EVALUATION_POLICY
    _keys(cohort, {'policy','iteration_id','phase','member_ids','member_count','completed_count',
        'horizon_seconds','started_at','ends_at','completed_at','abort_reason','evaluations'})
    ids, phase = cohort['member_ids'], cohort['phase']
    _require(_same(cohort['policy'], EVALUATION_POLICY) and cohort['iteration_id'] == f'{run_id}:{generation}'
        and phase in {'warming','evaluating','completed','aborted'}, 'Invalid common evaluation policy')
    _require(type(ids) is list and len(ids) == len(set(ids)) == 8 and
        type(cohort['member_count']) is int and cohort['member_count'] == 8, 'Incomplete cohort membership')
    for identity in ids:
        _require(canonical_uuid(identity) in accounts, 'Cohort member is not a retained account')
    _require(_float_record(cohort['horizon_seconds']) == 3600, 'Changed evaluation horizon')
    start, end, complete = (None if cohort[k] is None else _float_record(cohort[k])
                           for k in ('started_at','ends_at','completed_at'))
    _require((start is None) == (end is None) and (start is None or
        0 <= start <= 2**40 and end == start + 3600), 'Invalid evaluation window')
    _require((phase == 'warming' and start is None and complete is None) or
             (phase == 'evaluating' and start is not None and complete is None) or
             (phase == 'completed' and start is not None and complete is not None and complete >= end) or
             (phase == 'aborted' and complete is not None and complete >= (start or 0)), 'Invalid cohort phase times')
    _require((phase == 'aborted' and type(cohort['abort_reason']) is str and
              cohort['abort_reason'] in {'paused','stopped','risk_halted'}) or
             (phase != 'aborted' and cohort['abort_reason'] is None), 'Invalid evaluation interruption')
    records = cohort['evaluations']
    _require(type(records) is list and len(records) <= 8 and
             (phase not in {'aborted','completed'} or len(records) == 8), 'Missing cohort results')
    recorded_ids = []
    for row in records:
        _keys(row, {'probe_id','evaluation_id','iteration_id','fitness','roi','num_trades','reason',
            'status','cohort_complete','window_started_at','window_ends_at','terminated_at'})
        identity = row['probe_id']; recorded_ids.append(identity)
        _require(identity in ids and row['evaluation_id'] == f'{cohort["iteration_id"]}:{ids.index(identity)}'
            and row['iteration_id'] == cohort['iteration_id'], 'Result differs from its bound cohort slot')
        _require(_same(row['window_started_at'], cohort['started_at']) and
            _same(row['window_ends_at'], cohort['ends_at']), 'Result changed its evaluation window')
        stamp = _float_record(row['terminated_at'])
        _require((start is None or stamp >= start) and stamp <= 2**40, 'Invalid result timestamp')
        _require(type(row['cohort_complete']) is bool and row['cohort_complete'] == (phase == 'completed'),
            'Only a complete window can be optimizer input')
        bounded_integer(row['num_trades'], minimum=0, maximum=64)
        if row['status'] == 'aborted':
            _require(phase == 'aborted' and row['reason'] == cohort['abort_reason'] and
                row['fitness'] is None and row['roi'] is None and row['num_trades'] == 0 and stamp == complete,
                'An interrupted candidate cannot carry an invented score')
        else:
            _require(row['status'] == 'completed' and row['reason'] in {'drawdown','window_complete'}
                and phase != 'warming' and start is not None, 'Invalid terminal result')
            _float_record(row['fitness']); _float_record(row['roi'])
            _require(row['num_trades'] == sum(p['account_id'] == identity and p['closed'] for p in positions),
                'Terminal trade count differs from retained fills')
            if row['reason'] == 'window_complete':
                _require(phase == 'completed' and stamp == complete, 'Premature window completion')
            else:
                _require(accounts[identity]['retired'], 'Drawdown result requires an actually retired account')
    _require(recorded_ids == [i for i in ids if i in recorded_ids] and len(set(recorded_ids)) == len(recorded_ids),
        'Terminal results must retain unique cohort order')
    _require(type(cohort['completed_count']) is int and cohort['completed_count'] ==
        sum(row['status'] == 'completed' for row in records), 'Incorrect completed result count')


def _optimizer_views(evidence):
    """Read primitive audit views only; never construct runtime objects or RNGs."""
    nodes = {}
    def index(value):
        if type(value) is dict:
            if 'node' in value: nodes[value['node']] = value
            for child in value.values(): index(child)
        elif type(value) is list:
            for child in value: index(child)
    index(evidence)
    # A bounded encoded DAG can still have exponentially many expanded paths.
    # Charge every visit, including a repeated ref, before allocating the view.
    remaining = [100000, 1048576]
    def view(value, depth=0):
        remaining[0] -= 1
        remaining[1] -= len(value.encode('utf-8')) + 8 if type(value) is str else 16
        _require(depth <= 96 and min(remaining) >= 0, 'Optimizer audit expansion exceeds its bound')
        if type(value) is list: return [view(item, depth+1) for item in value]
        if type(value) is not dict: return value
        if 'ref' in value: return view(nodes[value['ref']], depth+1)
        kind = value.get('type')
        if kind == 'integer': return int(value['decimal'])
        if kind in {'float','numpy.float64'}: return {'float64': value['hex']}
        if kind in {'tuple','list'}: return [view(item, depth+1) for item in value['items']]
        pairs = (value['entries'] if kind == 'map' else value['fields'].items()
                 if kind == 'object' else ((k,v) for k,v in value.items() if k != 'node'))
        result = {}
        for key,item in pairs:
            view(key, depth+1)  # keys count toward expanded UTF-8 bytes too
            result[key] = view(item, depth+1)
        return result
    return view(evidence['strategy']), view(evidence['cohort'])


def _lifecycle_state(state):
    engine, cfg = state['engine'], state['engine']['config']
    life = engine['lifecycle']
    _keys(life, {'search_epoch','restart_required','signals_after','last_control_at','risk'})
    bounded_integer(life['search_epoch'], minimum=0, maximum=engine['generation'])
    _require(type(life['restart_required']) is bool, 'Restart flag must be explicit')
    for key in ('signals_after','last_control_at'):
        if life[key] is not None: _timestamp(life[key])
    risk = life['risk']
    _keys(risk, {'active','baseline_equity','observed_equity','observed_at','trip_id','tripped_at',
        'trip_equity','recovery_count','last_recovered_at'})
    _require(type(risk['active']) is bool and risk['baseline_equity'] == cfg['initial_cash'],
        'Risk must retain its original account capital baseline')
    _amount(risk['observed_equity']); _timestamp(risk['observed_at'])
    bounded_integer(risk['recovery_count'], minimum=0, maximum=2**40)
    if risk['trip_id'] is None:
        _require(not risk['active'] and risk['tripped_at'] is None and risk['trip_equity'] is None
            and risk['recovery_count'] == 0 and risk['last_recovered_at'] is None, 'Missing trip evidence')
    else:
        _require(canonical_uuid(risk['trip_id']) in engine['used_ids'], 'Trip identity was not allocated')
        _timestamp(risk['tripped_at']); _amount(risk['trip_equity'])
        _require(_below(risk['trip_equity'], cfg), 'Recorded risk trip did not cross the original threshold')
        if risk['last_recovered_at'] is not None: _timestamp(risk['last_recovered_at'])
    _require((not risk['active'] or state['status'] in {'risk_halted','stopped'}) and
        (state['status'] != 'risk_halted' or risk['active']), 'Risk latch disagrees with lifecycle status')
    _require(life['restart_required'] == (engine['cohort']['phase'] == 'aborted'),
        'Interrupted cohort requires a fresh unscored restart')
    _require(not risk['active'] or all(m['pending'] is None or m['pending']['action'] != 'entry'
        for m in engine['members']), 'Risk halt retained an entry intent')
    strategy, cohort = _optimizer_views(engine['optimizer'])
    mirror = engine['cohort']
    for key in ('iteration_id','phase','horizon_seconds','started_at','ends_at','completed_at','abort_reason','member_ids'):
        _require(_same(cohort[key], mirror[key]), 'Cohort mirror differs from actual optimizer evidence')
    results = cohort['_evaluations']
    _require(set(results) == {r['probe_id'] for r in mirror['evaluations']}, 'Optimizer cohort omits terminal evidence')
    if mirror['phase'] == 'evaluating':
        _require({r['probe_id'] for r in mirror['evaluations']} ==
                 {m['id'] for m in engine['members'] if m['terminal'] is not None},
                 'Active cohort must freeze every early terminal member')
    for row in mirror['evaluations']:
        saved = results[row['probe_id']]
        _require(_same({key: saved[key] for key in row}, row), 'Optimizer frozen result differs from cohort mirror')
    _require(strategy['_search_epoch'] == life['search_epoch'], 'Solver search epoch differs from lifecycle')
    for member in engine['members']:
        expected = dict(member['genome'])
        for key,value in expected.items():
            if type(value) is str: expected[key] = {'float64': value}
        _require(_same(cohort['_genomes'][member['id']], expected), 'Optimizer cohort phenotype differs from its member')
        _require(cohort['_evaluation_ids'][member['id']] == f'{mirror["iteration_id"]}:{mirror["member_ids"].index(member["id"])}',
            'Optimizer evaluation identity differs from its slot')


def _below(equity, config):
    return _units(equity, CASH_SCALE) * 10000 <= _units(config['initial_cash'], CASH_SCALE) * (
        10000 - int(config['lifecycle_policy']['account_loss_bps']))


def _equity(reserve, accounts, positions, price):
    from ..core.decimal_execution import mark_value
    amount = _units(reserve, CASH_SCALE) + sum(_units(a['cash'], CASH_SCALE) for a in accounts.values())
    for position in positions.values():
        if not position['closed']:
            _require(price is not None, 'Open holdings require their exact reference quote')
            amount += _units(mark_value(EntryPlan.from_dict(position['entry']), price), CASH_SCALE)
    return _text(amount, CASH_SCALE)


def _projection(before, after, operations):
    """Independent sequential ledger replay, including first risk crossing."""
    cfg = after['engine']['config']
    accounts = {} if before is None else {a['id']:deepcopy(a) for a in before['accounts']}
    positions = {} if before is None else {p['id']:deepcopy(p) for p in before['positions']}
    reserve = cfg['initial_cash'] if before is None else before['reserve']
    status = 'starting' if before is None else before['status']
    quote = after['engine']['last_quote']; price = None if quote is None else quote['price']
    prior_risk = None if before is None else before['engine']['lifecycle']['risk']
    blocked = False if before is None else prior_risk['active']
    crossing = None
    if before is not None and status in {'running','risk_halted'}:
        equity = _equity(reserve,accounts,positions,price)
        if not blocked and _below(equity,cfg): crossing = equity; blocked = True
    terminal_cash = {}
    for op in operations:
        kind = op['kind']
        if kind == 'birth':
            _require(not blocked and status in {'starting','running'} and op['id'] not in accounts
                and op['id'] not in positions and op['cash'] == cfg['seed_capital'], 'Invalid or risk-blocked funding')
            reserve = debit_cash(reserve, op['cash'])
            accounts[op['id']] = {'id':op['id'],'cash':op['cash'],'initial_cash':op['cash'],'retired':False}
        elif kind == 'open':
            account = accounts[op['account_id']]
            _require(not blocked and status == 'running' and not account['retired'] and
                op['id'] not in accounts and op['id'] not in positions and
                not any(p['account_id'] == account['id'] and not p['closed'] for p in positions.values()),
                'Invalid or risk-blocked entry')
            entry = EntryPlan.from_dict(op['execution'])
            _require(entry.budget == _text(_units(account['cash'],CASH_SCALE)//4,CASH_SCALE), 'Wrong entry budget')
            account['cash'] = debit_cash(account['cash'],entry.cash_debit)
            positions[op['id']] = {'id':op['id'],'account_id':account['id'],'asset':op['asset'],
                'entry':entry.to_dict(),'exit':None,'closed':False}
        elif kind == 'close':
            position = positions[op['id']]; account = accounts[position['account_id']]
            plan = ExitPlan.from_dict(op['execution'])
            _require(status in {'running','risk_halted'} and not position['closed'] and
                _same(plan.entry.to_dict(),position['entry']) and plan.kind == 'fill', 'Invalid lifecycle close')
            account['cash'] = credit_cash(account['cash'],plan.cash_credit)
            position.update(closed=True,exit=plan.to_dict())
        elif kind == 'retire':
            account = accounts[op['id']]
            _require(not account['retired'] and not any(p['account_id'] == op['id'] and not p['closed']
                for p in positions.values()), 'Repeated retirement or retained exposure')
            terminal_cash[op['id']] = account['cash']
            reserve = credit_cash(reserve, account['cash']); account.update(cash='0',retired=True)
        elif kind == 'distribution':
            _require(not blocked and status == 'running', 'Risk-blocked optimizer distribution')
        elif kind == 'lifecycle':
            allowed = {'starting':{'running'},'running':{'paused','risk_halted','stopped'},
                'paused':{'running','stopped'},'risk_halted':{'running','stopped'}}
            _require(op['status'] in allowed.get(status,set()), 'Invalid lifecycle transition')
            if op['status'] == 'risk_halted': _require(crossing is not None, 'Unjustified risk halt')
            if status == 'risk_halted' and op['status'] == 'running': blocked = False
            status = op['status']
        else:
            raise CommandValidationError('Unsupported lifecycle operation')
        if kind in {'open','close'}:
            equity = _equity(reserve,accounts,positions,price)
            if not blocked and _below(equity,cfg): crossing = equity; blocked = True
    _require(reserve == after['reserve'] and status == after['status'] and
        _same(sorted(accounts.values(),key=lambda a:a['id']),after['accounts']) and
        _same(sorted(positions.values(),key=lambda p:p['id']),after['positions']), 'Economic projection mismatch')
    risk = after['engine']['lifecycle']['risk']
    _require(risk['observed_equity'] == _equity(reserve,accounts,positions,price), 'Risk equity differs from exact owned assets')
    if crossing is not None:
        _require(risk['active'] and risk['trip_equity'] == crossing and
            (prior_risk is None or risk['trip_id'] != prior_risk['trip_id']), 'First exact threshold crossing was lost')
    for member in after['engine']['members']:
        if member['id'] in terminal_cash and member['terminal'] is not None:
            _require(member['terminal']['cash'] == terminal_cash[member['id']], 'Terminal cash differs from reclaimed capital')
    return terminal_cash


def _continuation(transition, operations, reclaimed):
    before, after, evidence = (transition[k] for k in ('before','after','evidence'))
    nxt = after['engine']; life = nxt['lifecycle']; risk = life['risk']
    kind, obs = evidence['kind'], evidence['observation']
    at = int(datetime.fromisoformat(evidence['inputs']['event_at']).timestamp())
    births = [op for op in operations if op['kind'] == 'birth']
    allocations = [op['id'] for op in operations if op['kind'] in {'birth','open','distribution'}]
    old_ids = [] if before is None else before['engine']['used_ids']
    oldrisk = None if before is None else before['engine']['lifecycle']['risk']
    trip = risk['trip_id'] is not None and (oldrisk is None or risk['trip_id'] != oldrisk['trip_id'])
    if trip: allocations.append(risk['trip_id'])
    fresh = nxt['used_ids'][len(old_ids):]
    _require(nxt['used_ids'][:len(old_ids)] == old_ids and len(fresh) == len(allocations)
        and set(fresh) == set(allocations) and fresh == evidence['inputs']['ids'][:len(fresh)],
        'Allocation history differs from the complete admitted identities')
    members = {m['id']:m for m in nxt['members']}
    _require([[members[op['id']]['genome']['generation'], members[op['id']]['name']] for op in births]
        == evidence['inputs']['names'][:len(births)] and
        all(op['lineage']['strategy'] == nxt['config']['strategy'] for op in births), 'Birth allocation mismatch')
    if before is None:
        _require(nxt['generation'] == life['search_epoch'] == 0 and not life['restart_required']
            and life['signals_after'] is None and life['last_control_at'] is None and not risk['active']
            and risk['trip_id'] is None and risk['observed_at'] == at and not after['positions']
            and nxt['last_quote'] is None and nxt['decision_timestamp'] is None and nxt['ema']['count'] == 0
            and nxt['last_evaluation'] is None and nxt['cohort']['phase'] == 'warming', 'Invalid fresh lifecycle state')
        _require([op['kind'] for op in operations] == ['birth']*8+['lifecycle'] and
            all(op['lineage']['operation'] == 'founder' and op['lineage']['version'] == 1 for op in births)
            and [op['id'] for op in births] == [m['id'] for m in nxt['members']], 'Incomplete bootstrap')
        return
    prior = before['engine']; oldlife = prior['lifecycle']
    _require(before['status'] != 'stopped' and (prior['last_quote'] is None or at >= prior['last_quote']['timestamp'])
        and (oldlife['last_control_at'] is None or at >= oldlife['last_control_at']), 'Lifecycle clock regression')
    quote = None if obs is None else {key:obs[key] for key in ('timestamp','price')}
    _require(nxt['last_quote'] == (prior['last_quote'] if kind == 'control' else quote), 'Lost exact source quote')
    changed = nxt['generation'] != prior['generation']
    _require(nxt['generation'] in {prior['generation'],prior['generation']+1}, 'Invalid generation advance')
    aborted = prior['cohort']['phase'] in {'warming','evaluating'} and nxt['cohort']['phase'] == 'aborted'
    recovered = kind == 'control' and evidence['control']['action'] == 'recover'
    expected_abort = trip or kind == 'control' and evidence['control']['action'] in {'pause','stop'}
    _require(not aborted or expected_abort, 'Cohort interruption lacks its lifecycle cause')
    _require(risk['recovery_count'] == oldrisk['recovery_count'] + int(recovered) and
        risk['last_recovered_at'] == (at if recovered else oldrisk['last_recovered_at']), 'Recovery audit mismatch')
    if trip:
        _require(risk['tripped_at'] == at and not oldrisk['active'] and kind in {'protective','decision'}
            and sum(op['kind'] == 'lifecycle' and op['status'] == 'risk_halted' for op in operations) == 1,
            'Trip transition mismatch')
    else:
        for key in ('trip_id','tripped_at','trip_equity'):
            _require(risk[key] == oldrisk[key], 'Risk trip history changed without a new crossing')
        _require(risk['active'] == (False if recovered else oldrisk['active']), 'Risk latch changed without explicit recovery')
    _require(sum(e['kind'] == 'evaluation_aborted' for e in transition['events']) == int(aborted),
        'Interrupted evaluation event mismatch')
    if aborted:
        _require(nxt['last_evaluation'] == {'cohort':nxt['cohort'],'selection':None}, 'Abort must retain an unscored audit')
        cause = ('risk_halted' if trip else
                 {'pause':'paused', 'stop':'stopped'}[evidence['control']['action']])
        _require(nxt['cohort']['abort_reason'] == cause,
                 'Evaluation interruption reason differs from its actual lifecycle cause')
    elif not changed:
        _require(_same(nxt['last_evaluation'],prior['last_evaluation']), 'Nonselection rewrote evaluation audit')
    if kind == 'control':
        action = evidence['control']['action']
        statuses = {'pause':({'running'},'paused'),'resume':({'paused'},'running'),
            'stop':({'running','paused','risk_halted'},'stopped'),'recover':({'risk_halted'},'running')}
        sources,target = statuses[action]
        _require(before['status'] in sources and after['status'] == target and
            operations == [{'kind':'lifecycle','status':target}] and evidence['actions'][0]['reason'] == action,
            'Control may change only its admitted lifecycle state')
        _require(life['last_control_at'] == at and life['signals_after'] ==
            (at if action in {'resume','recover'} else oldlife['signals_after']), 'Control signal boundary mismatch')
        _require(not changed and life['search_epoch'] == oldlife['search_epoch'] and
            nxt['decision_timestamp'] == prior['decision_timestamp'], 'Control changed ordinary state')
        if action in {'pause','stop'}:
            _require(nxt['cohort']['phase'] == 'aborted', 'Control must abort without selection')
        else:
            _require(_same(nxt['cohort'],prior['cohort']), 'Resume/recovery must preserve aborted audit until fresh restart')
        if recovered:
            _require(evidence['control']['trip_id'] == oldrisk['trip_id'] and oldrisk['active'] and
                quote == prior['last_quote'] and obs['candle_end'] is not None and
                at <= obs['candle_end'] + 900 and nxt['ema']['count'] >= 61 and
                any(m['terminal'] is None for m in prior['members']) and not _below(risk['observed_equity'],nxt['config']),
                'Recovery lacks matching trip, current completed source or surviving equity')
        _require(risk['observed_at'] == (at if recovered else oldrisk['observed_at']), 'Control rewrote risk observation time')
    else:
        _require(before['status'] in {'running','risk_halted'} and
            after['status'] == ('risk_halted' if risk['active'] else 'running'), 'Invalid active lifecycle')
        _require(life['last_control_at'] == oldlife['last_control_at'], 'Market observation invented a control')
        if kind == 'protective':
            _require(obs['candle_end'] is None and (prior['last_quote'] is None or at > prior['last_quote']['timestamp'])
                and nxt['decision_timestamp'] == prior['decision_timestamp'] and not changed
                and all(op['kind'] in {'close','retire','lifecycle'} for op in operations), 'Invalid protective phase')
            required = {p['id'] for p in before['positions'] if not p['closed'] and
                (_units(obs['price'],PRICE_SCALE)*100 <= _units(p['entry']['reference_price'],PRICE_SCALE)*97 or
                 _units(obs['price'],PRICE_SCALE)*100 >= _units(p['entry']['reference_price'],PRICE_SCALE)*107)}
            actual = {a['position_id'] for a in evidence['actions'] if a['reason'] in {'stop_loss','take_profit'}}
            _require(required == actual, 'Protection omitted or invented a stop/take threshold')
        else:
            _require(quote == prior['last_quote'] and nxt['decision_timestamp'] == at and
                (prior['decision_timestamp'] is None or at > prior['decision_timestamp']), 'Decision lacks its unconsumed protection')
        _require(risk['observed_at'] in {oldrisk['observed_at'],at}, 'Invalid risk observation time')
    if (kind == 'decision' and prior['cohort']['phase'] == 'evaluating' and
            at >= _float_record(prior['cohort']['ends_at'])):
        _require(changed or trip and aborted,
                 'Due evaluation must complete replacement or acknowledge its actual risk abort')
        _require(not any(action['reason'] in {'entry_signal','exit_signal'} for action in evidence['actions']),
                 'Deadline evaluation cannot consume ordinary signal fills')
    # Independently recompute the shared indicator continuation, except halted
    # decisions deliberately do not depend on a candle provider.
    expected_ema = deepcopy(prior['ema'])
    process_candle = (kind == 'decision' and not oldrisk['active']) or recovered
    if process_candle:
        from ..core.exact_rehearsal import _append_candle, ExactObservation
        _append_candle({'ema':expected_ema}, ExactObservation(**obs))
    _require(_same(nxt['ema'],expected_ema), 'Indicator history was skipped, revised or invented')
    restart = changed and oldlife['restart_required']
    _require(life['search_epoch'] == oldlife['search_epoch'] + int(restart), 'Search epoch changed outside unscored restart')
    if kind != 'control' and not restart:
        _require(life['signals_after'] == oldlife['signals_after'], 'Market phase changed its signal reset boundary')
    ready = (nxt['ema']['count'] >= 61 and nxt['ema']['last_end'] is not None and
             nxt['ema']['last_end'] <= at <= nxt['ema']['last_end'] + 900)
    if changed:
        _require(kind == 'decision' and not risk['active'] and len(births) == 8 and
            [op['id'] for op in births] == [m['id'] for m in nxt['members']] and
            [op['id'] for op in operations if op['kind'] == 'retire'] ==
                [m['id'] for m in prior['members'] if m['terminal'] is None], 'Replacement lost the original complete cohort')
        if restart:
            _require(prior['cohort']['phase'] == 'aborted' and oldlife['signals_after'] is not None
                and at > oldlife['signals_after'] and nxt['cohort']['phase'] == 'warming'
                and not life['restart_required'] and life['signals_after'] == at
                and ready and _same(nxt['last_evaluation'],prior['last_evaluation']) and nxt['distribution_id'] is None,
                'Restart must fund a fresh unscored search epoch')
            for index,(source,member,op) in enumerate(zip(prior['members'],nxt['members'],births)):
                lineage = op['lineage']
                expected = deepcopy(source['genome']); expected.update(generation=nxt['generation'],parent_ids=[source['id']])
                _require(lineage['version'] == 2 and lineage['operation'] == 'restart_clone' and
                    lineage['source_iteration_id'] == prior['cohort']['iteration_id'] and
                    lineage['offspring_index'] == index and
                    [s['source_id'] for s in lineage['sources']] == [source['id'],source['id']] and
                    _same(member['genome'],expected), 'Restart changed its bound interrupted phenotype or ancestry')
        else:
            saved = nxt['last_evaluation']['cohort']
            _require(prior['cohort']['phase'] == 'evaluating' and saved['phase'] == 'completed' and
                saved['member_ids'] == prior['cohort']['member_ids'] and
                saved['iteration_id'] == prior['cohort']['iteration_id'] and
                _float_record(saved['completed_at']) == at and
                all(op['lineage']['version'] == 1 and op['lineage']['source_iteration_id'] == saved['iteration_id'] for op in births),
                'Selection requires the complete original common window')
            _preserve_terminal_results(prior['cohort'], saved, completed=True)
            _selection_lineage(prior, nxt, births, operations)
            _require(nxt['cohort']['phase'] == ('evaluating' if ready else 'warming'),
                'Following evaluation window requires current complete history')
            if ready:
                _require(_float_record(nxt['cohort']['started_at']) == at,
                    'Following common window began at a different source time')
        for member in nxt['members']:
            _require(member['terminal'] is None and member['pending'] is None and member['num_trades'] == 0
                and member['peak_equity'] == nxt['config']['seed_capital'] and
                member['max_drawdown'] == {'numerator':'0','denominator':'1'}, 'Fresh account inherited interrupted P&L')
    else:
        _require(not births and not any(op['kind'] == 'distribution' for op in operations) and
            [m['id'] for m in prior['members']] == [m['id'] for m in nxt['members']] and
            prior['distribution_id'] == nxt['distribution_id'], 'Nonreplacement changed cohort identities/distribution')
        _preserve_terminal_results(prior['cohort'],nxt['cohort'],completed=False)
        _member_continuation(before, after, evidence, operations, at)
        if aborted:
            oldstrategy,_ = _optimizer_views(prior['optimizer'])
            newstrategy,_ = _optimizer_views(nxt['optimizer'])
            oldstrategy = _aborted_strategy(oldstrategy, nxt['config']['strategy'])
            _require(_same(oldstrategy,newstrategy), 'Nonselection changed optimizer or random state')
        else:
            # The strategy is encoded before the evaluation cohort. Ordinary
            # cohort changes therefore cannot renumber its graph. Comparing
            # primitive map views would erase insertion order and aliases.
            _require(_same(prior['optimizer']['strategy'],nxt['optimizer']['strategy']),
                     'Nonselection changed encoded strategy continuation')
        started = prior['cohort']['phase'] == 'warming' and nxt['cohort']['phase'] == 'evaluating'
        _require(not started or kind == 'decision' and ready and not risk['active'] and
            _float_record(nxt['cohort']['started_at']) == at, 'Evaluation started without current complete history')
        if not started and not aborted:
            for key in ('phase','started_at','ends_at','completed_at','abort_reason'):
                _require(_same(prior['cohort'][key],nxt['cohort'][key]), 'Noncompletion changed evaluation phase or deadline')
    _require(sum(e['kind'] == 'evaluation' for e in transition['events']) == int(changed and not restart),
        'Optimizer event does not match a completed selection')
    _new_result_scores(before, after, reclaimed, changed and not restart)
    for action in evidence['actions']:
        if action['reason'] in {'entry_signal','exit_signal'}:
            member = next(m for m in prior['members'] if m['id'] == action['account_id'])
            pending = member['pending']
            _require(type(pending) is dict and pending['signal_at'] == action['signal_at'] and
                pending['action'] == ('entry' if action['reason'] == 'entry_signal' else 'exit') and
                at <= member['cursor']+900 and
                (pending['action'] == 'entry' or pending['position_id'] == action['position_id']), 'Fill consumed a missing/expired signal')
            if action['reason'] == 'entry_signal':
                _require(not oldrisk['active'] and not oldlife['restart_required'] and
                    (oldlife['signals_after'] is None or action['signal_at'] > oldlife['signals_after']),
                    'Entry reused an interrupted signal')


def _preserve_terminal_results(before, after, *, completed):
    recorded = {r['probe_id']:r for r in after['evaluations']}
    for result in before['evaluations']:
        expected = deepcopy(result)
        if completed: expected['cohort_complete'] = True
        _require(result['probe_id'] in recorded and _same(expected,recorded[result['probe_id']]),
            'Frozen terminal/aborted result was rewritten')


def _selection_lineage(prior, following, births, operations):
    """Bind asserted ancestry to this full cohort, without proving solver math."""
    source_ids = prior['cohort']['member_ids']
    iteration = prior['cohort']['iteration_id']
    distributions = [op for op in operations if op['kind'] == 'distribution']
    cma = following['config']['strategy'] == 'cma_es'
    if cma:
        _require(len(distributions) == 1, 'CMA replacement requires one complete distribution')
        distribution = distributions[0]
        _require(distribution['source_ids'] == source_ids and
                 distribution['source_iteration_id'] == iteration and
                 distribution['previous_distribution_id'] == prior['distribution_id'] and
                 distribution['stage'] == ('bootstrap' if prior['distribution_id'] is None else 'update') and
                 following['distribution_id'] == distribution['id'],
                 'CMA distribution differs from its complete ordered cohort or preceding distribution')
    else:
        _require(not distributions, 'Only CMA selection can advance a distribution')
    for index, (member, op) in enumerate(zip(following['members'], births)):
        lineage = op['lineage']
        _require(lineage['offspring_index'] == index and
                 all(source['source_id'] in source_ids for source in lineage['sources']),
                 'Selection ancestry differs from its offspring slot or current cohort')
        if cma:
            _require(lineage['operation'] == 'distribution_sample' and
                     lineage['distribution_id'] == distribution['id'],
                     'CMA offspring is not bound to its actual distribution')
            parents = source_ids
        else:
            parents = [source['source_id'] for source in lineage['sources'] if source['role'] != 'asset_template']
        _require(member['genome']['parent_ids'] == parents,
                 'Flat parent identities contradict the authoritative ordered lineage roles')


def _new_result_scores(before, after, reclaimed, completed):
    """Bind new binary64 fitness views to exact terminal economics, not a solver."""
    from fractions import Fraction
    from ..core.decimal_execution import mark_value
    from ..core.evolution import compute_fitness
    old = before['engine']['cohort']
    current = (after['engine']['last_evaluation']['cohort'] if completed
               else after['engine']['cohort'])
    frozen = {row['probe_id'] for row in old['evaluations']}
    members = {m['id']:m for m in before['engine']['members']}
    accounts = {a['id']:a for a in before['accounts']}
    price = after['engine']['last_quote']['price'] if after['engine']['last_quote'] else None
    for row in current['evaluations']:
        if row['status'] != 'completed' or row['probe_id'] in frozen:
            continue
        _require(row['reason'] == ('window_complete' if completed else 'drawdown') and
                 _float_record(row['terminated_at']) == after['engine']['last_quote']['timestamp'],
                 'New terminal result differs from its actual completion reason or source time')
        identity = row['probe_id']; member = members[identity]
        _require(identity in reclaimed, 'New terminal score lacks a reclaimed exact account')
        cash = _units(reclaimed[identity],CASH_SCALE)
        initial = _units(accounts[identity]['cash'],CASH_SCALE)
        for position in before['positions']:
            if position['account_id'] == identity and not position['closed']:
                initial += _units(mark_value(EntryPlan.from_dict(position['entry']),price),CASH_SCALE)
        peak = max(_units(member['peak_equity'],CASH_SCALE),initial,cash)
        ratio = member['max_drawdown']
        drawdown = max(Fraction(int(ratio['numerator']),int(ratio['denominator'])),
                       Fraction(peak-initial,peak),Fraction(peak-cash,peak))
        seed = _units(accounts[identity]['initial_cash'],CASH_SCALE)
        roi = float(Fraction(cash-seed,seed))
        expected = compute_fitness(roi,float(drawdown))
        _require(row['roi'] == {'float64':roi.hex()} and
            row['fitness'] == {'float64':expected.hex()}, 'Terminal score differs from exact account economics')


def _aborted_strategy(value, strategy):
    value = deepcopy(value)
    if strategy == 'cma_es':
        value.update(_optimizer=None,_codec=None,_gene_names=[],_first_generation=True,
            _pending_vectors=None,_pending_genomes=None,_bound_ids=[],_bound_genomes={},_awaiting_bind=False)
    else:
        value['_cohort'].update(population_size=0,bound_ids=[],_signatures={},_pending=None,
            _previous_ids=[],_previous_context=None,_bootstrap=False)
        if strategy == 'differential_evolution': value.update(_phase='uninitialized',_pairs=[])
        if strategy == 'particle_swarm': value.update(_codec=None,_velocities={},_personal_best={},_global_best=None)
    return value


def _member_continuation(before, after, evidence, operations, at):
    from fractions import Fraction
    from ..core.decimal_execution import mark_value
    quote = after['engine']['last_quote']
    price = None if quote is None else quote['price']
    after_accounts = {a['id']:a for a in after['accounts']}
    before_accounts = {a['id']:a for a in before['accounts']}
    terminations = {a['account_id'] for a in evidence['actions'] if a['reason'] == 'terminal'}
    for old,new in zip(before['engine']['members'],after['engine']['members']):
        for key in ('id','name','genome'):
            _require(_same(old[key],new[key]), 'Member identity/phenotype changed midwindow')
        if old['terminal'] is not None:
            _require(_same(old,new), 'Frozen terminal member changed')
            continue
        if evidence['kind'] == 'control':
            for key in ('terminal','peak_equity','max_drawdown','num_trades','cursor'):
                _require(_same(old[key],new[key]), 'Control changed account evaluation evidence')
            _require(new['pending'] is None, 'Control retained an interrupted signal')
            continue
        def marked(accounts, positions, terminal=None):
            cash = accounts[old['id']]['cash'] if terminal is None else terminal['cash']
            total = _units(cash,CASH_SCALE)
            for p in positions:
                if p['account_id'] == old['id'] and not p['closed']:
                    total += _units(mark_value(EntryPlan.from_dict(p['entry']),price),CASH_SCALE)
            return total
        initial = marked(before_accounts,before['positions'])
        final = marked(after_accounts,after['positions'],new['terminal'])
        peak = max(_units(old['peak_equity'],CASH_SCALE),initial,final)
        drawdown = max(Fraction(int(old['max_drawdown']['numerator']),int(old['max_drawdown']['denominator'])),
            Fraction(peak-initial,peak),Fraction(peak-final,peak))
        # A decision with no member operation uses the already accepted quote;
        # protective preparation has already accounted for its peak/drawdown.
        _require(new['peak_equity'] == _text(peak,CASH_SCALE) and new['max_drawdown'] ==
            {'numerator':str(drawdown.numerator),'denominator':str(drawdown.denominator)}, 'Exact member risk metric mismatch')
        if new['terminal'] is not None:
            _require(new['id'] in terminations and new['terminal']['at'] == at and
                min(initial,final)*10000 <= peak*8000, 'Unjustified early drawdown retirement')
        else:
            _require(new['id'] not in terminations and min(initial,final)*10000 > peak*8000,
                     'Drawdown death was omitted or lost its terminal metadata')
        if evidence['kind'] == 'protective':
            _require(new['cursor'] == old['cursor'], 'Protection changed the ordinary signal cursor')
            expected = deepcopy(old['pending'])
            closed = any(a['account_id'] == old['id'] and a['position_id'] is not None
                         for a in evidence['actions'])
            if (closed or new['terminal'] is not None or
                    after['engine']['lifecycle']['risk']['active'] and expected is not None
                    and expected['action'] == 'entry'):
                expected = None
            _require(_same(new['pending'],expected), 'Protection changed an unrelated pending signal')
