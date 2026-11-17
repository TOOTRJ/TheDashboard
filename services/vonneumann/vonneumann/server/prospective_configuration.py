"""Explicit production-only construction for the continuous paper worker."""
from __future__ import annotations
import os
from uuid import uuid4

ORIGIN = 'https://the-dashboard-chi.vercel.app'
SUPABASE = 'https://fxpxsciltakyypunglzr.supabase.co'


def configured_v6_service(environment=None):
    env = os.environ if environment is None else environment
    if env.get('VN_SERVICE_MODE') != 'paper-v6':
        raise RuntimeError('explicit_paper_v6_selection_required')
    if (env.get('PYTHON_DOTENV_DISABLED') != '1' or env.get('VN_ENVIRONMENT') != 'production'
        or env.get('SUPABASE_URL') != SUPABASE or env.get('VN_ALLOWED_ORIGINS') != ORIGIN
        or env.get('VN_JUPITER_SOLE_CONSUMER') != '1'
        or not env.get('SUPABASE_PUBLISHABLE_KEY','').startswith('sb_publishable_')
        or any(env.get(key) for key in ('SUPABASE_SERVICE_ROLE_KEY','SUPABASE_SECRET_KEY',
            'RAILWAY_TOKEN','RAILWAY_API_TOKEN'))):
        raise RuntimeError('explicit_private_paper_configuration_required')
    from ..core.prospective_artifacts import SourceRecipeStore
    from ..db.prospective_journal import ProspectiveSQLJournal
    from ..market.provider_acquisition_v3 import IssuerBinding
    from ..market.provider_recorded_transport_v3 import ProviderRecordedTransport
    from ..research.prospective_ga_v3_policy import V3Config, PaperFillPolicy
    from .prospective_service import ProspectivePaperService
    from .prospective_source_feed import ProspectiveSourceFeed
    try:
        owner, run = env['VN_PAPER_OWNER_ID'], env['VN_PAPER_RUN_ID']
        market, principal = env['VN_PAPER_MARKET_EPOCH_ID'], env['VN_PAPER_PRINCIPAL_BINDING_ID']
        package = env['VN_PAPER_RECORDER_PACKAGE_SHA256']
        binding = IssuerBinding(owner,run,market,str(uuid4()),principal,
            (('jupiter-price-v3',str(uuid4())),('solana-rpc',str(uuid4()))))
        journal = ProspectiveSQLJournal(env['VN_PAPER_DB_LOGIN'],env['VN_PAPER_DB_PASSWORD'],
            env['VN_DATABASE_CA_PEM'].encode('ascii'),owner,run)
        artifacts = SourceRecipeStore(journal,owner,run)
        key, rpc = env['JUPITER_API_KEY'],env['VN_SOLANA_RPC_URL']
        if not key or not rpc:
            raise ValueError()
        async def authorize_request(prepared, family, identity, request_wire):
            # Stop is checked again before each external read. A response that
            # arrives after Stop may be retained, never used to resume trading.
            control = await journal.latest_control()
            if (control is None or control.get('action') != 'start'
                or (control.get('owner_id'),control.get('run_id')) != (owner,run)):
                raise RuntimeError('paper_collection_closed')
        feed = ProspectiveSourceFeed(binding,package,journal,artifacts,
            lambda: ProviderRecordedTransport(key,rpc,read_only_opt_in=True,
                authorize_request=authorize_request),interval_seconds=30)
        policy = PaperFillPolicy(env['VN_PAPER_FEE_BPS'],env['VN_PAPER_HALF_SPREAD_BPS'],
            env['VN_PAPER_SLIPPAGE_BPS'],env['VN_PAPER_COST_LABEL'],
            env['VN_PAPER_COST_EVIDENCE_ID'],env['VN_PAPER_COST_EVIDENCE_SHA256'])
        config = V3Config(owner,run,market,feed.current_binding,policy,
            initial_cash=env['VN_PAPER_INITIAL_CASH'],seed_capital=env['VN_PAPER_SEED_CAPITAL'],
            search_seed=env['VN_PAPER_SEARCH_SEED'])
        # Feed owns wall pacing; five seconds is a lower bound between completed
        # model iterations, not an extra delay when provider work already took30s.
        return ProspectivePaperService(journal,feed,config,interval=5,artifacts=artifacts)
    except Exception:
        raise RuntimeError('invalid_private_paper_configuration') from None
