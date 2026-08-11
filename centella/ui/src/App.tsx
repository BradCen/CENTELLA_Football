import { useCallback, useEffect, useMemo, useState } from 'react';
import { formations, teams } from './data';
import { launchMatch, runtimeState } from './bridge';
import { focusOnHover, useGameNavigation } from './navigation';
import type { FormationId, GameState, Player, Screen, Team } from './types';

const kitNames = ['LOCAL', 'VISITANTE', 'ALTERNATIVA'];
const kitColors = (team: Team, index: number) => {
  const options = [
    [team.primary, team.secondary],
    [team.secondary, team.primary],
    [team.accent, team.primary],
  ];
  return options[index] ?? options[0];
};

function Button({ children, className = '', onClick, disabled = false }: { children: React.ReactNode; className?: string; onClick?: () => void; disabled?: boolean }) {
  return <button data-focusable="true" onMouseEnter={focusOnHover} className={`focusable ${className}`} onClick={onClick} disabled={disabled}>{children}</button>;
}

function TopBar({ title, step }: { title: string; step?: string }) {
  return <header className="topbar">
    <div className="brand-lockup"><span className="bolt">ϟ</span><span>CENTELLA</span><small>FOOTBALL</small></div>
    <div className="screen-title">{title}</div>
    <div className="step-label">{step ?? '2027 // BUILD 01'}</div>
  </header>;
}

function Hints({ extra }: { extra?: string }) {
  return <footer className="hints">
    <span><kbd>↕↔</kbd> NAVEGAR</span><span><kbd>ENTER</kbd> ACEPTAR</span><span><kbd>ESC</kbd> ATRÁS</span>
    <span><kbd>✕ / A</kbd> ACEPTAR</span><span><kbd>○ / B</kbd> ATRÁS</span>{extra && <span>{extra}</span>}
  </footer>;
}

function Splash({ onContinue }: { onContinue: () => void }) {
  useEffect(() => {
    const key = () => onContinue();
    window.addEventListener('keydown', key, { once: true });
    const id = window.setInterval(() => {
      const pad = navigator.getGamepads?.().find(Boolean);
      if (pad?.buttons.some((b) => b.pressed)) { clearInterval(id); onContinue(); }
    }, 100);
    return () => { window.removeEventListener('keydown', key); clearInterval(id); };
  }, [onContinue]);

  return <main className="screen splash-screen">
    <div className="stadium-glow" />
    <div className="splash-mark"><div className="mega-bolt">ϟ</div><h1>CENTELLA</h1><p>FOOTBALL</p></div>
    <div className="press-any">PRESIONA CUALQUIER BOTÓN</div>
    <div className="legal">CENTELLA TECHNOLOGIES · PROTOTIPO DE DESARROLLO</div>
  </main>;
}

function Home({ onQuickMatch }: { onQuickMatch: () => void }) {
  return <main className="screen home-screen">
    <TopBar title="INICIO" />
    <section className="home-stage">
      <div className="hero-copy">
        <span className="eyebrow">TEMPORADA 2027</span>
        <h1>EL PARTIDO<br/><em>EMPIEZA AQUÍ.</em></h1>
        <p>Un recorrido construido primero para jugar: seleccionar, preparar y entrar al campo.</p>
      </div>
      <div className="mode-rail">
        <Button className="mode-card primary" onClick={onQuickMatch}>
          <span className="mode-index">01</span>
          <span className="mode-kicker">JUGAR AHORA</span>
          <strong>PARTIDO RÁPIDO</strong>
          <small>Clubes · alineaciones · tácticas · 11v11</small>
          <span className="mode-arrow">→</span>
        </Button>
        <div className="mode-card ghost"><span className="mode-index">02</span><span className="mode-kicker">PRÓXIMA FASE</span><strong>LIGA MÁSTER</strong><small>Gestión total del club</small></div>
        <div className="mode-card ghost"><span className="mode-index">03</span><span className="mode-kicker">PRÓXIMA FASE</span><strong>SER LEYENDA</strong><small>Construye una carrera</small></div>
      </div>
    </section>
    <Hints extra="L1/R1 · LB/RB  CAMBIAR SECCIÓN" />
  </main>;
}

function TeamBadge({ team, large = false }: { team: Team; large?: boolean }) {
  return <div className={`team-badge ${large ? 'large' : ''}`} style={{ '--team-a': team.primary, '--team-b': team.secondary } as React.CSSProperties}>
    <span>{team.short}</span>
  </div>;
}

function TeamSelect({ home, away, onHome, onAway, onContinue }: { home: Team; away: Team; onHome: (t: Team) => void; onAway: (t: Team) => void; onContinue: () => void }) {
  const [side, setSide] = useState<'home' | 'away'>('home');
  const [league, setLeague] = useState('TODAS');
  const leagues = ['TODAS', ...Array.from(new Set(teams.map((t) => t.league)))];
  const visible = league === 'TODAS' ? teams : teams.filter((t) => t.league === league);
  const select = (team: Team) => {
    if (side === 'home') { onHome(team); setSide('away'); }
    else onAway(team);
  };

  return <main className="screen selection-screen">
    <TopBar title="PARTIDO RÁPIDO" step="01 / EQUIPOS" />
    <section className="versus-strip">
      <Button className={`side-panel ${side === 'home' ? 'selected' : ''}`} onClick={() => setSide('home')}>
        <span>LOCAL</span><TeamBadge team={home} large/><strong>{home.name}</strong><small>{home.league}</small>
      </Button>
      <div className="vs-mark">VS</div>
      <Button className={`side-panel ${side === 'away' ? 'selected' : ''}`} onClick={() => setSide('away')}>
        <span>VISITANTE</span><TeamBadge team={away} large/><strong>{away.name}</strong><small>{away.league}</small>
      </Button>
    </section>
    <section className="team-browser">
      <div className="filter-row">{leagues.map((name) => <Button key={name} className={`filter-chip ${league === name ? 'active' : ''}`} onClick={() => setLeague(name)}>{name}</Button>)}</div>
      <div className="team-grid">{visible.map((team) => {
        const chosen = (side === 'home' ? home.id : away.id) === team.id;
        return <Button key={team.id} className={`team-card ${chosen ? 'chosen' : ''}`} onClick={() => select(team)}>
          <TeamBadge team={team}/><div><strong>{team.name}</strong><small>{team.country} · {team.league}</small></div><b>{team.rating}</b>
        </Button>;
      })}</div>
    </section>
    <div className="continue-dock"><Button className="cta" onClick={onContinue} disabled={home.id === away.id}>CONTINUAR <span>→</span></Button></div>
    <Hints />
  </main>;
}

function Jersey({ team, kit }: { team: Team; kit: number }) {
  const [a, b] = kitColors(team, kit);
  return <div className="jersey" style={{ '--kit-a': a, '--kit-b': b } as React.CSSProperties}><div className="jersey-neck"/><span>{team.short}</span></div>;
}

function KitSelect({ home, away, homeKit, awayKit, setHomeKit, setAwayKit, onContinue }: { home: Team; away: Team; homeKit: number; awayKit: number; setHomeKit: (n:number)=>void; setAwayKit:(n:number)=>void; onContinue:()=>void }) {
  return <main className="screen kit-screen">
    <TopBar title="EQUIPACIONES" step="02 / KITS" />
    <section className="kit-stage">
      <div className="kit-team"><span>LOCAL</span><h2>{home.name}</h2><Jersey team={home} kit={homeKit}/><div className="kit-options">{kitNames.map((name,i)=><Button key={name} className={`kit-chip ${homeKit===i?'active':''}`} onClick={()=>setHomeKit(i)}>{name}</Button>)}</div></div>
      <div className="kit-center"><span>EVITA COINCIDENCIAS</span><div className="tunnel-line"/><strong>{home.short}</strong><i>VS</i><strong>{away.short}</strong></div>
      <div className="kit-team"><span>VISITANTE</span><h2>{away.name}</h2><Jersey team={away} kit={awayKit}/><div className="kit-options">{kitNames.map((name,i)=><Button key={name} className={`kit-chip ${awayKit===i?'active':''}`} onClick={()=>setAwayKit(i)}>{name}</Button>)}</div></div>
    </section>
    <div className="continue-dock"><Button className="cta" onClick={onContinue}>GAME PLAN <span>→</span></Button></div><Hints />
  </main>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="stat"><span>{label}</span><div><i style={{ width: `${value}%` }}/></div><b>{value}</b></div>;
}

function PitchPlayer({ player, x, y, selected, captain, onSelect, onDragStart, onDrop }: { player: Player; x:number; y:number; selected:boolean; captain:boolean; onSelect:()=>void; onDragStart:()=>void; onDrop:()=>void }) {
  return <button draggable data-focusable="true" onMouseEnter={focusOnHover} onDragStart={onDragStart} onDragOver={(e)=>e.preventDefault()} onDrop={onDrop} onClick={onSelect} className={`pitch-player ${selected?'selected':''}`} style={{ left:`${x}%`, top:`${y}%` }}>
    <span className="rating">{player.rating}</span><span className="shirt">{player.number}</span><strong>{player.name.split(' ').pop()}</strong><small>{captain?'C · ':''}{player.position}</small>
  </button>;
}

function GamePlan({ state, setState, lineup, setLineup, onContinue }: { state: GameState; setState: React.Dispatch<React.SetStateAction<GameState>>; lineup: string[]; setLineup: React.Dispatch<React.SetStateAction<string[]>>; onContinue:()=>void }) {
  const [tab, setTab] = useState(0);
  const [selectedId, setSelectedId] = useState(lineup[0]);
  const [dragged, setDragged] = useState<string | null>(null);
  const playersById = useMemo(() => new Map(state.homeTeam.players.map((p)=>[p.id,p])), [state.homeTeam]);
  const starters = lineup.slice(0,11).map((id)=>playersById.get(id)!).filter(Boolean);
  const bench = lineup.slice(11).map((id)=>playersById.get(id)!).filter(Boolean);
  const selected = playersById.get(selectedId) ?? starters[0];
  const coords = formations[state.formation];
  const tabs = ['FORMACIÓN','TÁCTICAS','ROLES','INSTRUCCIONES'];

  const swap = (target: string) => {
    if (!dragged || dragged === target) return;
    setLineup((current) => {
      const next = [...current]; const a = next.indexOf(dragged); const b = next.indexOf(target);
      if (a >= 0 && b >= 0) [next[a],next[b]]=[next[b],next[a]];
      return next;
    });
    setDragged(null);
  };

  return <main className="screen gameplan-screen">
    <TopBar title="GAME PLAN" step="03 / ALINEACIÓN" />
    <div className="gameplan-tabs">{tabs.map((name,i)=><Button key={name} className={`tab ${tab===i?'active':''}`} onClick={()=>setTab(i)}>{name}</Button>)}</div>
    <section className="gameplan-layout">
      <div className="pitch-wrap">
        <div className="pitch">
          <div className="pitch-lines"><div className="center-circle"/><div className="box top"/><div className="box bottom"/></div>
          {starters.map((p,i)=><PitchPlayer key={p.id} player={p} x={coords[i][0]} y={coords[i][1]} selected={selectedId===p.id} captain={state.captainId===p.id} onSelect={()=>setSelectedId(p.id)} onDragStart={()=>setDragged(p.id)} onDrop={()=>swap(p.id)}/>)}
        </div>
        <div className="bench"><span className="bench-label">SUPLENTES</span>{bench.map((p)=><button key={p.id} draggable data-focusable="true" onMouseEnter={focusOnHover} onDragStart={()=>setDragged(p.id)} onDragOver={(e)=>e.preventDefault()} onDrop={()=>swap(p.id)} onClick={()=>setSelectedId(p.id)} className={`bench-player ${selectedId===p.id?'selected':''}`}><b>{p.rating}</b><span>{p.position}</span><strong>{p.name.split(' ').pop()}</strong></button>)}</div>
      </div>
      <aside className="plan-panel">
        <div className="player-card"><div className="player-rating">{selected.rating}</div><div><span>{selected.position} · #{selected.number}</span><h2>{selected.name}</h2></div></div>
        <div className="stats"><Stat label="RIT" value={selected.pace}/><Stat label="TIR" value={selected.shot}/><Stat label="PAS" value={selected.pass}/><Stat label="REG" value={selected.dribble}/><Stat label="DEF" value={selected.defense}/><Stat label="FIS" value={selected.physical}/></div>
        {tab===0 && <div className="panel-section"><label>FORMACIÓN</label><div className="option-grid">{(['433','4231','442','352'] as FormationId[]).map((f)=><Button key={f} className={state.formation===f?'active':''} onClick={()=>setState(s=>({...s,formation:f}))}>{f==='433'?'4-3-3':f==='4231'?'4-2-3-1':f==='442'?'4-4-2':'3-5-2'}</Button>)}</div><p>Arrastra jugadores entre campo y banquillo para intercambiarlos.</p></div>}
        {tab===1 && <div className="panel-section"><label>ESTILO DE EQUIPO</label><div className="option-grid">{['Equilibrado','Posesión','Vertical','Contraataque'].map((t)=><Button key={t} className={state.tactic===t?'active':''} onClick={()=>setState(s=>({...s,tactic:t}))}>{t}</Button>)}</div><label>ANCHURA <b>{state.width}</b></label><input type="range" min="20" max="80" value={state.width} onChange={(e)=>setState(s=>({...s,width:+e.target.value}))}/><label>PROFUNDIDAD <b>{state.depth}</b></label><input type="range" min="20" max="90" value={state.depth} onChange={(e)=>setState(s=>({...s,depth:+e.target.value}))}/></div>}
        {tab===2 && <div className="panel-section"><label>CAPITÁN</label><select value={state.captainId} onChange={(e)=>setState(s=>({...s,captainId:e.target.value}))}>{starters.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select><label>PENALTIS</label><select value={state.penaltyId} onChange={(e)=>setState(s=>({...s,penaltyId:e.target.value}))}>{starters.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></div>}
        {tab===3 && <div className="panel-section"><label>INSTRUCCIÓN · {selected.position}</label><div className="instruction-list"><Button>POSICIÓN NATURAL</Button><Button>APOYO EQUILIBRADO</Button><Button>INCORPORARSE AL ATAQUE</Button><Button>QUEDARSE ATRÁS</Button><Button>PRESIÓN INTENSA</Button></div></div>}
      </aside>
    </section>
    <div className="continue-dock"><Button className="cta" onClick={onContinue}>AJUSTES DEL PARTIDO <span>→</span></Button></div><Hints extra="L1/R1 · LB/RB  PESTAÑAS" />
  </main>;
}

function SettingRow({ label, value, options, setValue }: { label:string; value:string|number; options:(string|number)[]; setValue:(v:any)=>void }) {
  const index = options.indexOf(value);
  const change = (delta:number) => setValue(options[(index+delta+options.length)%options.length]);
  return <div className="setting-row"><div><span>{label}</span><strong>{value}</strong></div><div className="stepper"><Button onClick={()=>change(-1)}>‹</Button><Button onClick={()=>change(1)}>›</Button></div></div>;
}

function MatchSettings({ state, setState, onContinue }: { state:GameState; setState:React.Dispatch<React.SetStateAction<GameState>>; onContinue:()=>void }) {
  const patch = (key:string, value:any) => setState(s=>({...s,match:{...s.match,[key]:value}}));
  return <main className="screen settings-screen"><TopBar title="CONFIGURACIÓN DEL PARTIDO" step="04 / AJUSTES" />
    <section className="settings-layout"><div className="match-card"><div className="mini-versus"><TeamBadge team={state.homeTeam} large/><span>VS</span><TeamBadge team={state.awayTeam} large/></div><h2>{state.homeTeam.name}<br/><em>contra</em><br/>{state.awayTeam.name}</h2><p>{state.match.stadium} · {state.match.weather} · {state.match.time}</p></div>
      <div className="settings-list"><SettingRow label="DURACIÓN" value={state.match.duration} options={[4,6,8,10,12,15]} setValue={(v)=>patch('duration',v)}/><SettingRow label="DIFICULTAD" value={state.match.difficulty} options={['Aficionado','Profesional','Clase Mundial','Leyenda']} setValue={(v)=>patch('difficulty',v)}/><SettingRow label="VELOCIDAD" value={state.match.speed} options={['Lenta','Normal','Rápida']} setValue={(v)=>patch('speed',v)}/><SettingRow label="ESTADIO" value={state.match.stadium} options={['Estadio Centella','Arena Metropolitana','Parque del Sur','Coliseo Azul']} setValue={(v)=>patch('stadium',v)}/><SettingRow label="CLIMA" value={state.match.weather} options={['Despejado','Nublado','Lluvia']} setValue={(v)=>patch('weather',v)}/><SettingRow label="HORA" value={state.match.time} options={['Día','Atardecer','Noche']} setValue={(v)=>patch('time',v)}/><SettingRow label="CÁMARA" value={state.match.camera} options={['Transmisión','Cooperativa','Dinámica','Lateral']} setValue={(v)=>patch('camera',v)}/></div>
    </section><div className="continue-dock"><Button className="cta" onClick={onContinue}>IR AL TÚNEL <span>→</span></Button></div><Hints /></main>;
}

function Tunnel({ state }: { state: GameState }) {
  const [runtime, setRuntime] = useState<{ready:boolean;platform:string}>({ready:false,platform:'...'});
  const [message, setMessage] = useState('COMPROBANDO MOTOR...');
  const [launching, setLaunching] = useState(false);
  const check = useCallback(async()=>{ const result=await runtimeState(); setRuntime(result); setMessage(result.ready?'MOTOR 3D LISTO':'MOTOR 3D NO DISPONIBLE'); },[]);
  useEffect(()=>{ void check(); },[check]);
  const play = async()=>{ setLaunching(true); setMessage('INICIANDO 11 VS 11...'); const result=await launchMatch(state); setMessage(result.message || (result.ok?'PARTIDO INICIADO':'NO SE PUDO INICIAR')); if(!result.ok)setLaunching(false); };
  return <main className="screen tunnel-screen"><TopBar title="PATADA INICIAL" step="05 / PREVIA" />
    <section className="tunnel-stage"><div className="tunnel-team home"><Jersey team={state.homeTeam} kit={state.homeKit}/><span>LOCAL</span><h1>{state.homeTeam.name}</h1><p>{state.formation==='433'?'4-3-3':state.formation==='4231'?'4-2-3-1':state.formation==='442'?'4-4-2':'3-5-2'} · {state.tactic}</p></div><div className="tunnel-core"><div className="competition">CENTELLA MATCHDAY</div><div className="versus-big">VS</div><div className={`engine-pill ${runtime.ready?'ready':'not-ready'}`}>{message}</div><small>{state.match.stadium}<br/>{state.match.weather} · {state.match.time} · {state.match.duration} MIN</small><Button className="kickoff" onClick={play} disabled={!runtime.ready || launching}>{launching?'INICIANDO...':'JUGAR PARTIDO'} <span>▶</span></Button>{!runtime.ready&&<Button className="retry" onClick={()=>void check()}>VOLVER A COMPROBAR MOTOR</Button>}</div><div className="tunnel-team away"><Jersey team={state.awayTeam} kit={state.awayKit}/><span>VISITANTE</span><h1>{state.awayTeam.name}</h1><p>{state.match.difficulty} · {state.match.camera}</p></div></section><Hints /></main>;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('splash');
  const [state, setState] = useState<GameState>(()=>({
    homeTeam:teams[0], awayTeam:teams[10], homeKit:0, awayKit:1, formation:'433', captainId:teams[0].players[8].id, penaltyId:teams[0].players[9].id,
    tactic:'Equilibrado', width:50, depth:55,
    match:{duration:6,difficulty:'Profesional',weather:'Despejado',stadium:'Estadio Centella',time:'Noche',camera:'Transmisión',speed:'Normal'},
  }));
  const [lineup, setLineup] = useState<string[]>(()=>teams[0].players.map(p=>p.id));

  useEffect(()=>{ setLineup(state.homeTeam.players.map(p=>p.id)); setState(s=>({...s,captainId:state.homeTeam.players[8].id,penaltyId:state.homeTeam.players[9].id})); },[state.homeTeam.id]);

  const goBack = useCallback(()=>{
    const back: Record<Screen,Screen> = {splash:'splash',home:'splash',teams:'home',kits:'teams',gameplan:'kits',settings:'gameplan',tunnel:'settings'};
    setScreen(back[screen]);
  },[screen]);
  useGameNavigation(goBack);

  const setHome=(team:Team)=>setState(s=>({...s,homeTeam:team}));
  const setAway=(team:Team)=>setState(s=>({...s,awayTeam:team}));

  return <div className="app-shell">
    <div className="ambient"><i/><i/><i/><i/></div>
    {screen==='splash'&&<Splash onContinue={()=>setScreen('home')}/>} 
    {screen==='home'&&<Home onQuickMatch={()=>setScreen('teams')}/>} 
    {screen==='teams'&&<TeamSelect home={state.homeTeam} away={state.awayTeam} onHome={setHome} onAway={setAway} onContinue={()=>setScreen('kits')}/>} 
    {screen==='kits'&&<KitSelect home={state.homeTeam} away={state.awayTeam} homeKit={state.homeKit} awayKit={state.awayKit} setHomeKit={(n)=>setState(s=>({...s,homeKit:n}))} setAwayKit={(n)=>setState(s=>({...s,awayKit:n}))} onContinue={()=>setScreen('gameplan')}/>} 
    {screen==='gameplan'&&<GamePlan state={state} setState={setState} lineup={lineup} setLineup={setLineup} onContinue={()=>setScreen('settings')}/>} 
    {screen==='settings'&&<MatchSettings state={state} setState={setState} onContinue={()=>setScreen('tunnel')}/>} 
    {screen==='tunnel'&&<Tunnel state={state}/>} 
  </div>;
}
