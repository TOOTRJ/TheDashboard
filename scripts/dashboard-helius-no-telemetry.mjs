/**
 * Suppress the exact analytics endpoint reviewed in helius-mcp 2.3.0 before its
 * modules load. This is not a general network sandbox or a promise about future
 * upstream versions. Do not inspect or log telemetry bodies, keys or headers.
 */
export function withoutHeliusTelemetry(fetchImplementation) {
  return function dashboardHeliusFetch(input, init) {
    let url;
    try {
      url = new URL(input instanceof Request ? input.url : input);
    } catch {
      // Keep native/fake fetch validation and errors for all other inputs.
    }
    if (url?.origin === 'https://www.helius.dev'
        && url.pathname === '/relay-RMqE/capture/') {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Reflect.apply(fetchImplementation, this, [input, init]);
  };
}

globalThis.fetch = withoutHeliusTelemetry(globalThis.fetch);
