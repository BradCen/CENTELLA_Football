import type { GameState } from './types';

declare global {
  interface Window {
    pywebview?: {
      api?: {
        runtime_state?: () => Promise<{ ready: boolean; platform: string }>;
        play_config?: (payload: Record<string, unknown>) => Promise<{ ok: boolean; message: string }>;
        toggle_fullscreen?: () => Promise<{ ok: boolean }>;
        close?: () => Promise<{ ok: boolean }>;
      };
    };
  }
}

export async function runtimeState() {
  const api = window.pywebview?.api;
  if (!api?.runtime_state) return { ready: false, platform: 'browser' };
  try { return await api.runtime_state(); }
  catch { return { ready: false, platform: 'error' }; }
}

export async function launchMatch(state: GameState) {
  const api = window.pywebview?.api;
  if (!api?.play_config) {
    return { ok: false, message: 'Bridge nativo no disponible. Ejecuta CENTELLA mediante RUN_CENTELLA_BETA.bat.' };
  }

  return api.play_config({
    level: '11_vs_11_stochastic',
    local_players: 1,
    controller_count: navigator.getGamepads?.().filter(Boolean).length ?? 0,
    versus: false,
    difficulty: state.match.difficulty,
    duration: state.match.duration,
    weather: state.match.weather,
    stadium: state.match.stadium,
    time: state.match.time,
    camera: state.match.camera,
    speed: state.match.speed,
    home_team: state.homeTeam.id,
    away_team: state.awayTeam.id,
    home_kit: state.homeKit,
    away_kit: state.awayKit,
    formation: state.formation,
    tactic: state.tactic,
    width: state.width,
    depth: state.depth,
    captain: state.captainId,
    penalty_taker: state.penaltyId,
  });
}
