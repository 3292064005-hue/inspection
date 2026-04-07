import { defineStore } from 'pinia';

const STORAGE_KEY = 'inspection-hmi-settings';

interface UiSettings {
  fullScreenByDefault: boolean;
  showAdvancedMetrics: boolean;
  soundEnabled: boolean;
  archiveDays: number;
  refreshMode: 'smooth' | 'performance';
}

function loadSettings(): UiSettings {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return {
      fullScreenByDefault: false,
      showAdvancedMetrics: true,
      soundEnabled: false,
      archiveDays: 14,
      refreshMode: 'smooth',
    };
  }

  try {
    return JSON.parse(raw) as UiSettings;
  } catch {
    return {
      fullScreenByDefault: false,
      showAdvancedMetrics: true,
      soundEnabled: false,
      archiveDays: 14,
      refreshMode: 'smooth',
    };
  }
}

export const useSettingsStore = defineStore('settings', {
  state: () => loadSettings(),
  actions: {
    persist() {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          fullScreenByDefault: this.fullScreenByDefault,
          showAdvancedMetrics: this.showAdvancedMetrics,
          soundEnabled: this.soundEnabled,
          archiveDays: this.archiveDays,
          refreshMode: this.refreshMode,
        }),
      );
    },
  },
});
