import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import ExternalLineupPitch from './ExternalLineupPitch';
import { teams } from './data';
import { launchMatch, runtimeState } from './bridge';
import { focusOnHover, useGameNavigation } from './navigation';
import type { FormationId, GameState, Player, Screen, Team } from './types';

const kitNames = ['LOCAL', 'VISITANTE', 'ALTERNATIVA'];

function Button({ children, className = '', onClick, disabled = false }: { children: ReactNode; className?: string; onClick?: () => void; disabled?: boolean }) {
  return <button data-focusable="true" onMouseEnter={focusOnHover} className={`focusable ${className}`} onClick={onClick} disabled={disabled}>{children}</button>;
}

function TopBar({ title, step }: { title: string; step?: string }) {
  return <header className="topbar"><div className="brand-lockup"><span className="bolt">ϟ</span><span>CENTELLA</span><small>FOOTBALL</small></div><div className="screen-title">{title}</div><div className="step-label">{step ?? 'VERTICAL SLICE 02'}</div></header>;
}

function Hints({ extra }: { extra?: string }) {
  return <footer className="hints"><span><kbd>↕↔</kbd> NAVEGAR</span><span><kbd>ENTER</kbd> ACEPTAR</span><span><kbd>ESC</kbd> ATRÁS</span><span><kbd>✕ / A</kbd> ACEPTAR</span><span><kbd>○ / B</kbd> ATRÁS</span>{extra && <span>{extra}</span>}</footer>;
}

function TeamBadge({ team, large = false }: { team: Team; large?: boolean }) {
  return <div className={`team-badge ${large ? 'large' : ''}`} style={{ '--team-a': team.primary, '--team-b': team.secondary } as React.CSSProperties}><span>{team.short}</span></div>;
}

function Jersey({ team, kit }: { team: Team; kit: number }) {
  const options = [[team.primary, team.secondary], [team.secondary, team.primary], [team.accent, team.primary]];
  const [a, b] = options[kit] ?? options[0];
  return <div className="jersey" style={{ '--kit-a': a, '--kit-b': b } as React.CSSProperties}><div className="jersey-neck"/><span>{team.short}</span></div>;
}

function Splash({ onContinue }: { onContinue: () => void }) {
  useEffect(() => {
    const key = () => onContinue();
    window.addEventListener('keydown', key, { once: true });
    let consumed = false;
    const id = window.setInterval(() => {
      if (consumed) return;
      const pad = navigator.getGamepads?.().find(Boolean);
      if (pad?.buttons.some((button) => button.pressed)) { consumed = true; clearInterval(id); onContinue(); }
    }, 90);
    return () => { window.removeEventListener('keydown', key); clearInterval(id); };
  }, [onContinue]);
  return <main className="screen splash-screen"><div className="stadium-glow"/><div className="splash-mark"><div className="mega-bolt">ϟ</div><h1>CENTELLA</h1><p>FOOTBALL</p></div><div className="press-any">PRESIONA CUALQUIER BOTÓN</div><div className="legal">CENTELLA TECHNOLOGIES · UI REACT / WEBVIEW2 / GRF</div></main>;
}

function Home({ onQuickMatch }: { onQuickMatch: () => void }) {
  return <main className="screen home-screen"><TopBar title="JUGAR"/><section className="home-stage"><div className="hero-copy"><span className="eyebrow">CENTELLA MATCHDAY</span><h1>FÚTBOL.<br/><em>SIN RODEOS.</em></h1><p>Elige dos clubes, prepara el once, ajusta la táctica y entra al motor 11v11.</p></div><div className="mode-rail"><Button className="mode-card primary" onClick={onQuickMatch}><span className="mode-index">01</span><span className="mode-kicker">DISPONIBLE</span><strong>PARTIDO RÁPIDO</strong><small>Equipos · kits · Game Plan · GRF</small><span className="mode-arrow">→</span></Button><div className="mode-card ghost"><span className="mode-index">02</span><span className="mode-kicker">BLOQUEADO HASTA VALIDAR UI</span><strong>LIGA MÁSTER</strong><small>No se construye todavía</small></div><div className="mode-card ghost"><span className="mode-index">03</span><span className="mode-kicker">BLOQUEADO HASTA VALIDAR UI</span><strong>SER LEYENDA</strong><small>No se construye todavía</small></div></div></section><Hints/></main>;
}

function TeamSelect({ state, setState, onContinue }: { state: GameState; setState: React.Dispatch<React.SetStateAction<GameState>>; onContinue: () => void }) {
  const [side, setSide] = useState<'home'|'away'>('home');
  const [league, setLeague] = useState('TODAS');
  const leagues = ['TODAS', ...Array.from(new Set(teams.map((team) => team.league)))];
  const visible = league === 'TODAS' ? teams : teams.filter((team) => team.league === league);
  const choose = (team: Team) => {
    setState((current) => side === 'home' ? { ...current, homeTeam: team } : { ...current, awayTeam: team });
    if (side === 'home') setSide('away');
  };
  return <main className="screen selection-screen"><TopBar title="PARTIDO RÁPIDO" step="01 / EQUIPOS"/><section className="versus-strip"><Button className={`side-panel ${side === 'home' ? 'selected' : ''}`} onClick={() => setSide('home')}><span>LOCAL</span><TeamBadge team={state.homeTeam} large/><strong>{state.homeTeam.name}</strong><small>{state.homeTeam.league}</small></Button><div className="vs-mark">VS</div><Button className={`side-panel ${side === 'away' ? 'selected' : ''}`} onClick={() => setSide('away')}><span>VISITANTE</span><TeamBadge team={state.awayTeam} large/><strong>{state.awayTeam.name}</strong><small>{state.awayTeam.league}</small></Button></section><section className="team-browser"><div className="filter-row">{leagues.map((name) => <Button key={name} className={`filter-chip ${league === name ? 'active' : ''}`} onClick={() => setLeague(name)}>{name}</Button>)}</div><div className="team-grid">{visible.map((team) => <Button key={team.id} className={`team-card ${(side === 'home' ? state.homeTeam.id : state.awayTeam.id) === team.id ? 'chosen' : ''}`} onClick={() => choose(team)}><TeamBadge team={team}/><div><strong>{team.name}</strong><small>{team.country} · {team.league}</small></div><b>{team.rating}</b></Button>)}</div></section><div className="continue-dock"><Button className="cta" disabled={state.homeTeam.id === state.awayTeam.id} onClick={onContinue}>EQUIPACIONES <span>→</span></Button></div><Hints/></main>;
}

function Kits({ state, setState, onContinue }: { state: GameState; setState: React.Dispatch<React.SetStateAction<GameState>>; onContinue: () => void }) {
  return <main className="screen kit-screen"><TopBar title="EQUIPACIONES" step="02 / KITS"/><section className="kit-stage"><div className="kit-team"><span>LOCAL</span><h2>{state.homeTeam.name}</h2><Jersey team={state.homeTeam} kit={state.homeKit}/><div className="kit-options">{kitNames.map((name, index) => <Button key={name} className={`kit-chip ${state.homeKit === index ? 'active' : ''}`} onClick={() => setState((s) => ({ ...s, homeKit: index }))}>{name}</Button>)}</div></div><div className="kit-center"><span>IDENTIDAD VISUAL</span><div className="tunnel-line"/><strong>{state.homeTeam.short}</strong><i>VS</i><strong>{state.awayTeam.short}</strong></div><div className="kit-team"><span>VISITANTE</span><h2>{state.awayTeam.name}</h2><Jersey team={state.awayTeam} kit={state.awayKit}/><div className="kit-options">{kitNames.map((name, index) => <Button key={name} className={`kit-chip ${state.awayKit === index ? 'active' : ''}`} onClick={() => setState((s) => ({ ...s, awayKit: index }))}>{name}</Button>)}</div></div></section><div className="continue-dock"><Button className="cta" onClick={onContinue}>GAME PLAN <span>→</span></Button></div><Hints/></main>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="stat"><span>{label}</span><div><i style={{ width: `${value}%` }}/></div><b>{value}</b></div>;
}

function GamePlan({ state, setState, lineup, setLineup, onContinue }: { state: GameState; setState: React.Dispatch<React.SetStateAction<GameState>>; lineup: string[]; setLineup: React.Dispatch<React.SetStateAction<string[]>>; onContinue: () => void }) {
  const [tab, setTab] = useState(0);
  const [selectedId, setSelectedId] = useState(lineup[0]);
  const players = useMemo(() => new Map(state.homeTeam.players.map((player) => [player.id, player])), [state.homeTeam]);
  const starters = lineup.slice(0, 11).map((id) => players.get(id)).filter((player): player is Player => Boolean(player));
  const bench = lineup.slice(11).map((id) => players.get(id)).filter((player): player is Player => Boolean(player));
  const selected = players.get(selectedId) ?? starters[0];
  const selectedIndex = lineup.indexOf(selectedId);
  const selectedIsStarter = selectedIndex >= 0 && selectedIndex < 11;
  const tabs = ['FORMACIÓN', 'TÁCTICAS', 'ROLES', 'INSTRUCCIONES'];
  const substitute = (benchId: string) => {
    if (!selectedIsStarter) { setSelectedId(benchId); return; }
    setLineup((current) => {
      const next = [...current];
      const benchIndex = next.indexOf(benchId);
      if (benchIndex < 11) return next;
      [next[selectedIndex], next[benchIndex]] = [next[benchIndex], next[selectedIndex]];
      return next;
    });
    setSelectedId(benchId);
  };

  return <main className="screen gameplan-screen"><TopBar title="GAME PLAN" step="03 / ALINEACIÓN"/><div className="gameplan-tabs">{tabs.map((name, index) => <Button key={name} className={`tab ${tab === index ? 'active' : ''}`} onClick={() => setTab(index)}>{name}</Button>)}</div><section className="gameplan-layout"><div className="pitch-wrap"><ExternalLineupPitch club={state.homeTeam} starters={starters} formation={state.formation} selectedId={selectedId} captainId={state.captainId} onSelect={setSelectedId}/><div className="bench"><span className="bench-label">SUPLENTES · SELECCIONA TITULAR Y LUEGO SUPLENTE PARA CAMBIAR</span>{bench.map((player) => <button key={player.id} data-focusable="true" onMouseEnter={focusOnHover} onClick={() => substitute(player.id)} className={`bench-player ${selectedId === player.id ? 'selected' : ''}`}><b>{player.rating}</b><span>{player.position}</span><strong>{player.name.split(' ').pop()}</strong></button>)}</div></div><aside className="plan-panel"><div className="integration-chip">MIT COMPONENT · REACT-SOCCER-LINEUP</div><div className="player-card"><div className="player-rating">{selected.rating}</div><div><span>{selected.position} · #{selected.number}</span><h2>{selected.name}</h2></div></div><div className="stats"><Stat label="RIT" value={selected.pace}/><Stat label="TIR" value={selected.shot}/><Stat label="PAS" value={selected.pass}/><Stat label="REG" value={selected.dribble}/><Stat label="DEF" value={selected.defense}/><Stat label="FIS" value={selected.physical}/></div>{tab === 0 && <div className="panel-section"><label>FORMACIÓN</label><div className="option-grid">{(['433','4231','442','352'] as FormationId[]).map((formation) => <Button key={formation} className={state.formation === formation ? 'active' : ''} onClick={() => setState((s) => ({ ...s, formation }))}>{formation === '433' ? '4-3-3' : formation === '4231' ? '4-2-3-1' : formation === '442' ? '4-4-2' : '3-5-2'}</Button>)}</div><p>La cancha ya no es nuestro dibujo manual: ahora usa el componente MIT externo integrado al proyecto.</p></div>}{tab === 1 && <div className="panel-section"><label>ESTILO DE EQUIPO</label><div className="option-grid">{['Equilibrado','Posesión','Vertical','Contraataque'].map((tactic) => <Button key={tactic} className={state.tactic === tactic ? 'active' : ''} onClick={() => setState((s) => ({ ...s, tactic }))}>{tactic}</Button>)}</div><label>ANCHURA <b>{state.width}</b></label><input type="range" min="20" max="80" value={state.width} onChange={(event) => setState((s) => ({ ...s, width: Number(event.target.value) }))}/><label>PROFUNDIDAD <b>{state.depth}</b></label><input type="range" min="20" max="90" value={state.depth} onChange={(event) => setState((s) => ({ ...s, depth: Number(event.target.value) }))}/></div>}{tab === 2 && <div className="panel-section"><label>CAPITÁN</label><select value={state.captainId} onChange={(event) => setState((s) => ({ ...s, captainId: event.target.value }))}>{starters.map((player) => <option key={player.id} value={player.id}>{player.name}</option>)}</select><label>PENALTIS</label><select value={state.penaltyId} onChange={(event) => setState((s) => ({ ...s, penaltyId: event.target.value }))}>{starters.map((player) => <option key={player.id} value={player.id}>{player.name}</option>)}</select></div>}{tab === 3 && <div className="panel-section"><label>INSTRUCCIÓN · {selected.position}</label><div className="instruction-list"><Button>POSICIÓN NATURAL</Button><Button>APOYO EQUILIBRADO</Button><Button>INCORPORARSE</Button><Button>QUEDARSE ATRÁS</Button><Button>PRESIÓN INTENSA</Button></div></div>}</aside></section><div className="continue-dock"><Button className="cta" onClick={onContinue}>AJUSTES DEL PARTIDO <span>→</span></Button></div><Hints extra="L1/R1 · LB/RB  PESTAÑAS"/></main>;
}

function SettingRow({ label, value, options, onChange }: { label: string; value: string|number; options: (string|number)[]; onChange: (value: string|number) => void }) {
  const index = options.indexOf(value);
  const step = (delta: number) => onChange(options[(index + delta + options.length) % options.length]);
  return <div className="setting-row"><div><span>{label}</span><strong>{value}</strong></div><div className="stepper"><Button onClick={() => step(-1)}>‹</Button><Button onClick={() => step(1)}>›</Button></div></div>;
}

function Settings({ state, setState, onContinue }: { state: GameState; setState: React.Dispatch<React.SetStateAction<GameState>>; onContinue: () => void }) {
  const patch = (key: string, value: string|number) => setState((s) => ({ ...s, match: { ...s.match, [key]: value } }));
  return <main className="screen settings-screen"><TopBar title="CONFIGURACIÓN DEL PARTIDO" step="04 / AJUSTES"/><section className="settings-layout"><div className="match-card"><div className="mini-versus"><TeamBadge team={state.homeTeam} large/><span>VS</span><TeamBadge team={state.awayTeam} large/></div><h2>{state.homeTeam.name}<br/><em>contra</em><br/>{state.awayTeam.name}</h2><p>{state.match.stadium} · {state.match.weather} · {state.match.time}</p></div><div className="settings-list"><SettingRow label="DURACIÓN" value={state.match.duration} options={[4,6,8,10,12,15]} onChange={(value) => patch('duration', value)}/><SettingRow label="DIFICULTAD" value={state.match.difficulty} options={['Aficionado','Profesional','Clase Mundial','Leyenda']} onChange={(value) => patch('difficulty', value)}/><SettingRow label="VELOCIDAD" value={state.match.speed} options={['Lenta','Normal','Rápida']} onChange={(value) => patch('speed', value)}/><SettingRow label="ESTADIO" value={state.match.stadium} options={['Estadio Centella','Arena Metropolitana','Parque del Sur','Coliseo Azul']} onChange={(value) => patch('stadium', value)}/><SettingRow label="CLIMA" value={state.match.weather} options={['Despejado','Nublado','Lluvia']} onChange={(value) => patch('weather', value)}/><SettingRow label="HORA" value={state.match.time} options={['Día','Atardecer','Noche']} onChange={(value) => patch('time', value)}/><SettingRow label="CÁMARA" value={state.match.camera} options={['Transmisión','Cooperativa','Dinámica','Lateral']} onChange={(value) => patch('camera', value)}/></div></section><div className="continue-dock"><Button className="cta" onClick={onContinue}>IR AL TÚNEL <span>→</span></Button></div><Hints/></main>;
}

function Tunnel({ state }: { state: GameState }) {
  const [runtime, setRuntime] = useState({ ready: false, platform: '...' });
  const [message, setMessage] = useState('COMPROBANDO MOTOR...');
  const [launching, setLaunching] = useState(false);
  const check = useCallback(async () => { const result = await runtimeState(); setRuntime(result); setMessage(result.ready ? 'MOTOR 3D LISTO' : 'MOTOR 3D NO DISPONIBLE'); }, []);
  useEffect(() => { void check(); }, [check]);
  const play = async () => { setLaunching(true); setMessage('INICIANDO 11 VS 11...'); const result = await launchMatch(state); setMessage(result.message || (result.ok ? 'PARTIDO INICIADO' : 'NO SE PUDO INICIAR')); if (!result.ok) setLaunching(false); };
  return <main className="screen tunnel-screen"><TopBar title="PATADA INICIAL" step="05 / PREVIA"/><section className="tunnel-stage"><div className="tunnel-team home"><Jersey team={state.homeTeam} kit={state.homeKit}/><span>LOCAL</span><h1>{state.homeTeam.name}</h1><p>{state.formation === '433' ? '4-3-3' : state.formation === '4231' ? '4-2-3-1' : state.formation === '442' ? '4-4-2' : '3-5-2'} · {state.tactic}</p></div><div className="tunnel-core"><div className="competition">CENTELLA MATCHDAY</div><div className="versus-big">VS</div><div className={`engine-pill ${runtime.ready ? 'ready' : 'not-ready'}`}>{message}</div><small>{state.match.stadium}<br/>{state.match.weather} · {state.match.time} · {state.match.duration} MIN</small><Button className="kickoff" onClick={play} disabled={!runtime.ready || launching}>{launching ? 'INICIANDO...' : 'JUGAR PARTIDO'} <span>▶</span></Button>{!runtime.ready && <Button className="retry" onClick={() => void check()}>VOLVER A COMPROBAR MOTOR</Button>}</div><div className="tunnel-team away"><Jersey team={state.awayTeam} kit={state.awayKit}/><span>VISITANTE</span><h1>{state.awayTeam.name}</h1><p>{state.match.difficulty} · {state.match.camera}</p></div></section><Hints/></main>;
}

export default function AppV2() {
  const [screen, setScreen] = useState<Screen>('splash');
  const [state, setState] = useState<GameState>(() => ({ homeTeam: teams[0], awayTeam: teams[10], homeKit: 0, awayKit: 1, formation: '433', captainId: teams[0].players[8].id, penaltyId: teams[0].players[9].id, tactic: 'Equilibrado', width: 50, depth: 55, match: { duration: 6, difficulty: 'Profesional', weather: 'Despejado', stadium: 'Estadio Centella', time: 'Noche', camera: 'Transmisión', speed: 'Normal' } }));
  const [lineup, setLineup] = useState<string[]>(() => teams[0].players.map((player) => player.id));
  useEffect(() => { setLineup(state.homeTeam.players.map((player) => player.id)); setState((s) => ({ ...s, captainId: state.homeTeam.players[8].id, penaltyId: state.homeTeam.players[9].id })); }, [state.homeTeam.id]);
  const goBack = useCallback(() => { const back: Record<Screen, Screen> = { splash: 'splash', home: 'splash', teams: 'home', kits: 'teams', gameplan: 'kits', settings: 'gameplan', tunnel: 'settings' }; setScreen(back[screen]); }, [screen]);
  useGameNavigation(goBack);
  return <div className="app-shell v2-shell"><div className="ambient"><i/><i/><i/><i/></div>{screen === 'splash' && <Splash onContinue={() => setScreen('home')}/>} {screen === 'home' && <Home onQuickMatch={() => setScreen('teams')}/>} {screen === 'teams' && <TeamSelect state={state} setState={setState} onContinue={() => setScreen('kits')}/>} {screen === 'kits' && <Kits state={state} setState={setState} onContinue={() => setScreen('gameplan')}/>} {screen === 'gameplan' && <GamePlan state={state} setState={setState} lineup={lineup} setLineup={setLineup} onContinue={() => setScreen('settings')}/>} {screen === 'settings' && <Settings state={state} setState={setState} onContinue={() => setScreen('tunnel')}/>} {screen === 'tunnel' && <Tunnel state={state}/>}</div>;
}
