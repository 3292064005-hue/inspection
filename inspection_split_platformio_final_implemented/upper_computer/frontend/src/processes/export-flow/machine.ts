export type ExportFlowState = 'idle' | 'requesting' | 'ready' | 'failed';

export function deriveExportFlowState(input: { busy: boolean; exportedUrl: string; failed: boolean }): ExportFlowState {
  if (input.busy) return 'requesting';
  if (input.failed) return 'failed';
  if (input.exportedUrl) return 'ready';
  return 'idle';
}
