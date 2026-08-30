import { create } from "zustand";

/** The case the user is currently investigating, used for global search scope. */
interface CaseNavState {
  activeCaseId: string | null;
  setActiveCaseId: (id: string | null) => void;
}

export const useCaseNavStore = create<CaseNavState>((set) => ({
  activeCaseId: null,
  setActiveCaseId: (activeCaseId) => set({ activeCaseId }),
}));