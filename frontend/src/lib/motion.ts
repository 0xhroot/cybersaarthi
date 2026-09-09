import type { Variants } from "framer-motion";

/**
 * Centralized motion primitives.
 *
 * Every animated surface should reuse one of these tokens so the product keeps
 * a single, restrained motion language. Respects reduced-motion preferences via
 * the `useReducedMotion` hook at the call site (see lib/motion helpers).
 */

export const MOTION_DURATIONS = {
  fast: 0.14,
  base: 0.22,
  slow: 0.34,
} as const;

export const easeStandard = [0.2, 0, 0, 1] as const;
export const easeEmphasized = [0.16, 1, 0.3, 1] as const;

export const pageTransition: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: MOTION_DURATIONS.base, ease: easeStandard } },
  exit: { opacity: 0, transition: { duration: MOTION_DURATIONS.fast, ease: easeStandard } },
};

export const fadeIn: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: MOTION_DURATIONS.base, ease: easeStandard } },
  exit: { opacity: 0, transition: { duration: MOTION_DURATIONS.fast } },
};

export const slideIn: Variants = {
  initial: { opacity: 0, x: -10 },
  animate: { opacity: 1, x: 0, transition: { duration: MOTION_DURATIONS.base, ease: easeStandard } },
  exit: { opacity: 0, x: -6, transition: { duration: MOTION_DURATIONS.fast } },
};

export const scaleIn: Variants = {
  initial: { opacity: 0, scale: 0.97 },
  animate: {
    opacity: 1,
    scale: 1,
    transition: { duration: MOTION_DURATIONS.base, ease: easeEmphasized },
  },
  exit: { opacity: 0, scale: 0.98, transition: { duration: MOTION_DURATIONS.fast } },
};

export function staggerChildren(interval = 0.05, delay = 0): Variants {
  return {
    animate: { transition: { staggerChildren: interval, delayChildren: delay } },
  };
}

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: MOTION_DURATIONS.base, ease: easeStandard } },
};

export const hoverLift = {
  whileHover: { y: -1 },
  whileTap: { scale: 0.99 },
  transition: { duration: MOTION_DURATIONS.fast, ease: easeStandard },
} as const;

export const drawerTransition: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: MOTION_DURATIONS.fast } },
  exit: { opacity: 0, transition: { duration: MOTION_DURATIONS.fast } },
};