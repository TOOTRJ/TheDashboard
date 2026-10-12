"""Explicit integer-period operator for a separately versioned two-EMA model.

Legacy callers retain Gaussian behavior. This is a pure operator, not a checkpoint
decoder, native admission capability or activation setting.
"""
from __future__ import annotations

from .search_random import SearchRandomStreams

VERSION='ema-period-triangular-integer-v1'
DENOMINATOR=2**53
RATE_SCALE=1_000_000
DOMAINS=(('ema_fast',3,12,3),('ema_slow',15,60,15))


def _counter(value,minimum,maximum):
    if type(value) is not int or not minimum<=value<=maximum:
        raise ValueError('Portable mutation requires bounded plain integer inputs')
    return value


def mutate_periods(fast:int,slow:int,*,seed:str,epoch:int,event:int,child:int,sexual:bool)->dict:
    _counter(fast,3,12);_counter(slow,15,60);_counter(epoch,0,2**31-1)
    _counter(event,0,2**31-1);_counter(child,0,7)
    if type(sexual) is not bool:raise ValueError('Explicit sexual/asexual boolean required')
    rng=SearchRandomStreams(seed,'genetic_algorithm').rng('mutation',epoch,'generation',event,child)
    rate=200_000 if sexual else 300_000
    values=(fast,slow);trace=[];draws=0
    def word():
        nonlocal draws
        draws+=1
        if draws>2048:raise ValueError('Portable mutation draw budget exhausted')
        return rng.getrandbits(32)
    def below(n):
        for _ in range(256):
            value=word()>>(32-n.bit_length())
            if value<n:return value
        raise ValueError('Portable mutation rejection budget exhausted')
    periods=[]
    for original,(name,lo,hi,radius) in zip(values,DOMAINS):
        numerator=(word()>>5)*2**26+(word()>>6)
        mutate=numerator*RATE_SCALE<rate*DENOMINATOR
        left=below(radius+1) if mutate else None
        right=below(radius+1) if mutate else None
        delta=left-right if mutate else 0
        following=min(hi,max(lo,original+delta))
        periods.append(following)
        trace.append({'gene':name,'uniform_numerator':numerator,'mutated':mutate,
            'left':left,'right':right,'delta':delta,'before':original,'after':following})
    return {'operator':VERSION,'ema_fast':periods[0],'ema_slow':periods[1],
        'rate_per_million':rate,'draws':draws,'trace':trace}



def policy():
    return {'version':VERSION,'genes':['ema_fast','ema_slow'],
        'domains':{'ema_fast':[3,12],'ema_slow':[15,60]},
        'radii':{'ema_fast':3,'ema_slow':15},
        'sexual_rate_per_million':200000,'asexual_rate_per_million':300000,
        'uniform_denominator':str(DENOMINATOR),'decision':'integer_cross_product_lt',
        'step':'difference_of_two_uniform_integers_inclusive_zero_radius',
        'rounding':'none_integer_sum_then_clamp','asset':'fixed_SOL/USD_no_mutation_draw',
        'epoch_event_maximum':2**31-1,'rejection_attempts':256,'word_budget':2048}


def validate_context(strategy,config):
    _counter(strategy._search_epoch,0,2**31-1)
    # Evolve increments the stored event after the batch. The terminal value is
    # valid retained state, but cannot admit a batch that would overflow it.
    _counter(strategy._mutation_event,0,2**31-2)
    if (type(strategy._search_streams) is not SearchRandomStreams
            or strategy._search_streams.algorithm!='genetic_algorithm'
            or type(strategy.mutation_rate) is not float or strategy.mutation_rate!=.20
            or type(strategy.mutation_strength) is not float or strategy.mutation_strength!=.15
            or config.strategy_profile!='ema_baseline_v1'
            or config.enabled_genes!=['ema_fast','ema_slow']
            or config.get_effective_assets()!=['SOL/USD']):
        raise ValueError('Portable operator requires the explicit fixed two-EMA GA profile')
    domains=config.resolve_gene_domains()
    if any((domains[name].minimum,domains[name].maximum)!=(lo,hi)
            or not domains[name].integer for name,lo,hi,_ in DOMAINS):
        raise ValueError('Portable period domains changed without operator review')


def _genome_period(value):
    # Genome's reviewed wire uses integer-valued floats. Accept only an exact
    # integral representation, never rounding a fractional value into the model.
    if type(value) is float:
        numerator,denominator=value.as_integer_ratio()
        if denominator!=1:raise ValueError('Genome period must be exactly integral')
        return numerator
    if type(value) is int:return value
    raise ValueError('Genome period has an unsupported numeric type')


def reproduce(parent,mate,num_children,config,*,rng,seed,epoch,event,child_start,operations):
    # Imports are deliberately local: ordinary legacy evolution does not load this operator.
    from .evolution import NUMERIC_GENES
    from .genome import Genome
    from .strategies.genetic_algorithm import crossover
    _counter(num_children,1,2);_counter(child_start,0,7)
    if child_start+num_children>8:raise ValueError('Portable offspring fanout exceeded')
    config.assert_profile_genome(parent)
    if mate is not None:config.assert_profile_genome(mate)
    generation=max(parent.generation,mate.generation if mate else parent.generation)+1
    if mate is not None:
        repaired=[]
        candidates=list(crossover(parent,mate,generation,config,repair_flags=repaired,rng=rng))[:num_children]
        if any(repaired):raise ValueError('Portable crossover unexpectedly repaired fixed controls')
    else:
        candidates=[Genome(**{g:getattr(parent,g) for g in NUMERIC_GENES},
            assets=list(parent.assets),generation=generation,parent_ids=[]) for _ in range(num_children)]
    for index,child in enumerate(candidates):
        output=mutate_periods(_genome_period(child.ema_fast),_genome_period(child.ema_slow),seed=seed,epoch=epoch,
            event=event,child=child_start+index,sexual=mate is not None)
        child.ema_fast=output['ema_fast'];child.ema_slow=output['ema_slow']
        child.validate(config);config.assert_profile_genome(child)
        if (child.ema_fast,child.ema_slow)!=(output['ema_fast'],output['ema_slow']):
            raise ValueError('Portable profile changed after mutation')
        operations.append('crossover_mutation' if mate is not None else 'clone_mutation')
    return candidates
