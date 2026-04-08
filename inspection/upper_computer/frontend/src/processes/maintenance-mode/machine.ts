export type MaintenanceState = 'locked' | 'enabled' | 'executing' | 'cooldown';

export function deriveMaintenanceState(input: { enabled: boolean; busy: boolean; hasCooldown: boolean }): MaintenanceState {
  if (!input.enabled) return 'locked';
  if (input.busy) return 'executing';
  if (input.hasCooldown) return 'cooldown';
  return 'enabled';
}
