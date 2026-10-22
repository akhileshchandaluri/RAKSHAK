export type Appliance = {
  id: string; name: string; tier: 1 | 2 | 3; powerKw: number; status: "on" | "off";
};
export type Building = {
  id: string; name: string; kind: string; x: number; z: number;
  powerKw: number; status: string; appliances: Appliance[];
};
export type TwinState = {
  timestamp: number; running: boolean; mode: string; frequencyHz: number;
  solarKw: number; demandKw: number; generationKw: number;
  shedThresholdHz: number; restoreThresholdHz: number; balancingEnabled: boolean;
  disturbance: string; disturbanceSeconds: number; events: string[];
  buildings: Building[];
  metrics: { frequencyNadirHz: number; recoverySeconds: number | null;
    shedActions: number; energyNotServedCriticalKwh: number; reboundPeakKw: number };
};
export type HistoryPoint = { t: number; frequencyHz: number; demandKw: number; generationKw: number };
export type TwinPacket = { state: TwinState; history: HistoryPoint[] };