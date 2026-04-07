import { defineStore } from 'pinia';
import type { FaultEvent } from '@/shared/types/domain';

export const useFaultStore = defineStore('fault', {
  state: () => ({
    activeFault: null as FaultEvent | null,
    history: [] as FaultEvent[],
  }),
  actions: {
    raiseFault(fault: FaultEvent) {
      this.activeFault = fault;
      this.history.unshift(fault);
      this.history = this.history.slice(0, 20);
    },
    clearFault(id: string) {
      if (this.activeFault?.id === id) {
        this.activeFault = null;
      }
    },
    clearAll() {
      this.activeFault = null;
    },
  },
});
