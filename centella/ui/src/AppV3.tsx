import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type Dispatch,
  type SetStateAction,
} from 'react';
import ExternalLineupPitch from './ExternalLineupPitch';
import { teams } from './data';
import { launchMatch, runtimeState } from './bridge';
import { SpatialButton, useInitialFocus, useSpatialGamepad } from './spatial';
import type { FormationId, GameState, Player, Screen, Team } from './types';

const kitNames = ['LOCAL', 'VISITANTE', 'ALTERNATIVA'];
const formations: { id: FormationId; label: string }[] = [
  { id: '433', label: '4-3-3' },
  { id: '4231', label: '4-2-3-1' },
  { id: '442', label: '4-4-2' },
  { id: '352', label: '3-5-2' },
];

function Brand() {
  return <div className="v3-brand"><span className="v3-bolt"/><div><b>CENTELLA</b><small>FOOTBALL</small></div></div>;
}

function TopChrome({ section, step, engineReady }: { section: string; step?: string; engineReady: boolean }) {
  return <header className="v3-top"><Brand/><nav><span className={section === 'JUGAR' ? 'active' : ''}>JUGAR</span><span>CARRERA</span><span>COMPETICIONES</span><span>ENTRENAR</span><span>PERSONALIZAR</span></nav><div className={`v3-engine ${engineReady ? 'ready' : ''}`}><i/>{engineReady ? 'MOTOR CONECTADO' : 'MOTOR OFFLINE'}{step && <small>{step}</small>}</div></header>;
}

function FooterHints({ build = 'V3 // SPATIAL UI' }: { build?: string }) {
  return <footer className="v3-hints"><span><kbd>↕↔</kbd>NAVEGAR</span><span><kbd>ENTER</kbd>ACEPTAR</span><span><kbd>ESC</kbd>ATRÁS</span><span><kbd>A / ✕</kbd>ACEPTAR</span><span><kbd>B / ○</kbd>ATRÁS</span><b>{build}</b></footer>;
}

function Splash({ onContinue }: { onContinue: () => void }) {
  useEffect(() => {
    let used = false;
    const continueOnce = () => { if (!used) { used = true; onContinue(); } };
    const key = () => continueOnce();
    window.addEventListener('keydown', key, { once: true });
    const interval = window.setInterval(() => {
      const pad = navigator.getGamepads?.().find(Boolean);
      if (pad?.buttons.some((button) => button.pressed)) continueOnce();
    }, 80);
    return () => { window.removeEventListener('keydown', key); window.clearInterval(interval); };
  }, [onContinue]);

  return <main className="v3-screen v3-splash" onClick={onContinue}>
    <div className="v3-stars"/><div className="v3-stadium"/><div className="v3-splash-brand"><span className="v3-mega-bolt"/><h1>CENTELLA</h1><p>FOOTBALL</p></div><div className="v3-press">PRESIONA CUALQUIER BOTÓN</div><small className="v3-legal">CENTELLA TECHNOLOGIES // DEVELOPMENT BUILD</small>
  </main>;
}

function Home({ onQuickMatch, engineReady }: { onQuickMatch: () => void; engineReady: boolean }) {
  useInitialFocus('HOME_QUICK');
  return <main className="v3-screen v3-home"><div className="v3-stars"/><div className="v3-stadium"/><TopChrome section="JUGAR" engineReady={engineReady}/><section className="v3-home-grid">
    <SpatialButton focusKey="HOME_QUICK" className="v3-hero" onPress={onQuickMatch} accessibilityLabel="Partido rápido">
      {(focused) => <><div className="v3-hero-watermark">01</div><div className="v3-hero-copy"><span>CENTELLA MATCHDAY // JUGAR AHORA</span><h1>EL PARTIDO<br/><em>EMPIEZA AQUÍ.</em></h1><p>Elige dos clubes, prepara tu once y entra al campo. Nada de formularios: primero fútbol.</p></div><div className="v3-player-silhouette"><div/></div><div className={`v3-selection-chip ${focused ? 'visible' : ''}`}>SELECCIONADO</div><div className="v3-hero-cta"><div><strong>PARTIDO RÁPIDO</strong><small>CLUBES · KITS · GAME PLAN · 11 VS 11</small></div><b>→</b></div></>}
    </SpatialButton>
    <aside className="v3-side-stack"><div className="v3-mode locked"><span>02</span><label>CARRERA</label><strong>LIGA MÁSTER</strong><p>Construye el club durante varias temporadas.</p></div><div className="v3-mode locked"><span>03</span><label>CARRERA DE JUGADOR</label><strong>SER LEYENDA</strong><p>De promesa a referente mundial.</p></div><div className="v3-settings-teaser"><i>⚙</i><div><strong>AJUSTES</strong><small>Controles · audio · video</small></div></div></aside>
  </section><FooterHints/></main>;
}

function TeamCrest({ team, giant = false }: { team: Team; giant?: boolean }) {
  return <div className={`v3-crest ${giant ? 'giant' : ''}`} style={{ '--club-a': team.primary, '--club-b': team.secondary } as CSSProperties}><span>{team.short}</span></div>;
}

function TeamRating({ team }: { team: Team }) {
  const attack = Math.min(99, team.rating + 2);
  const midfield = Math.max(50, team.rating - 1);
  const defense = Math.max(50, team.rating - 3);
  return <div className="v3-rating"><div><span>ATA</span><i><b style={{ width: `${attack}%` }}/></i><strong>{attack}</strong></div><div><span>MED</span><i><b style={{ width: `${midfield}%` }}/></i><strong>{midfield}</strong></div><div><span>DEF</span><i><b style={{ width: `${defense}%` }}/></i><strong>{defense}</strong></div></div>;
}

function TeamSelect({ state, setState, onContinue, engineReady }: { state: GameState; setState: Dispatch<SetStateAction<GameState>>; onContinue: () => void; engineReady: boolean }) {
  const [side, setSide] = useState<'home'|'away'>('home');
  const [league, setLeague] = useState('TODAS');
  const leagues = ['TODAS', ...Array.from(new Set(teams.map((team) => team.league)))];
  const visible = league === 'TODAS' ? teams : teams.filter((team) => team.league === league);
  const current = side === 'home' ? state.homeTeam : state.awayTeam;
  useInitialFocus(`TEAM_${current.id}`, `${side}-${league}`);

  const choose = (team: Team) => {
    if (side === 'home') {
      setState((s) => ({ ...s, homeTeam: team }));
      setSide('away');
    } else {
      setState((s) => ({ ...s, awayTeam: team }));
    }
  };

  return <main className="v3-screen v3-team-select"><div className="v3-stars"/><TopChrome section="JUGAR" step="01 / EQUIPOS" engineReady={engineReady}/><section className="v3-versus-stage">
    <SpatialButton focusKey="SIDE_HOME" className={`v3-club-panel home ${side === 'home' ? 'armed' : ''}`} onPress={() => setSide('home')}><span className="v3-side-label">LOCAL</span><TeamCrest team={state.homeTeam} giant/><h2>{state.homeTeam.name}</h2><small>{state.homeTeam.country} · {state.homeTeam.league}</small><TeamRating team={state.homeTeam}/></SpatialButton>
    <div className="v3-vs-core"><small>AMISTOSO</small><b>VS</b><i>90'</i></div>
    <SpatialButton focusKey="SIDE_AWAY" className={`v3-club-panel away ${side === 'away' ? 'armed' : ''}`} onPress={() => setSide('away')}><span className="v3-side-label">VISITANTE</span><TeamCrest team={state.awayTeam} giant/><h2>{state.awayTeam.name}</h2><small>{state.awayTeam.country} · {state.awayTeam.league}</small><TeamRating team={state.awayTeam}/></SpatialButton>
  </section><section className="v3-browser"><div className="v3-leagues">{leagues.map((name) => <SpatialButton key={name} focusKey={`LEAGUE_${name}`} className={`v3-league ${league === name ? 'active' : ''}`} onPress={() => setLeague(name)}>{name}</SpatialButton>)}</div><div className="v3-team-rail">{visible.map((team) => <SpatialButton key={team.id} focusKey={`TEAM_${team.id}`} className={`v3-team-tile ${current.id === team.id ? 'chosen' : ''}`} onPress={() => choose(team)}><TeamCrest team={team}/><div><strong>{team.name}</strong><small>{team.short} · {team.rating} OVR</small></div></SpatialButton>)}</div></section><div className="v3-next"><SpatialButton focusKey="TEAM_CONTINUE" className="v3-next-button" disabled={state.homeTeam.id === state.awayTeam.id} onPress={onContinue}>EQUIPACIONES <b>→</b></SpatialButton></div><FooterHints/></main>;
}

function Jersey({ team, kit, large = false }: { team: Team; kit: number; large?: boolean }) {
  const palettes = [[team.primary, team.secondary], [team.secondary, team.primary], [team.accent, team.primary]];
  const [a, b] = palettes[kit] ?? palettes[0];
  return <div className={`v3-jersey ${large ? 'large' : ''}`} style={{ '--kit-a': a, '--kit-b': b } as CSSProperties}><div className="v3-neck"/><span>{team.short}</span><i/></div>;
}

function Kits({ state, setState, onContinue, engineReady }: { state: GameState; setState: Dispatch<SetStateAction<GameState>>; onContinue: () => void; engineReady: boolean }) {
  useInitialFocus(`HOME_KIT_${state.homeKit}`);
  return <main className="v3-screen v3-kits"><div className="v3-stars"/><TopChrome section="JUGAR" step="02 / EQUIPACIONES" engineReady={engineReady}/><section className="v3-kit-stage"><div className="v3-kit-side"><span>LOCAL</span><h2>{state.homeTeam.name}</h2><Jersey team={state.homeTeam} kit={state.homeKit} large/><div className="v3-kit-rail">{kitNames.map((name, index) => <SpatialButton key={name} focusKey={`HOME_KIT_${index}`} className={`v3-kit-option ${state.homeKit === index ? 'active' : ''}`} onPress={() => setState((s) => ({ ...s, homeKit: index }))}><Jersey team={state.homeTeam} kit={index}/><small>{name}</small></SpatialButton>)}</div></div><div className="v3-kit-middle"><small>MATCHDAY</small><div><b>{state.homeTeam.short}</b><i>VS</i><b>{state.awayTeam.short}</b></div><span>EVITA COINCIDENCIAS DE COLOR</span></div><div className="v3-kit-side"><span>VISITANTE</span><h2>{state.awayTeam.name}</h2><Jersey team={state.awayTeam} kit={state.awayKit} large/><div className="v3-kit-rail">{kitNames.map((name, index) => <SpatialButton key={name} focusKey={`AWAY_KIT_${index}`} className={`v3-kit-option ${state.awayKit === index ? 'active' : ''}`} onPress={() => setState((s) => ({ ...s, awayKit: index }))}><Jersey team={state.awayTeam} kit={index}/><small>{name}</small></SpatialButton>)}</div></div></section><div className="v3-next"><SpatialButton focusKey="KIT_CONTINUE" className="v3-next-button" onPress={onContinue}>GAME PLAN <b>→</b></SpatialButton></div><FooterHints/></main>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="v3-stat"><span>{label}</span><i><b style={{ width: `${value}%` }}/></i><strong>{value}</strong></div>;
}

function GamePlan({ state, setState, lineup, setLineup, tab, setTab, onContinue, engineReady }: { state: GameState; setState: Dispatch<SetStateAction<GameState>>; lineup: string[]; setLineup: Dispatch<SetStateAction<string[]>>; tab: number; setTab: Dispatch<SetStateAction<number>>; onContinue: () => void; engineReady: boolean }) {
  const [selectedId, setSelectedId] = useState(lineup[0]);
  const playerMap = useMemo(() => new Map(state.homeTeam.players.map((player) => [player.id, player])), [state.homeTeam]);
  const starters = lineup.slice(0, 11).map((id) => playerMap.get(id)).filter((player): player is Player => Boolean(player));
  const bench = lineup.slice(11).map((id) => playerMap.get(id)).filter((player): player is Player => Boolean(player));
  const selected = playerMap.get(selectedId) ?? starters[0];
  const selectedIndex = lineup.indexOf(selectedId);
  useInitialFocus(`GP_TAB_${tab}`, tab);

  const substitute = (benchId: string) => {
    if (selectedIndex < 0 || selectedIndex >= 11) { setSelectedId(benchId); return; }
    setLineup((current) => {
      const next = [...current];
      const benchIndex = next.indexOf(benchId);
      if (benchIndex >= 11) [next[selectedIndex], next[benchIndex]] = [next[benchIndex], next[selectedIndex]];
      return next;
    });
    setSelectedId(benchId);
  };

  const tabs = ['FORMACIÓN','TÁCTICAS','ROLES','INSTRUCCIONES'];
  return <main className="v3-screen v3-gameplan"><TopChrome section="JUGAR" step="03 / GAME PLAN" engineReady={engineReady}/><div className="v3-gp-tabs">{tabs.map((name, index) => <SpatialButton key={name} focusKey={`GP_TAB_${index}`} className={`v3-gp-tab ${tab === index ? 'active' : ''}`} onPress={() => setTab(index)}>{name}</SpatialButton>)}</div><section className="v3-gp-layout"><div className="v3-pitch-column"><div className="v3-pitch-frame"><ExternalLineupPitch club={state.homeTeam} starters={starters} formation={state.formation} selectedId={selected.id} captainId={state.captainId} onSelect={setSelectedId}/></div><div className="v3-bench"><span>SUPLENTES</span>{bench.map((player) => <SpatialButton key={player.id} focusKey={`BENCH_${player.id}`} className={`v3-bench-player ${selected.id === player.id ? 'active' : ''}`} onPress={() => substitute(player.id)}><b>{player.rating}</b><small>{player.position}</small><strong>{player.name.split(' ').pop()}</strong></SpatialButton>)}</div></div><aside className="v3-plan-panel"><div className="v3-player-head"><div className="v3-ovr">{selected.rating}</div><div><small>{selected.position} · #{selected.number}</small><h2>{selected.name}</h2></div></div><div className="v3-stats"><Stat label="RIT" value={selected.pace}/><Stat label="TIR" value={selected.shot}/><Stat label="PAS" value={selected.pass}/><Stat label="REG" value={selected.dribble}/><Stat label="DEF" value={selected.defense}/><Stat label="FIS" value={selected.physical}/></div>{tab === 0 && <div className="v3-panel-section"><label>FORMACIÓN</label><div className="v3-option-grid">{formations.map((formation) => <SpatialButton key={formation.id} focusKey={`FORMATION_${formation.id}`} className={`v3-option ${state.formation === formation.id ? 'active' : ''}`} onPress={() => setState((s) => ({ ...s, formation: formation.id }))}>{formation.label}</SpatialButton>)}</div><p>Cancha renderizada por react-soccer-lineup (MIT). Selecciona un titular en el campo o un suplente abajo.</p></div>}{tab === 1 && <div className="v3-panel-section"><label>PLAN DE JUEGO</label><div className="v3-option-grid">{['Equilibrado','Posesión','Vertical','Contraataque'].map((tactic) => <SpatialButton key={tactic} focusKey={`TACTIC_${tactic}`} className={`v3-option ${state.tactic === tactic ? 'active' : ''}`} onPress={() => setState((s) => ({ ...s, tactic }))}>{tactic}</SpatialButton>)}</div><div className="v3-tactic-meter"><span>ANCHURA</span><b style={{ width: `${state.width}%` }}/></div><div className="v3-tactic-meter"><span>PROFUNDIDAD</span><b style={{ width: `${state.depth}%` }}/></div></div>}{tab === 2 && <div className="v3-panel-section"><label>ROLES</label><div className="v3-roster-list">{starters.slice(0, 6).map((player) => <SpatialButton key={player.id} focusKey={`ROLE_${player.id}`} className={`v3-roster-row ${state.captainId === player.id ? 'active' : ''}`} onPress={() => setState((s) => ({ ...s, captainId: player.id }))}><span>{player.number}</span><strong>{player.name}</strong><small>{state.captainId === player.id ? 'CAPITÁN' : player.position}</small></SpatialButton>)}</div></div>}{tab === 3 && <div className="v3-panel-section"><label>INSTRUCCIÓN · {selected.position}</label>{['POSICIÓN NATURAL','APOYO EQUILIBRADO','INCORPORARSE','QUEDARSE ATRÁS','PRESIÓN INTENSA'].map((instruction) => <SpatialButton key={instruction} focusKey={`INSTR_${instruction}`} className="v3-instruction">{instruction}<b>›</b></SpatialButton>)}</div>}</aside></section><div className="v3-next"><SpatialButton focusKey="GP_CONTINUE" className="v3-next-button" onPress={onContinue}>AJUSTES DEL PARTIDO <b>→</b></SpatialButton></div><FooterHints build="MIT PITCH + NORIGIN SPATIAL NAV"/></main>;
}

function Settings({ state, setState, onContinue, engineReady }: { state: GameState; setState: Dispatch<SetStateAction<GameState>>; onContinue: () => void; engineReady: boolean }) {
  useInitialFocus(`SET_DURATION_${state.match.duration}`);
  const setMatch = (key: string, value: string|number) => setState((s) => ({ ...s, match: { ...s.match, [key]: value } }));
  const rows: { key: string; label: string; value: string|number; options: (string|number)[] }[] = [
    { key: 'duration', label: 'DURACIÓN', value: state.match.duration, options: [4,6,8,10,12] },
    { key: 'difficulty', label: 'DIFICULTAD', value: state.match.difficulty, options: ['Aficionado','Profesional','Clase Mundial','Leyenda'] },
    { key: 'speed', label: 'VELOCIDAD', value: state.match.speed, options: ['Lenta','Normal','Rápida'] },
    { key: 'weather', label: 'CLIMA', value: state.match.weather, options: ['Despejado','Nublado','Lluvia'] },
    { key: 'time', label: 'HORA', value: state.match.time, options: ['Día','Atardecer','Noche'] },
    { key: 'camera', label: 'CÁMARA', value: state.match.camera, options: ['Transmisión','Cooperativa','Dinámica','Lateral'] },
  ];
  return <main className="v3-screen v3-match-settings"><div className="v3-stars"/><TopChrome section="JUGAR" step="04 / AJUSTES" engineReady={engineReady}/><section className="v3-settings-layout"><div className="v3-match-poster"><div className="v3-poster-crests"><TeamCrest team={state.homeTeam} giant/><b>VS</b><TeamCrest team={state.awayTeam} giant/></div><h2>{state.homeTeam.name}<small>CONTRA</small>{state.awayTeam.name}</h2><p>{state.match.stadium} · {state.match.weather} · {state.match.time}</p></div><div className="v3-settings-board">{rows.map((row) => <div className="v3-setting-block" key={row.key}><label>{row.label}</label><div>{row.options.map((option) => <SpatialButton key={String(option)} focusKey={`SET_${row.key.toUpperCase()}_${option}`} className={`v3-setting-choice ${row.value === option ? 'active' : ''}`} onPress={() => setMatch(row.key, option)}>{option}</SpatialButton>)}</div></div>)}</div></section><div className="v3-next"><SpatialButton focusKey="SET_CONTINUE" className="v3-next-button" onPress={onContinue}>IR AL TÚNEL <b>→</b></SpatialButton></div><FooterHints/></main>;
}

function Tunnel({ state, engineReady, refreshRuntime }: { state: GameState; engineReady: boolean; refreshRuntime: () => Promise<void> }) {
  const [launching, setLaunching] = useState(false);
  const [message, setMessage] = useState(engineReady ? 'MOTOR 3D LISTO' : 'MOTOR 3D NO DISPONIBLE');
  useInitialFocus(engineReady ? 'TUNNEL_PLAY' : 'TUNNEL_RETRY', engineReady);
  useEffect(() => setMessage(engineReady ? 'MOTOR 3D LISTO' : 'MOTOR 3D NO DISPONIBLE'), [engineReady]);
  const play = async () => {
    setLaunching(true); setMessage('INICIANDO 11 VS 11...');
    const result = await launchMatch(state);
    setMessage(result.message || (result.ok ? 'PARTIDO INICIADO' : 'NO SE PUDO INICIAR'));
    if (!result.ok) setLaunching(false);
  };
  return <main className="v3-screen v3-tunnel"><div className="v3-tunnel-light left"/><div className="v3-tunnel-light right"/><TopChrome section="JUGAR" step="05 / PREVIA" engineReady={engineReady}/><section className="v3-tunnel-stage"><div className="v3-tunnel-club home"><Jersey team={state.homeTeam} kit={state.homeKit} large/><span>LOCAL</span><h1>{state.homeTeam.name}</h1><p>{formations.find((f) => f.id === state.formation)?.label} · {state.tactic}</p></div><div className="v3-tunnel-core"><small>CENTELLA MATCHDAY</small><b>VS</b><div className={`v3-runtime-pill ${engineReady ? 'ready' : ''}`}>{message}</div><p>{state.match.stadium}<br/>{state.match.weather} · {state.match.time} · {state.match.duration} MIN</p>{engineReady ? <SpatialButton focusKey="TUNNEL_PLAY" className="v3-kickoff" disabled={launching} onPress={() => void play()}>{launching ? 'INICIANDO...' : 'JUGAR PARTIDO'}<b>▶</b></SpatialButton> : <SpatialButton focusKey="TUNNEL_RETRY" className="v3-kickoff secondary" onPress={() => void refreshRuntime()}>VOLVER A COMPROBAR<b>↻</b></SpatialButton>}</div><div className="v3-tunnel-club away"><Jersey team={state.awayTeam} kit={state.awayKit} large/><span>VISITANTE</span><h1>{state.awayTeam.name}</h1><p>{state.match.difficulty} · {state.match.camera}</p></div></section><FooterHints/></main>;
}

export default function AppV3() {
  const [screen, setScreen] = useState<Screen>('splash');
  const [engineReady, setEngineReady] = useState(false);
  const [gameplanTab, setGameplanTab] = useState(0);
  const [state, setState] = useState<GameState>(() => ({
    homeTeam: teams[0], awayTeam: teams[10], homeKit: 0, awayKit: 1, formation: '433', captainId: teams[0].players[8].id, penaltyId: teams[0].players[9].id,
    tactic: 'Equilibrado', width: 50, depth: 55,
    match: { duration: 6, difficulty: 'Profesional', weather: 'Despejado', stadium: 'Estadio Centella', time: 'Noche', camera: 'Transmisión', speed: 'Normal' },
  }));
  const [lineup, setLineup] = useState<string[]>(() => teams[0].players.map((player) => player.id));

  const refreshRuntime = useCallback(async () => {
    const result = await runtimeState();
    setEngineReady(Boolean(result.ready));
  }, []);

  useEffect(() => { void refreshRuntime(); }, [refreshRuntime]);
  useEffect(() => {
    setLineup(state.homeTeam.players.map((player) => player.id));
    setState((s) => ({ ...s, captainId: state.homeTeam.players[8].id, penaltyId: state.homeTeam.players[9].id }));
  }, [state.homeTeam.id]);

  const goBack = useCallback(() => {
    const back: Record<Screen, Screen> = { splash: 'splash', home: 'splash', teams: 'home', kits: 'teams', gameplan: 'kits', settings: 'gameplan', tunnel: 'settings' };
    setScreen((current) => back[current]);
  }, []);

  const shoulder = useCallback((delta: -1 | 1) => {
    if (screen !== 'gameplan') return;
    setGameplanTab((current) => (current + delta + 4) % 4);
  }, [screen]);
  useSpatialGamepad(goBack, shoulder);

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Backspace') { event.preventDefault(); goBack(); }
      if (screen === 'gameplan' && (event.key === 'q' || event.key === 'Q')) setGameplanTab((current) => (current + 3) % 4);
      if (screen === 'gameplan' && (event.key === 'e' || event.key === 'E')) setGameplanTab((current) => (current + 1) % 4);
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [goBack, screen]);

  return <div className="v3-root">
    {screen === 'splash' && <Splash onContinue={() => setScreen('home')}/>} 
    {screen === 'home' && <Home onQuickMatch={() => setScreen('teams')} engineReady={engineReady}/>} 
    {screen === 'teams' && <TeamSelect state={state} setState={setState} onContinue={() => setScreen('kits')} engineReady={engineReady}/>} 
    {screen === 'kits' && <Kits state={state} setState={setState} onContinue={() => setScreen('gameplan')} engineReady={engineReady}/>} 
    {screen === 'gameplan' && <GamePlan state={state} setState={setState} lineup={lineup} setLineup={setLineup} tab={gameplanTab} setTab={setGameplanTab} onContinue={() => setScreen('settings')} engineReady={engineReady}/>} 
    {screen === 'settings' && <Settings state={state} setState={setState} onContinue={() => setScreen('tunnel')} engineReady={engineReady}/>} 
    {screen === 'tunnel' && <Tunnel state={state} engineReady={engineReady} refreshRuntime={refreshRuntime}/>} 
  </div>;
}
