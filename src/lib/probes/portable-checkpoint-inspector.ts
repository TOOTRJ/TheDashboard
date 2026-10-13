/** Inert original-v2 laboratory reader. No API, credentials, model restoration,
 * optimizer decoding, control submission, history reconstruction or authority.
 * Supplied bindings are integrity inputs; this parser cannot authenticate them.
 */
export type PortableDisplayBinding = {
  owner_id: string; run_id: string; revision: string; manifest_sha256: string;
  command_id: string; command_sha256: string; semantic_validator_sha256: string; native_package_sha256: string;
};
export type PortableCheckpointView = {
  owner: string; run: string; revision: string; currentRevision: string; status: string; historical: boolean;
  model: string; assessment: string; profile: string; source: string; asset: 'SOL/USD'; currency: 'USD';
  generation: string; dependencyPins: 13; guardObservedAt: string; reserve: string; initialCash: string;
  sourceEpoch: string; sourceSequence: string; emaCount: string; riskActive: boolean; restartRequired: boolean;
  accounts: { id: string; name: string; cash: string; initialCash: string; fastPeriod: number; slowPeriod: number;
    trades: string; pending: boolean; terminal: boolean }[];
  holdings: { id: string; accountId: string; asset: 'SOL/USD'; quantity: string; referencePrice: string; cashDebit: string }[];
  restorationAuthority: false; hostedAuthority: false; runningAuthority: false;
};
const FORMAT = 'ga-portable-native-checkpoint-readback-lab-v1';
const MODEL = 'ga-portable-provider-model-research-v2';
const ASSESSMENT = 'ga-portable-provider-assessment-research-v2';
const MAX_ENVELOPE = 589824, MAX_MANIFEST = 65536, MAX_COMPONENT = 196608, MAX_AGGREGATE = 262144;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const DIGEST = /^[0-9a-f]{64}$/;
const STATUSES = new Set(['created', 'running', 'paused', 'risk_halted', 'stopped', 'failed']);
const encoder = new TextEncoder();
function refuse(): never { throw new Error('Portable checkpoint is unavailable or incompatible.'); }
function requireValue(condition: unknown): asserts condition { if (!condition) refuse(); }
function object(value: unknown): Record<string, unknown> {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value));
  return value as Record<string, unknown>;
}
function fields(value: unknown, names: string[]): Record<string, unknown> {
  const row = object(value); const keys = Object.keys(row);
  requireValue(keys.length === names.length && names.every(name => Object.hasOwn(row, name)));
  return row;
}
function uuid(value: unknown): string { requireValue(typeof value === 'string' && UUID.test(value)); return value; }
function digest(value: unknown): string { requireValue(typeof value === 'string' && DIGEST.test(value)); return value; }
function decimalCounter(value: unknown, minimum = BigInt(1), maximum = BigInt('9223372036854775807')): string {
  requireValue(typeof value === 'string' && /^(0|[1-9]\d{0,18})$/.test(value));
  requireValue(BigInt(value) >= minimum && BigInt(value) <= maximum); return value;
}
function taggedInteger(value: unknown, maximum = BigInt('9223372036854775807')): string {
  return decimalCounter(fields(value, ['$integer']).$integer, BigInt(0), maximum);
}
function amount(value: unknown, places = 36): string {
  requireValue(typeof value === 'string' && /^(0|[1-9]\d{0,12})(\.\d{1,36})?$/.test(value)
    && (value.split('.')[1]?.length ?? 0) <= places); return value;
}
function period(value: unknown, minimum: number, maximum: number): number {
  requireValue(typeof value === 'string');
  const match = /^0x1\.([0-9a-f]{13})p\+([0-9]{1,2})$/.exec(value);
  requireValue(match !== null);
  const decoded = (1 + parseInt(match[1], 16) / 16 ** 13) * 2 ** Number(match[2]);
  requireValue(Number.isInteger(decoded) && decoded >= minimum && decoded <= maximum); return decoded;
}
function canonicalFloat(value: unknown) {
  requireValue(typeof value === 'string');
  if (value === '0x0.0p+0' || value === '-0x0.0p+0') return;
  const match = /^-?0x([01])\.([0-9a-f]{13})p([+-](?:0|[1-9]\d{0,3}))$/.exec(value);
  requireValue(match !== null);
  const exponent = Number(match[3]);
  requireValue(exponent >= -1022 && exponent <= 1023 && !(match[3] === '-0')
    && (match[1] === '1' || (exponent === -1022 && match[2] !== '0000000000000')));
}
function unicode(value: string) {
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const following = value.charCodeAt(++index); requireValue(following >= 0xdc00 && following <= 0xdfff);
    } else requireValue(code < 0xdc00 || code > 0xdfff);
  }
}
/** Bounded duplicate-aware parser. Untagged JSON numbers are refused, including
 * integers outside JS's safe range. The native outer schema uses string counters.
 */
function strictJSON(text: string, maximum: number): unknown {
  requireValue(typeof text === 'string' && text.length > 0 && encoder.encode(text).length <= maximum);
  unicode(text); let offset = 0, visits = 0;
  const whitespace = () => { while (' \n\r\t'.includes(text[offset] ?? '\u0000')) offset++; };
  const string = (): string => {
    requireValue(text[offset++] === '"'); const start = offset - 1;
    while (offset < text.length) {
      const char = text[offset++];
      if (char === '\\') { requireValue(offset < text.length); offset++; }
      else if (char === '"') {
        const value: unknown = JSON.parse(text.slice(start, offset));
        requireValue(typeof value === 'string' && !value.includes('\u0000')); unicode(value); return value;
      }
    }
    return refuse();
  };
  function value(depth: number): unknown {
    requireValue(++visits <= 60000 && depth <= 64); whitespace();
    const char = text[offset];
    if (char === '"') return string();
    for (const [word, result] of [['true', true], ['false', false], ['null', null]] as const) {
      if (text.startsWith(word, offset)) { offset += word.length; return result; }
    }
    if (char === '[') {
      offset++; const result: unknown[] = []; whitespace();
      if (text[offset] === ']') { offset++; return result; }
      while (offset < text.length) {
        requireValue(result.length < 4096); result.push(value(depth + 1)); whitespace();
        if (text[offset++] === ']') return result;
        requireValue(text[offset - 1] === ',');
      }
      return refuse();
    }
    requireValue(char === '{'); offset++; const result: Record<string, unknown> = Object.create(null); whitespace();
    if (text[offset] === '}') { offset++; return result; }
    while (offset < text.length) {
      whitespace(); requireValue(Object.keys(result).length < 4096); const key = string();
      requireValue(!Object.hasOwn(result, key)); whitespace(); requireValue(text[offset++] === ':');
      result[key] = value(depth + 1); whitespace();
      if (text[offset++] === '}') return result;
      requireValue(text[offset - 1] === ',');
    }
    return refuse();
  }
  try { const result = value(0); whitespace(); requireValue(offset === text.length); return result; }
  catch { return refuse(); }
}
function compareUnicode(left: string, right: string) {
  const a = [...left], b = [...right];
  for (let index = 0; index < Math.min(a.length, b.length); index++) {
    const difference = a[index].codePointAt(0)! - b[index].codePointAt(0)!; if (difference) return difference;
  }
  return a.length - b.length;
}
function canonical(value: unknown): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  const row = object(value);
  return '{' + Object.keys(row).sort(compareUnicode).map(key => JSON.stringify(key) + ':' + canonical(row[key])).join(',') + '}';
}
function numericWire(text: string, maximum: number): Record<string, unknown> {
  const value = strictJSON(text, maximum); requireValue(canonical(value) === text);
  // Validate numeric tag structure without instantiating an optimizer graph or
  // converting amounts/counters into floating point. Graph bodies stay opaque.
  let visits = 0;
  function visit(item: unknown, depth: number) {
    requireValue(++visits <= 20000 && depth <= 64);
    if (typeof item === 'string') { requireValue(encoder.encode(item).length <= 16384); return; }
    if (item === null || typeof item === 'boolean') return;
    if (Array.isArray(item)) { item.forEach(child => visit(child, depth + 1)); return; }
    const row = object(item), keys = Object.keys(row);
    if (Object.hasOwn(row, '$integer')) {
      requireValue(keys.length === 1 && typeof row.$integer === 'string' && /^(0|-?[1-9]\d{0,77})$/.test(row.$integer));
      requireValue((BigInt(row.$integer) < BigInt(0) ? -BigInt(row.$integer) : BigInt(row.$integer)) < BigInt(2) ** BigInt(256));
    } else if (Object.hasOwn(row, '$float64')) {
      requireValue(keys.length === 1); canonicalFloat(row.$float64);
    } else for (const key of keys) { visit(key, depth + 1); visit(row[key], depth + 1); }
  }
  visit(value, 0); return object(value);
}
async function sha(text: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', encoder.encode(text));
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
}
function bindingFields(binding: PortableDisplayBinding, owner: string) {
  const expected = fields(binding, ['owner_id', 'run_id', 'revision', 'manifest_sha256', 'command_id',
    'command_sha256', 'semantic_validator_sha256', 'native_package_sha256']);
  requireValue(uuid(expected.owner_id) === uuid(owner)); uuid(expected.run_id); uuid(expected.command_id);
  decimalCounter(expected.revision, BigInt(2));
  for (const key of ['manifest_sha256', 'command_sha256', 'semantic_validator_sha256', 'native_package_sha256']) digest(expected[key]);
}

export async function inspectPortableCheckpoint(text: string, binding: PortableDisplayBinding, owner: string): Promise<PortableCheckpointView> {
  binding = Object.freeze({ ...binding });
  bindingFields(binding, owner);
  const outer = fields(strictJSON(text, MAX_ENVELOPE), ['format', 'manifest_wire', 'component_wires', 'receipt',
    'current_revision', 'current_status', 'pending_command_authority', 'restoration_authority', 'hosted_authority']);
  requireValue(outer.format === FORMAT && outer.pending_command_authority === false
    && outer.restoration_authority === false && outer.hosted_authority === false);
  requireValue(typeof outer.manifest_wire === 'string' && Array.isArray(outer.component_wires)
    && outer.component_wires.length === 13 && outer.component_wires.every(item => typeof item === 'string'));
  const componentWires = outer.component_wires as string[];
  requireValue(encoder.encode(outer.manifest_wire).length + componentWires.reduce((sum, item) => sum + encoder.encode(item).length, 0) <= MAX_AGGREGATE);
  requireValue(await sha(outer.manifest_wire) === binding.manifest_sha256);
  const manifest = fields(numericWire(outer.manifest_wire, MAX_MANIFEST), ['format', 'source_model_version', 'owner_id', 'run_id',
    'revision', 'status', 'reserve', 'accounts', 'positions', 'engine', 'source', 'components']);
  requireValue(manifest.format === 'ga-portable-provider-checkpoint-research-v2' && manifest.source_model_version === MODEL
    && manifest.owner_id === owner && manifest.run_id === binding.run_id && taggedInteger(manifest.revision) === binding.revision);
  const currentRevision = decimalCounter(outer.current_revision);
  requireValue(BigInt(currentRevision) >= BigInt(binding.revision) && typeof outer.current_status === 'string' && STATUSES.has(outer.current_status));
  requireValue(typeof manifest.status === 'string' && STATUSES.has(manifest.status)
    && (currentRevision !== binding.revision || outer.current_status === manifest.status));
  const receipt = fields(outer.receipt, ['format', 'owner_id', 'run_id', 'command_id', 'command_sha256', 'revision', 'manifest_sha256',
    'model_format', 'assessment_format', 'semantic_validator_sha256', 'native_package_sha256', 'record_observed', 'pending_until_commit',
    'guard_observed_at', 'final_visible_instant_freshness', 'restoration_authority', 'hosted_authority']);
  requireValue(receipt.format === 'ga-portable-native-receipt-lab-v1' && receipt.model_format === MODEL && receipt.assessment_format === ASSESSMENT
    && receipt.record_observed === true && receipt.pending_until_commit === false && receipt.final_visible_instant_freshness === false
    && receipt.restoration_authority === false && receipt.hosted_authority === false);
  for (const key of Object.keys(binding) as (keyof PortableDisplayBinding)[]) requireValue(receipt[key] === binding[key]);
  requireValue(typeof receipt.guard_observed_at === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$/.test(receipt.guard_observed_at));
  requireValue(Number(receipt.guard_observed_at.slice(0, 4)) >= 1);
  const date = new Date(receipt.guard_observed_at); requireValue(Number.isFinite(date.getTime())
    && date.toISOString().slice(0, 19) === receipt.guard_observed_at.slice(0, 19));
  const engine = fields(manifest.engine, ['generation', 'last_quote', 'decision_timestamp', 'lifecycle', 'cohort_source', 'members']);
  const generation = taggedInteger(engine.generation, BigInt('2147483647'));
  requireValue(Array.isArray(engine.members) && engine.members.length === 8);
  const members = engine.members.map(item => fields(item, ['id', 'name', 'cursor', 'pending', 'num_trades', 'peak_equity', 'max_drawdown', 'terminal', 'assessment']));
  const ids = members.map(member => uuid(member.id)); requireValue(new Set(ids).size === 8);
  const slots: [string, string, string][] = [['configuration', 'configuration', '0'], ['optimizer', 'optimizer', generation], ['cohort', 'cohort', generation],
    ...ids.map(id => ['genome', id, generation] as [string, string, string]), ['source_bars', 'source_bars', '0'], ['ema', 'ema', '0']];
  requireValue(Array.isArray(manifest.components) && manifest.components.length === 13);
  const refs = manifest.components.map(item => fields(item, ['kind', 'entity_id', 'generation', 'sha256']));
  requireValue(new Set(refs.map(ref => digest(ref.sha256))).size === 13);
  const bodies = await Promise.all(componentWires.map(async (raw, index) => {
    requireValue(await sha(raw) === refs[index].sha256);
    const block = fields(numericWire(raw, MAX_COMPONENT), ['format', 'hash_policy', 'owner_id', 'run_id', 'kind', 'entity_id', 'generation', 'body']);
    requireValue(block.format === 'ga-portable-provider-component-research-v2' && block.hash_policy === 'tagged-numeric-json-utf8-sha256-research-v1'
      && block.owner_id === owner && block.run_id === binding.run_id);
    const slot = slots[index]; requireValue(block.kind === slot[0] && block.entity_id === slot[1]
      && taggedInteger(block.generation) === slot[2] && refs[index].kind === slot[0] && refs[index].entity_id === slot[1]
      && taggedInteger(refs[index].generation) === slot[2]);
    return object(block.body);
  }));
  const config = fields(bodies[0], ['assessment_policy', 'asset', 'candle_seconds', 'code_version', 'counter_policy', 'execution', 'horizon_seconds',
    'initial_cash', 'lifecycle_policy', 'max_generations', 'max_positions', 'mutation_policy', 'population', 'profile', 'search_seed', 'seed_capital', 'source', 'source_policy', 'strategy']);
  requireValue(config.profile === 'ema-ga-portable-provider-research-v2' && config.code_version === 'fresh-ga-portable-provider-research-v2'
    && config.assessment_policy === ASSESSMENT && config.source === 'synthetic-exact-fixture-v1' && config.asset === 'SOL/USD'
    && config.strategy === 'genetic_algorithm' && taggedInteger(config.population) === '8'
    && taggedInteger(config.candle_seconds) === '900' && taggedInteger(config.horizon_seconds) === '3600'
    && taggedInteger(config.max_positions) === '8');
  requireValue(object(config.counter_policy).version === 'signed-bigint-reserved-stop-research-v1'
    && object(config.lifecycle_policy).version === 'ga-active-common-cohort-portable-research-v2');
  const mutation = object(config.mutation_policy);
  requireValue(mutation.version === 'ema-period-triangular-integer-v1' && Array.isArray(mutation.genes)
    && mutation.genes.length === 2 && mutation.genes[0] === 'ema_fast' && mutation.genes[1] === 'ema_slow');
  const execution = object(config.execution); requireValue(execution.account_currency === 'USD' && execution.version === 'usd-reference-decimal-v2'
    && execution.cost_assumptions === 'uncalibrated_scenario' && execution.valuation === 'reference_mark');
  const source = fields(manifest.source, ['epoch', 'last_quote', 'quote_sequence', 'version']);
  const policy = object(config.source_policy); requireValue(source.version === 'ga-provider-source-research-v1'
    && policy.version === source.version && policy.epoch === source.epoch && policy.chain === 'solana'
    && policy.denomination === 'USD' && policy.asset === 'SOL/USD' && policy.valuation === 'reference_mark');
  const lifecycle = fields(engine.lifecycle, ['last_control_at', 'restart_required', 'risk', 'search_epoch', 'signals_after']);
  const risk = object(lifecycle.risk); requireValue(typeof risk.active === 'boolean' && typeof lifecycle.restart_required === 'boolean');
  const ema = fields(bodies[12], ['closes', 'count', 'last_end', 'previous', 'values']);
  requireValue(Array.isArray(manifest.accounts) && manifest.accounts.length === 8 && Array.isArray(manifest.positions) && manifest.positions.length <= 8);
  const accounts = manifest.accounts.map(item => fields(item, ['id', 'cash', 'initial_cash', 'retired']));
  const byId = new Map(accounts.map(account => [uuid(account.id), account])); requireValue(byId.size === 8 && ids.every(id => byId.has(id)));
  const displayed = members.map((member, index) => {
    const account = byId.get(ids[index])!; requireValue(account.retired === false && typeof member.name === 'string'
      && encoder.encode(member.name).length <= 128 && member.name.trim() === member.name && member.name.length > 0);
    return { id: ids[index], name: member.name, cash: amount(account.cash), initialCash: amount(account.initial_cash),
      fastPeriod: period(bodies[3 + index].ema_fast, 3, 12), slowPeriod: period(bodies[3 + index].ema_slow, 15, 60),
      trades: taggedInteger(member.num_trades), pending: member.pending !== null, terminal: member.terminal !== null };
  });
  const held = manifest.positions.map(item => {
    const position = fields(item, ['account_id', 'asset', 'closed', 'entry', 'exit', 'id']);
    requireValue(position.asset === 'SOL/USD' && position.closed === false && position.exit === null && byId.has(uuid(position.account_id)));
    const entry = object(position.entry); requireValue(entry.version === 'usd-reference-decimal-v2');
    return { id: uuid(position.id), accountId: uuid(position.account_id), asset: 'SOL/USD' as const,
      quantity: amount(entry.quantity, 18), referencePrice: amount(entry.reference_price, 18), cashDebit: amount(entry.cash_debit) };
  });
  requireValue(new Set(held.map(position => position.id)).size === held.length && new Set(held.map(position => position.accountId)).size === held.length);
  return { owner, run: binding.run_id, revision: binding.revision, currentRevision, status: manifest.status, historical: currentRevision !== binding.revision,
    model: MODEL, assessment: ASSESSMENT, profile: config.profile, source: config.source, asset: 'SOL/USD', currency: 'USD', generation,
    dependencyPins: 13, guardObservedAt: receipt.guard_observed_at, reserve: amount(manifest.reserve), initialCash: amount(config.initial_cash),
    sourceEpoch: uuid(source.epoch), sourceSequence: taggedInteger(source.quote_sequence), emaCount: taggedInteger(ema.count),
    riskActive: risk.active, restartRequired: lifecycle.restart_required, accounts: displayed, holdings: held,
    restorationAuthority: false, hostedAuthority: false, runningAuthority: false };
}
