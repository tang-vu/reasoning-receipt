/**
 * Selection + replay state for the DAG view.
 *
 * Zustand keeps this trivially small so DagView, DagDetailPanel, and
 * DagReplayControls share state without prop drilling.
 */

import { create } from "zustand";

interface DagState {
  selectedNodeId: string | null;
  isPlaying: boolean;
  /** Current step in the replay (0 = nothing visible yet). */
  step: number;
  /** Total replay steps; renderer sets this when graph loads. */
  totalSteps: number;
  select: (id: string | null) => void;
  togglePlay: () => void;
  setStep: (s: number) => void;
  setTotalSteps: (n: number) => void;
  reset: () => void;
}

export const useDagStore = create<DagState>((set) => ({
  selectedNodeId: null,
  isPlaying: false,
  step: 0,
  totalSteps: 0,
  select: (id) => set({ selectedNodeId: id }),
  togglePlay: () => set((s) => ({ isPlaying: !s.isPlaying })),
  setStep: (step) => set({ step }),
  setTotalSteps: (totalSteps) => set({ totalSteps }),
  reset: () => set({ selectedNodeId: null, isPlaying: false, step: 0 }),
}));
