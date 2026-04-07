import { defineStore } from 'pinia';
import type { CameraFrame, InspectionResult } from '@/shared/types/domain';

export interface TimelineEntry {
  id: string;
  time: string;
  title: string;
  detail: string;
  tone: 'INFO' | 'WARN' | 'ERROR';
}

export const useInspectionStore = defineStore('inspection', {
  state: () => ({
    frame: {
      url: '',
      capturedAt: new Date().toISOString(),
      annotated: true,
    } as CameraFrame,
    currentResult: null as InspectionResult | null,
    recentResults: [] as InspectionResult[],
    selectedResultId: '' as string,
    frameViewMode: 'overlay' as 'overlay' | 'raw',
    timeline: [] as TimelineEntry[],
  }),
  getters: {
    selectedResult(state) {
      if (!state.selectedResultId) return state.currentResult;
      return state.recentResults.find((item) => item.id === state.selectedResultId) ?? state.currentResult;
    },
  },
  actions: {
    applyFrame(frame: CameraFrame) {
      this.frame = frame;
    },
    applyResult(result: InspectionResult) {
      this.currentResult = result;
      this.selectedResultId = result.id;
      this.recentResults.unshift(result);
      this.recentResults = this.recentResults.slice(0, 60);

      this.timeline.unshift({
        id: result.id,
        time: result.timestamp,
        title: `${result.decision} / ${result.recipeName}`,
        detail: result.explanation.join('；'),
        tone: result.decision === 'NG' ? 'WARN' : result.decision === 'RECHECK' ? 'WARN' : 'INFO',
      });
      this.timeline = this.timeline.slice(0, 30);
    },
    pushTimeline(title: string, detail: string, tone: TimelineEntry['tone'] = 'INFO') {
      this.timeline.unshift({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        time: new Date().toISOString(),
        title,
        detail,
        tone,
      });
      this.timeline = this.timeline.slice(0, 30);
    },
    selectResult(id: string) {
      this.selectedResultId = id;
    },
    setFrameViewMode(mode: 'overlay' | 'raw') {
      this.frameViewMode = mode;
    },
  },
});
