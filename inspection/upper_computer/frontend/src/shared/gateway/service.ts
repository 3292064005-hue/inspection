import { appEnv } from '@/shared/config/env';
import type { HmiGateway } from '@/shared/gateway/contracts';
import { SafeGateway } from '@/shared/gateway/safeGateway';
import { MockGateway } from '@/mocks/mockGateway';
import { HttpGateway } from '@/shared/gateway/httpGateway';

let gatewayInstance: HmiGateway | null = null;

export function getGateway(): HmiGateway {
  if (gatewayInstance) return gatewayInstance;

  if (appEnv.gatewayMode === 'http') {
    gatewayInstance = new SafeGateway(new HttpGateway());
    return gatewayInstance as HmiGateway;
  }

  gatewayInstance = new SafeGateway(new MockGateway());
  return gatewayInstance as HmiGateway;
}
