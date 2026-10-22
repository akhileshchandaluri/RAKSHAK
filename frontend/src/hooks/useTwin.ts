import { useEffect, useState } from "react";
import type { HistoryPoint, TwinState, TwinPacket } from "../types";

const API = "http://localhost:8000";
const WS = "ws://localhost:8000/ws";

export function useTwin() {
  const [state, setState] = useState<TwinState | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let disposed = false;

    fetch(`${API}/api/state`)
      .then(r => r.json())
      .then((s: TwinState) => { if (!disposed) setState(s); })
      .catch(() => { if (!disposed) setConnected(false); });

    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(WS);
      socket.onopen = () => setConnected(true);
      socket.onmessage = event => {
        const packet = JSON.parse(event.data) as TwinPacket;
        setState(packet.state);
        setHistory(packet.history);
      };
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) retry = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket?.close();
    };
    connect();

    return () => {
      disposed = true;
      if (retry) window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  async function post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(`${API}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json() as Promise<T>;
  }

  return {
    state, history, connected,
    setScenario: (scenario: string) => post("/api/scenario", { scenario }),
    setBalancing: (balancingEnabled: boolean) => post("/api/control", { balancingEnabled }),
  };
}