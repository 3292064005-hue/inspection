import type { Decision, HealthStatus, StationPhase } from '@/shared/types/domain';

export const phaseOrder: StationPhase[] = [
  'BOOT',
  'IDLE',
  'READY',
  'FEEDING',
  'POSITION_CHECK',
  'CAPTURE',
  'ANALYZE',
  'SORTING',
  'COUNT_UPDATE',
  'FAULT',
];

export function phaseLabel(value: StationPhase): string {
  return {
    BOOT: '初始化',
    IDLE: '待机',
    READY: '准备放行',
    FEEDING: '单件放行',
    POSITION_CHECK: '到位确认',
    CAPTURE: '图像采集',
    ANALYZE: '图像分析',
    SORTING: '执行分拣',
    COUNT_UPDATE: '统计记录',
    FAULT: '故障',
  }[value];
}

export function decisionTone(value: Decision): string {
  return {
    OK: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300',
    NG: 'border-rose-400/30 bg-rose-500/10 text-rose-300',
    RECHECK: 'border-amber-400/30 bg-amber-500/10 text-amber-300',
  }[value];
}

export function healthTone(value: HealthStatus): string {
  return {
    ONLINE: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300',
    DEGRADED: 'border-amber-400/30 bg-amber-500/10 text-amber-300',
    OFFLINE: 'border-rose-400/30 bg-rose-500/10 text-rose-300',
  }[value];
}
