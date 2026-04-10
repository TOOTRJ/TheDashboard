import * as React from "react";
import type { WsMessage } from "./types";
import { VN_WS_URL } from "./constants";

interface UseProbesWebSocket {
  connected: boolean;
  sendCommand: (action: string, params?: Record<string, unknown>) => void;
}

/**
 * Always-on WebSocket hook with callback-based message handling.
 * The onMessage callback fires synchronously for EVERY message — no drops.
 */
export function useProbesWebSocket(
  onMessage: (msg: WsMessage) => void,
): UseProbesWebSocket {
  const [connected, setConnected] = React.useState(false);
  const wsRef = React.useRef<WebSocket | null>(null);
  const reconnectTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = React.useRef(1000);
  const mountedRef = React.useRef(true);
  // Stable ref to the latest callback (avoids reconnecting on callback change)
  const onMessageRef = React.useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = React.useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(VN_WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return; }
        setConnected(true);
        reconnectDelay.current = 1000;
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const msg = JSON.parse(event.data) as WsMessage;
          onMessageRef.current(msg);
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnected(false);
        wsRef.current = null;
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, 15000);
          connect();
        }, reconnectDelay.current);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      if (mountedRef.current) {
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, 15000);
          connect();
        }, reconnectDelay.current);
      }
    }
  }, []);

  React.useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendCommand = React.useCallback(
    (action: string, params?: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({ type: "command", data: { action, params } }),
        );
      }
    },
    [],
  );

  return { connected, sendCommand };
}
