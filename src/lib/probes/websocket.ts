import * as React from "react";
import type { WsMessage } from "./types";
import { VN_ENDPOINTS } from "./constants";
import { openAuthenticatedSocket, type SocketStatus } from "./transport";

export function useProbesWebSocket(
  accessToken: string | null,
  userId: string,
  onMessage: (message: WsMessage) => void,
): SocketStatus {
  const [status, setStatus] = React.useState<SocketStatus>({ connected: false, error: null });
  const onMessageRef = React.useRef(onMessage);
  React.useLayoutEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  // Layout cleanup retires old callbacks as soon as logout/token refresh commits.
  React.useLayoutEffect(() => {
    if (!accessToken || !VN_ENDPOINTS.wsUrl || VN_ENDPOINTS.error) return;
    return openAuthenticatedSocket({
      url: VN_ENDPOINTS.wsUrl,
      accessToken,
      userId,
      onMessage: (message) => onMessageRef.current(message),
      onStatus: setStatus,
    });
  }, [accessToken, userId]);

  return accessToken && !VN_ENDPOINTS.error ? status : {
    connected: false,
    error: VN_ENDPOINTS.error,
  };
}
