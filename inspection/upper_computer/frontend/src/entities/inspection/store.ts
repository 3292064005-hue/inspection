import { defineStore } from 'pinia';
import type { CameraFrame, InspectionResult, ObservedInspectionResult, ResultStatisticsSnapshot } from '@/shared/types/domain';

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
      semantic: 'LATEST_RESULT_FRAME',
      sourceEvent: 'inspection.result.observed',
      description: '最近一次视觉处理结果对应的图像快照。',
    } as CameraFrame,
    currentResult: null as InspectionResult | null,
    observedResult: null as ObservedInspectionResult | null,
    recentResults: [] as InspectionResult[],
    statistics: null as ResultStatisticsSnapshot | null,
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
    replaceRecentResults(results: InspectionResult[]) {
      const deduped = new Map<string, InspectionResult>();
      results.forEach((result) => {
        if (!result?.id) return;
        deduped.set(result.id, result);
      });
      const ordered = Array.from(deduped.values())
        .sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp)))
        .slice(0, 60);
      this.recentResults = ordered;
      if (this.selectedResultId) {
        this.currentResult = ordered.find((item) => item.id === this.selectedResultId) ?? this.currentResult;
      } else {
        this.currentResult = ordered[0] ?? null;
      }
    },
    applyStatistics(statistics: ResultStatisticsSnapshot | null) {
      this.statistics = statistics;
    },
    applyObservedResult(result: ObservedInspectionResult) {
      this.observedResult = result;
      this.frame = {
        ...this.frame,
        url: result.overlayUrl ?? result.imageUrl ?? this.frame.url,
        capturedAt: result.timestamp,
        annotated: !!result.overlayUrl,
        semantic: 'LATEST_RESULT_FRAME',
        sourceEvent: 'inspection.result.observed',
        description: '最近一次视觉处理结果对应的图像快照。',
      };
    },
    applyResult(result: InspectionResult) {
      this.currentResult = result;
      this.selectedResultId = result.id;
      if (this.observedResult?.id === result.id) {
        this.observedResult = null;
      }
      this.replaceRecentResults([result, ...this.recentResults]);
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
