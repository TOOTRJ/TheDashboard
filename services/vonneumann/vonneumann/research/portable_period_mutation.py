"""Integer-only two-period mutation proposal; no installed model or authority.

Old GA Gaussian semantics are unchanged. A future consumer must select this
operator under a new model/configuration version, never by relabeling a v1
checkpoint. Per-child namespaces match the old comparison seed; distribution
and draw consumption are explicitly different under this operator version.
"""
from __future__ import annotations

from ..core.search_random import SearchRandomStreams

VERSION='ema-period-triangular-integer-research-v1'
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
        'rate_per_million':rate,'draws':draws,'trace':trace,'model_integration':False,
        'restoration_authority':False}
