import type { ConnectionState } from '@/shared/types/domain';
import type { GatewayStatusSnapshot } from '@/shared/gateway/contracts';

export type AppSessionState = 'booting' | 'connecting' | 'online' | 'reconnecting' | 'degraded' | 'offline' | 'error';

export function deriveAppSessionState(connectionState: ConnectionState, status?: GatewayStatusSnapshot): AppSessionState {
  if (connectionState === 'BOOTING') return 'booting';
  if (connectionState === 'CONNECTING') return 'connecting';
  if (connectionState === 'RECONNECTING' || status?.transport === 'RECONNECTING') return 'reconnecting';
  if (connectionState === 'DEGRADED') return 'degraded';
  if (connectionState === 'ERROR') return 'error';
  if (connectionState === 'OFFLINE') return 'offline';
  return 'online';
}
