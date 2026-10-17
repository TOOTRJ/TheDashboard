import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { defaultStrategies, supportedSymbols, timeframes } from '../src/lib/mock/strategies.ts';

// Executes actual TSX and local concept views with controlled UI bindings.
// External widgets, React DOM, native keyboard and real market data are excluded.
function harness(file='src/app/(dashboard)/strategies/page.tsx') {
 const states=[],effects=[];let index=0,tree;const jsx=(type,props)=>({type,props});
 const forbidden=name=>(...args)=>{effects.push({name,args});throw new Error(`Unsupported ${name}`);};
 const react={useState(value){const i=index++;if(!(i in states))states[i]=typeof value==='function'?value():value;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];},useMemo:fn=>fn(),useEffect:()=>{}};
 const modules={react,'react/jsx-runtime':{jsx,jsxs:jsx}};
 const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 for(const node of source.statements)if(ts.isImportDeclaration(node)){
  const name=node.moduleSpecifier.text;if(name==='react')continue;
  modules[name]={};for(const item of node.importClause?.namedBindings?.elements??[])modules[name][item.propertyName?.text??item.name.text]=item.name.text;
 }
 modules['@/lib/mock/strategies']=new Proxy({defaultStrategies,supportedSymbols,timeframes},{get(target,name){return Object.hasOwn(target,name)?target[name]:forbidden(`mock ${String(name)}`);}});
 modules.sonner={toast:new Proxy({}, {get:(_,name)=>forbidden(`toast ${String(name)}`)})};
 modules['@/components/layout/DashboardProvider']={useDashboardFilters:()=>({dateRange:'30d',setDateRange:forbidden('unrelated filter'),searchQuery:'',setSearchQuery:forbidden('unrelated search'),dateRangeOptions:[]})};
 modules['@/components/auth/AuthProvider']={useAuth:()=>({user:{email:'fake@example.invalid'},profile:null,signOut:forbidden('signout')})};
 modules['next/navigation']={usePathname:()=>'/strategies',useRouter:()=>({push:forbidden('navigation'),refresh:forbidden('refresh')})};
 const output=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const exports={};vm.runInNewContext(output,{exports,require:name=>{assert.ok(Object.hasOwn(modules,name),name);return modules[name];},
  setTimeout:forbidden('timer'),setInterval:forbidden('interval'),fetch:forbidden('network'),
  Date:class {constructor(){forbidden('date-based fixture')();}},
  window:{open:forbidden('popup')},document:{createElement:forbidden('artifact')},
 },{timeout:1000});
 function render(){index=0;tree=file.includes('Header')?exports.Header({onOpenMobileNav:forbidden('navigation')}):exports.default();}
 function nodes(node){if(!node||typeof node!=='object')return [];const content=typeof node.type==='function'&&node.type.name==='StrategyConcept'?node.type(node.props):node;return [content,...[content.props?.children].flat(Infinity).flatMap(nodes)];}
 function text(node=tree){return nodes(node).flatMap(n=>[n.props?.children].flat(Infinity).filter(x=>typeof x==='string'||typeof x==='number')).join(' ').replace(/\s+/g,' ').trim();}
 render();return {render,effects,text,nodes:()=>nodes(tree),all:predicate=>nodes(tree).filter(predicate),find:predicate=>{const n=nodes(tree).find(predicate);assert.ok(n);return n;},
  select(id,value){const trigger=nodes(tree).find(n=>n.props?.id===id);assert.ok(trigger);const select=nodes(tree).find(n=>n.type==='Select'&&nodes(n).includes(trigger));select.props.onValueChange(value);render();},
  request(button,event='click'){if(!button.props.disabled){if(event==='Enter')button.props.onKeyDown?.({key:'Enter'});button.props.onClick?.();}render();},
 };
}

test('initial strategy page evaluates no seeded trades and shows unavailable rather than fabricated results',()=>{
 const h=harness();assert.match(h.text(),/Examples only/);assert.match(h.text(),/No trades, returns or risk scores have been calculated/);assert.match(h.text(),/do not run a backtest or configure the trading bot/);
 assert.match(h.text(),/Historical strategy evaluation is not available/);assert.doesNotMatch(h.text(),/P&L|Sharpe|Profit Factor|Max Drawdown|strategies tested|Backtest complete|Infinity/);
 assert.equal(h.all(n=>n.type==='Table'||n.type==='Dialog'||n.type==='Input'||n.type==='Checkbox').length,0);assert.deepEqual(h.effects,[]);
});
test('unavailable backtest is disabled with an adjacent reason and no click/Enter/completion handler',()=>{
 const h=harness();const button=h.find(n=>n.type==='Button'&&h.text(n).includes('Run backtest unavailable'));
 assert.equal(button.props.disabled,true);assert.equal(button.props.type,'button');assert.equal(button.props.onClick,undefined);assert.equal(button.props.onKeyDown,undefined);
 assert.match(h.text(h.find(n=>n.props?.id===button.props['aria-describedby'])),/No historical dataset has been evaluated/);
 h.request(button);h.request(button,'Enter');assert.deepEqual(h.effects,[]);assert.doesNotMatch(h.text(),/Backtest complete|strategies tested/);
});
test('supported external symbol choices alter widgets only without evaluating any strategy',()=>{
 const h=harness();for(const item of supportedSymbols){h.select('strategy-chart-symbol',item.value);const expected=`BINANCE:${item.value.replace('USD','USDT')}`;
  assert.equal(h.find(n=>n.type==='TradingViewChart').props.symbol,expected);assert.equal(h.find(n=>n.type==='TradingViewAnalysis').props.symbol,expected);
  assert.match(h.text(),/Historical strategy evaluation is not available/);assert.deepEqual(h.effects,[]);
 }
 const previous=h.find(n=>n.type==='TradingViewChart').props.symbol;h.select('strategy-chart-symbol','private-invalid');assert.equal(h.find(n=>n.type==='TradingViewChart').props.symbol,previous);
});
test('each chart timeframe retains supported mapping and separate explicitly one-hour analysis',()=>{
 const h=harness(),intervals={'1m':'1','5m':'5','15m':'15','1h':'60','4h':'240','1d':'D'};
 for(const item of timeframes){h.select('strategy-chart-timeframe',item.value);assert.equal(h.find(n=>n.type==='TradingViewChart').props.interval,intervals[item.value]);assert.equal(h.find(n=>n.type==='TradingViewAnalysis').props.interval,'1h');assert.deepEqual(h.effects,[]);}
 h.select('strategy-chart-timeframe','invalid');assert.equal(h.find(n=>n.type==='TradingViewChart').props.interval,'D');assert.match(h.text(),/External One-Hour Analysis/);
});
test('strategy concepts expose only read-only sample definitions with no purported tested selections',()=>{
 const h=harness();for(const item of defaultStrategies){assert.ok(h.text().includes(item.name));for(const [name,value]of Object.entries(item.parameters))assert.ok(h.all(n=>n.type==='span').some(n=>h.text(n).replace(/\s+:/g,':')===`${name}: ${value}`));}
 assert.equal(h.all(n=>n.type==='h3').length,defaultStrategies.length);assert.equal(h.all(n=>n.props?.onClick&&n.type!=='Button').length,0);assert.doesNotMatch(h.text(),/strategies tested|[0-9]+\/[0-9]+ selected/);
 assert.match(h.text(),/independently provided chart is not input/);assert.doesNotMatch(h.text(),/Live Chart|powered by TradingView|Backtest Results/);
 const link=h.find(n=>n.type==='a');assert.equal(link.props.href,'https://www.tradingview.com/chart/');assert.equal(link.props.rel,'noopener noreferrer');assert.deepEqual(h.effects,[]);
});
test('actual route header agrees with the unavailable evaluator without changing unrelated actions',()=>{
 const h=harness('src/components/layout/Header.tsx');assert.match(h.text(),/Strategy Concepts/);assert.match(h.text(),/historical evaluation unavailable/);assert.doesNotMatch(h.text(),/Test and analyze trading strategies with historical data/);assert.deepEqual(h.effects,[]);
});
