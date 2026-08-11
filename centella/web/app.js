(() => {
  "use strict";

  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];
  const screen = $("#screen"), intro = $("#introScreen"), toast = $("#toast");
  const enginePill = $("#enginePill"), runtimeLabel = $("#runtimeLabel");
  let runtimeReady = false, introActive = true, current = "play", previous = [];
  let focusIndex = 0, lastPad = {}, lastAxis = 0;

  const leagues = [
    {id:"nova", country:"Venezuela", name:"LIGA NOVA", color:"#2691ff", teams:["centella","aurora","caribe","llanos"]},
    {id:"iberia", country:"España", name:"LIGA IBERIA", color:"#ffca4b", teams:["atlas","realazul","puerto","montana"]},
    {id:"europe", country:"Europa", name:"SUPERLIGA EURO", color:"#8e7dff", teams:["volt","nord","royal","union"]}
  ];
  const teams = {
    centella:{name:"CENTELLA FC",abbr:"CEN",crest:"ϟ",primary:"#168cff",secondary:"#061325",rating:81},
    aurora:{name:"AURORA SC",abbr:"AUR",crest:"A",primary:"#e84dff",secondary:"#25052d",rating:79},
    caribe:{name:"CARIBE 1908",abbr:"CAR",crest:"C",primary:"#12d9ad",secondary:"#03211b",rating:78},
    llanos:{name:"LLANOS UNITED",abbr:"LLU",crest:"L",primary:"#ffb53d",secondary:"#291804",rating:77},
    atlas:{name:"ATLAS MADRID",abbr:"ATM",crest:"A",primary:"#f13c45",secondary:"#280408",rating:83},
    realazul:{name:"REAL AZUL",abbr:"RAZ",crest:"R",primary:"#f4f6ff",secondary:"#172e6d",rating:84},
    puerto:{name:"PUERTO FC",abbr:"PFC",crest:"P",primary:"#25b9ff",secondary:"#06233a",rating:80},
    montana:{name:"MONTAÑA CF",abbr:"MCF",crest:"M",primary:"#53cb69",secondary:"#0b2510",rating:79},
    volt:{name:"VOLT UNITED",abbr:"VLT",crest:"V",primary:"#f3f5f8",secondary:"#11151c",rating:82},
    nord:{name:"NORD CITY",abbr:"NOR",crest:"N",primary:"#75d8ff",secondary:"#061a29",rating:81},
    royal:{name:"ROYAL 04",abbr:"R04",crest:"R",primary:"#ffd447",secondary:"#271f03",rating:80},
    union:{name:"UNION RED",abbr:"UNR",crest:"U",primary:"#e73548",secondary:"#25070b",rating:79}
  };

  const firstNames = ["Mateo","Diego","Samuel","Adrián","Nicolás","Gabriel","Bruno","Lucas","Thiago","Daniel","Alejandro","Marco","Iván","Emilio","Santiago","Leo","Tomás","Ángel","Rafael","Julián"];
  const lastNames = ["Rivas","Suárez","Campos","Silva","Méndez","Torres","Paredes","Vega","Salas","Mora","Navarro","Costa","Ferrer","Luna","Pinto","Reyes","Acosta","León","Molina","Soto"];
  const positions = ["POR","LD","DFC","DFC","LI","MCD","MC","MC","ED","DC","EI","POR","DFC","LD","LI","MC","MCO","ED","EI","DC","DC","MCD"];
  function makeSquad(teamId) {
    const seed = Object.keys(teams).indexOf(teamId)+1, base=teams[teamId].rating;
    return positions.map((pos,i)=>(
      {id:`${teamId}-${i}`, name:`${firstNames[(i*3+seed)%firstNames.length]} ${lastNames[(i*5+seed)%lastNames.length]}`,
      pos, number:i<11?i+1:i+12, ovr:Math.max(66,Math.min(89,base + ((i*7+seed)%9)-4-(i>10?2:0))),
      pace:65+((i*9+seed)%26), shot:58+((i*7+seed)%29), pass:61+((i*5+seed)%27),
      dribble:60+((i*11+seed)%28), defend:55+((i*13+seed)%31), physical:60+((i*4+seed)%28)}));
  }
  Object.keys(teams).forEach(id=>teams[id].squad=makeSquad(id));

  const formations = {
    "4-3-3":[["POR",50,88],["LI",16,68],["DFC",38,70],["DFC",62,70],["LD",84,68],["MC",28,47],["MCD",50,54],["MC",72,47],["EI",18,23],["DC",50,15],["ED",82,23]],
    "4-2-3-1":[["POR",50,88],["LI",16,68],["DFC",38,70],["DFC",62,70],["LD",84,68],["MCD",38,51],["MCD",62,51],["EI",20,31],["MCO",50,35],["ED",80,31],["DC",50,15]],
    "4-4-2":[["POR",50,88],["LI",16,68],["DFC",38,70],["DFC",62,70],["LD",84,68],["MI",18,43],["MC",40,49],["MC",60,49],["MD",82,43],["DC",40,19],["DC",60,19]],
    "3-5-2":[["POR",50,88],["DFC",28,70],["DFC",50,72],["DFC",72,70],["MI",12,47],["MC",34,49],["MCD",50,56],["MC",66,49],["MD",88,47],["DC",40,18],["DC",60,18]]
  };

  const state = {
    mode:"quick", league:"nova", home:"centella", away:"volt", formation:"4-3-3",
    squadOrder:teams.centella.squad.map(p=>p.id), selectedPlayer:0,
    tactics:{style:"EQUILIBRADO", width:50, depth:55, buildup:"EQUILIBRADO", chance:"PASE DIRECTO"},
    roles:{captain:0, leftFK:8, rightFK:10, penalties:9, corners:7},
    instructions:{striker:"QUEDARSE EN EL CENTRO", wingers:"DESMARCARSE", fullbacks:"INCORPORARSE"},
    settings:{difficulty:"PROFESIONAL", minutes:10, speed:"NORMAL", weather:"DESPEJADO", time:"NOCHE", stadium:"CENTELLA ARENA", camera:"DINÁMICA", competitive:true},
    master:{club:"centella", day:1, budget:24500000, objective:"CLASIFICAR A COMPETICIÓN CONTINENTAL"},
    tournament:"COPA CENTELLA"
  };

  const esc = s => String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const team = id => teams[id];
  const league = id => leagues.find(x=>x.id===id) || leagues[0];
  const crest = (id,size="lg") => `<span class="crest ${size}" style="--c:${team(id).primary};--c2:${team(id).secondary}">${esc(team(id).crest)}</span>`;
  const rating = n => `<span class="rating">${n}</span>`;
  function toastMsg(msg,error=false){toast.textContent=msg;toast.className=`toast show${error?" error":""}`;clearTimeout(toastMsg.t);toastMsg.t=setTimeout(()=>toast.className="toast",3000);}
  function save(){localStorage.setItem("centella-football-state",JSON.stringify(state));}
  try { Object.assign(state, JSON.parse(localStorage.getItem("centella-football-state")||"{}")); } catch(_) {}

  function push(view){ if(current!==view) previous.push(current); current=view; render(); }
  function back(){ current=previous.pop()||"play"; render(); }
  function sectionTitle(kicker,title,sub=""){return `<div class="section-title"><small>${kicker}</small><h1>${title}</h1>${sub?`<p>${sub}</p>`:""}</div>`;}

  function renderPlay(){
    const modes=[
      ["quick","PARTIDO RÁPIDO","Sal al campo ahora","EXHIBICIÓN","setup"],
      ["master","LIGA MÁSTER 2.0","Construye una era","CARRERA","master"],
      ["competition","COMPETICIONES","Copa, liga y cuadro","TORNEOS","competitions"],
      ["training","ENTRENAMIENTO","Domina el balón","ACADEMIA","training"],
      ["coop","CO-OP LOCAL","Juega en el sofá","2–4 JUGADORES","setup"]
    ];
    return `<div class="play-layout">
      <div class="play-heading"><span class="season">CENTELLA 27</span><h1>JUGAR</h1><p>Elige cómo quieres vivir el partido.</p></div>
      <div class="mode-carousel">${modes.map((m,i)=>`<button class="mode-tile ${i===0?"featured":""}" data-action="mode" data-mode="${m[0]}" data-target="${m[4]}">
        <div class="tile-art art-${m[0]}"><span>${i+1}</span><i></i></div><small>${m[3]}</small><strong>${m[1]}</strong><p>${m[2]}</p><b>ENTRAR →</b>
      </button>`).join("")}</div>
      <aside class="continue-card"><small>ÚLTIMA CONFIGURACIÓN</small><div>${crest(state.home,"sm")}<b>${team(state.home).name}</b><span>VS</span>${crest(state.away,"sm")}<b>${team(state.away).name}</b></div><button data-screen="prematch">CONTINUAR PARTIDO →</button></aside>
    </div>`;
  }

  function teamPicker(side){
    const id=state[side], lg=league(state.league);
    return `<article class="team-picker ${side}">
      <small>${side==="home"?"LOCAL":"VISITANTE"}</small>
      ${crest(id)}<h2>${team(id).name}</h2>
      <div class="stars">${"★".repeat(Math.round(team(id).rating/20))}</div>
      <div class="team-ratings"><span>ATA <b>${team(id).rating+1}</b></span><span>MED <b>${team(id).rating}</b></span><span>DEF <b>${team(id).rating-1}</b></span></div>
      <div class="picker-controls"><button data-action="cycle-team" data-side="${side}" data-dir="-1">‹</button><span>${lg.name}</span><button data-action="cycle-team" data-side="${side}" data-dir="1">›</button></div>
    </article>`;
  }
  function renderSetup(){
    return `<div class="setup-layout">
      ${sectionTitle("PARTIDO RÁPIDO","SELECCIÓN DE EQUIPOS","Liga, club, equipación y lado.")}
      <div class="league-selector"><button data-action="cycle-league" data-dir="-1">‹</button><div><small>${league(state.league).country}</small><b>${league(state.league).name}</b></div><button data-action="cycle-league" data-dir="1">›</button></div>
      <div class="versus-grid">${teamPicker("home")}<div class="versus-mark"><small>${state.mode==="coop"?"CO-OP LOCAL":"EXHIBICIÓN"}</small><b>VS</b><span>${state.settings.stadium}</span></div>${teamPicker("away")}</div>
      <div class="setup-actions"><button class="secondary" data-screen="play">← VOLVER</button><button data-screen="squad">GESTIÓN DEL EQUIPO</button><button data-screen="match-settings">AJUSTES DEL PARTIDO</button><button class="primary" data-screen="prematch">CONTINUAR →</button></div>
    </div>`;
  }

  function currentSquad(){ return team(state.home).squad; }
  function orderedSquad(){
    const map=new Map(currentSquad().map(p=>[p.id,p]));
    const ids=state.squadOrder.filter(id=>map.has(id));
    currentSquad().forEach(p=>{if(!ids.includes(p.id))ids.push(p.id);});
    state.squadOrder=ids;
    return ids.map(id=>map.get(id));
  }
  function renderPitchPlayers(){
    const sq=orderedSquad(), layout=formations[state.formation]||formations["4-3-3"];
    return layout.map((slot,i)=>{const p=sq[i];return `<button class="player-chip ${state.selectedPlayer===i?"selected":""}" style="left:${slot[1]}%;top:${slot[2]}%" data-action="select-player" data-index="${i}">
      <span class="mini-shirt">${p.number}</span><b>${esc(p.name.split(" ").pop())}</b><small>${p.pos} ${p.ovr}</small></button>`}).join("");
  }
  function playerPanel(p){
    return `<aside class="player-panel"><div class="player-card-head">${crest(state.home,"sm")}<div><small>${p.pos} · #${p.number}</small><h2>${esc(p.name)}</h2></div>${rating(p.ovr)}</div>
      <div class="attribute-grid">${[["RIT",p.pace],["TIR",p.shot],["PAS",p.pass],["REG",p.dribble],["DEF",p.defend],["FIS",p.physical]].map(x=>`<div><span>${x[0]}</span><b>${x[1]}</b><i style="--v:${x[1]}%"></i></div>`).join("")}</div>
      <button data-action="swap-player">CAMBIAR JUGADOR</button><button data-action="move-position">EDITAR POSICIÓN</button>
    </aside>`;
  }
  function renderSquad(){
    const sq=orderedSquad(), p=sq[state.selectedPlayer]||sq[0];
    const tabs=[["squad","FORMACIÓN"],["tactics","TÁCTICAS"],["roles","ROLES"],["instructions","INSTRUCCIONES"]];
    return `<div class="management-layout">
      <div class="management-top">${sectionTitle("GESTIÓN DEL EQUIPO",team(state.home).name,"Once, posiciones, suplentes y plan de partido.")}
        <div class="management-tabs">${tabs.map(t=>`<button class="${current===t[0]?"active":""}" data-screen="${t[0]}">${t[1]}</button>`).join("")}</div>
        <label class="formation-select">FORMACIÓN <select data-setting="formation">${Object.keys(formations).map(f=>`<option ${f===state.formation?"selected":""}>${f}</option>`).join("")}</select></label>
      </div>
      <div class="pitch"><div class="pitch-lines-ui"></div>${renderPitchPlayers()}</div>
      ${playerPanel(p)}
      <div class="bench"><small>SUPLENTES / RESERVAS</small><div>${sq.slice(11).map((x,i)=>`<button class="bench-player" data-action="bench-select" data-index="${i+11}"><b>${x.pos}</b><span>${esc(x.name)}</span>${rating(x.ovr)}</button>`).join("")}</div></div>
      <div class="management-actions"><button class="secondary" data-screen="setup">← EQUIPOS</button><button class="primary" data-screen="prematch">CONFIRMAR ONCE →</button></div>
    </div>`;
  }

  function sliderRow(label,key,val){return `<label class="slider-row"><span>${label}<b>${val}</b></span><input type="range" min="1" max="100" value="${val}" data-tactic="${key}"></label>`;}
  function renderTactics(){
    return `<div class="panel-screen">${sectionTitle("PLAN DE PARTIDO","TÁCTICAS","Define cómo se comportará tu equipo.")}
      <div class="subtabs"><button data-screen="squad">FORMACIÓN</button><button class="active">TÁCTICAS</button><button data-screen="roles">ROLES</button><button data-screen="instructions">INSTRUCCIONES</button></div>
      <div class="tactic-columns"><div class="glass-panel"><h3>DEFENSA</h3><label>ESTILO<select data-tactic-select="style">${["EQUILIBRADO","PRESIÓN TRAS PÉRDIDA","PRESIÓN CONSTANTE","REPLEGAR"].map(v=>`<option ${state.tactics.style===v?"selected":""}>${v}</option>`)}</select></label>${sliderRow("ANCHURA","width",state.tactics.width)}${sliderRow("PROFUNDIDAD","depth",state.tactics.depth)}</div>
      <div class="glass-panel"><h3>ATAQUE</h3><label>CONSTRUCCIÓN<select data-tactic-select="buildup">${["EQUILIBRADO","CONTRAATAQUE","SALIDA LENTA"].map(v=>`<option ${state.tactics.buildup===v?"selected":""}>${v}</option>`)}</select></label><label>CREACIÓN<select data-tactic-select="chance">${["PASE DIRECTO","POSESIÓN","CARRERAS HACIA DELANTE"].map(v=>`<option ${state.tactics.chance===v?"selected":""}>${v}</option>`)}</select></label><div class="tactic-map"><span></span><i></i><b></b></div></div></div>
      <div class="bottom-actions"><button data-screen="squad">← ONCE</button><button class="primary" data-screen="prematch">GUARDAR PLAN →</button></div></div>`;
  }
  function roleSelect(label,key){
    const sq=orderedSquad(); return `<label><span>${label}</span><select data-role="${key}">${sq.slice(0,11).map((p,i)=>`<option value="${i}" ${Number(state.roles[key])===i?"selected":""}>${p.number} · ${esc(p.name)}</option>`).join("")}</select></label>`;
  }
  function renderRoles(){
    return `<div class="panel-screen">${sectionTitle("PLAN DE PARTIDO","ROLES","Capitán y especialistas a balón parado.")}
      <div class="subtabs"><button data-screen="squad">FORMACIÓN</button><button data-screen="tactics">TÁCTICAS</button><button class="active">ROLES</button><button data-screen="instructions">INSTRUCCIONES</button></div>
      <div class="roles-grid">${roleSelect("CAPITÁN","captain")}${roleSelect("TIRO LIBRE IZQ.","leftFK")}${roleSelect("TIRO LIBRE DER.","rightFK")}${roleSelect("PENALES","penalties")}${roleSelect("CÓRNERS","corners")}</div>
      <div class="bottom-actions"><button data-screen="squad">← ONCE</button><button class="primary" data-screen="prematch">GUARDAR ROLES →</button></div></div>`;
  }
  function renderInstructions(){
    const rows=[["DELANTERO","striker",["QUEDARSE EN EL CENTRO","CAER A BANDAS","FALSO 9"]],["EXTREMOS","wingers",["DESMARCARSE","VENIR A RECIBIR","APOYO EQUILIBRADO"]],["LATERALES","fullbacks",["INCORPORARSE","QUEDARSE ATRÁS","ATAQUE EQUILIBRADO"]]];
    return `<div class="panel-screen">${sectionTitle("PLAN DE PARTIDO","INSTRUCCIONES","Órdenes individuales por líneas.")}
      <div class="subtabs"><button data-screen="squad">FORMACIÓN</button><button data-screen="tactics">TÁCTICAS</button><button data-screen="roles">ROLES</button><button class="active">INSTRUCCIONES</button></div>
      <div class="instruction-grid">${rows.map(r=>`<label><b>${r[0]}</b><select data-instruction="${r[1]}">${r[2].map(v=>`<option ${state.instructions[r[1]]===v?"selected":""}>${v}</option>`).join("")}</select><p>La orden se aplica a los jugadores de esta línea durante el partido.</p></label>`).join("")}</div>
      <div class="bottom-actions"><button data-screen="squad">← ONCE</button><button class="primary" data-screen="prematch">GUARDAR →</button></div></div>`;
  }

  function settingSelect(label,key,vals){
    return `<label class="setting-row"><span>${label}</span><select data-match-setting="${key}">${vals.map(v=>`<option ${String(state.settings[key])===String(v)?"selected":""}>${v}</option>`).join("")}</select></label>`;
  }
  function renderMatchSettings(){
    return `<div class="panel-screen">${sectionTitle("PARTIDO","AJUSTES","Configura la experiencia antes de entrar al campo.")}
      <div class="settings-grid"><div class="glass-panel"><h3>JUGABILIDAD</h3>${settingSelect("DIFICULTAD","difficulty",["AMATEUR","PROFESIONAL","TOP PLAYER","LEYENDA"])}${settingSelect("DURACIÓN","minutes",[4,6,8,10,12,15])}${settingSelect("VELOCIDAD","speed",["LENTA","NORMAL","RÁPIDA"])}<label class="toggle-row"><span>MODO COMPETITIVO</span><input type="checkbox" data-match-toggle="competitive" ${state.settings.competitive?"checked":""}></label></div>
      <div class="glass-panel"><h3>PRESENTACIÓN</h3>${settingSelect("ESTADIO","stadium",["CENTELLA ARENA","METRO DOME","ESTADIO DEL LLANO","NOVA PARK"])}${settingSelect("HORA","time",["DÍA","TARDE","NOCHE"])}${settingSelect("CLIMA","weather",["DESPEJADO","NUBLADO","LLUVIA"])}${settingSelect("CÁMARA","camera",["DINÁMICA","TRANSMISIÓN","COOPERATIVA","CLÁSICA"])}</div></div>
      <div class="bottom-actions"><button data-screen="setup">← EQUIPOS</button><button class="primary" data-screen="prematch">APLICAR →</button></div></div>`;
  }

  function renderPrematch(){
    const h=team(state.home),a=team(state.away);
    return `<div class="prematch">
      <div class="match-banner"><small>${league(state.league).name} · ${state.settings.stadium}</small><h1>DÍA DE PARTIDO</h1><p>${state.settings.time} · ${state.settings.weather} · ${state.settings.difficulty} · ${state.settings.minutes} MIN</p></div>
      <div class="prematch-vs"><div>${crest(state.home)}<h2>${h.name}</h2><span>${state.formation}</span></div><b>VS</b><div>${crest(state.away)}<h2>${a.name}</h2><span>CPU</span></div></div>
      <div class="prematch-menu"><button data-screen="squad">GESTIÓN DEL EQUIPO<small>Once · táctica · roles</small></button><button data-screen="match-settings">AJUSTES<small>Duración · dificultad · cámara</small></button><button class="primary huge" id="playButton" data-action="launch">JUGAR PARTIDO <b>▶</b><small id="playStatus">${runtimeReady?"MOTOR LISTO":"MOTOR NO DISPONIBLE"}</small></button></div>
    </div>`;
  }

  function renderMaster(){
    const t=team(state.master.club), sq=t.squad;
    return `<div class="master-home">${sectionTitle("LIGA MÁSTER 2.0",t.name,"Temporada 2027 · Jornada "+state.master.day)}
      <div class="master-grid"><button class="master-hero" data-screen="prematch"><small>PRÓXIMO PARTIDO</small><div>${crest(state.master.club)}<b>${t.name}</b><span>VS</span>${crest("aurora")}<b>${team("aurora").name}</b></div><strong>JUGAR JORNADA →</strong></button>
      <button class="master-card" data-screen="squad"><small>PLANTILLA</small><strong>GESTIÓN DEL EQUIPO</strong><p>${sq.length} jugadores · ${state.formation}</p></button>
      <button class="master-card" data-screen="transfers"><small>MERCADO</small><strong>TRANSFERENCIAS</strong><p>Buscar · negociar · lista de deseos</p></button>
      <button class="master-card" data-screen="standings"><small>COMPETICIÓN</small><strong>CLASIFICACIÓN</strong><p>Tabla · calendario · resultados</p></button>
      <button class="master-card"><small>CLUB</small><strong>FINANZAS</strong><p>Presupuesto $${(state.master.budget/1e6).toFixed(1)} M</p></button>
      <button class="master-card"><small>DESARROLLO</small><strong>CANTERA</strong><p>Juveniles · planes de desarrollo</p></button>
      <button class="master-card"><small>DIRECTIVA</small><strong>OBJETIVOS</strong><p>${state.master.objective}</p></button></div>
    </div>`;
  }
  function renderTransfers(){
    const pool=Object.keys(teams).filter(x=>x!==state.master.club).flatMap(id=>teams[id].squad.slice(0,5).map(p=>({...p,club:id,value:(p.ovr-60)*550000}))).sort((a,b)=>b.ovr-a.ovr);
    return `<div class="panel-screen">${sectionTitle("LIGA MÁSTER","CENTRO DE TRANSFERENCIAS","Explora jugadores y construye tu plantilla.")}
      <div class="transfer-toolbar"><input id="playerSearch" placeholder="Buscar jugador o posición"><select><option>TODAS LAS POSICIONES</option><option>DC</option><option>MC</option><option>DFC</option><option>POR</option></select><span>PRESUPUESTO <b>$${(state.master.budget/1e6).toFixed(1)} M</b></span></div>
      <div class="transfer-list">${pool.slice(0,18).map(p=>`<button class="transfer-row" data-action="scout" data-player="${p.id}"><span>${p.pos}</span><b>${esc(p.name)}</b><small>${team(p.club).abbr}</small>${rating(p.ovr)}<em>$${(p.value/1e6).toFixed(1)} M</em><i>NEGOCIAR →</i></button>`).join("")}</div>
      <div class="bottom-actions"><button data-screen="master">← CENTRAL</button></div></div>`;
  }
  function renderStandings(){
    const ids=league(state.league).teams;
    return `<div class="panel-screen">${sectionTitle("LIGA MÁSTER","CLASIFICACIÓN",league(state.league).name)}
      <div class="standings">${ids.concat(["volt","nord","royal","union"]).map((id,i)=>`<div><b>${i+1}</b>${crest(id,"xs")}<span>${team(id).name}</span><small>PJ ${7-i%3}</small><strong>${18-i*2}</strong></div>`).join("")}</div>
      <div class="bottom-actions"><button data-screen="master">← CENTRAL</button></div></div>`;
  }
  function renderCompetitions(){
    const comps=[["COPA CENTELLA","Eliminación directa","16 CLUBES"],["LIGA NOVA","Temporada completa","12 CLUBES"],["COPA CONTINENTAL","Grupos + eliminatorias","24 CLUBES"],["TORNEO PERSONALIZADO","Crea tus reglas","4–32 CLUBES"]];
    return `<div class="competition-screen">${sectionTitle("COMPETICIONES","ELIGE EL TROFEO","Copa, liga o torneo personalizado.")}
      <div class="competition-cards">${comps.map((c,i)=>`<button data-action="competition" data-name="${c[0]}"><div class="trophy">${i===0?"♛":i===1?"⬢":i===2?"◇":"+"}</div><small>${c[2]}</small><strong>${c[0]}</strong><p>${c[1]}</p><b>CONFIGURAR →</b></button>`).join("")}</div>
      <div class="bracket-preview"><span>OCTAVOS</span><i></i><span>CUARTOS</span><i></i><span>SEMIS</span><i></i><span>FINAL</span></div></div>`;
  }
  function renderTraining(){
    const drills=[["LIBRE","Muévete, pasa, regatea y dispara","11_vs_11_easy_stochastic"],["ATAQUE","Finalización y uno contra uno","academy_run_to_score"],["PASE","Posesión y circulación","academy_pass_and_shoot_with_keeper"],["DEFENSA","Temporización y recuperación","academy_run_to_score_with_keeper"]];
    return `<div class="training-screen">${sectionTitle("ACADEMIA","ENTRENAMIENTO","Entra al césped sin esperar un partido.")}
      <div class="drills">${drills.map((d,i)=>`<button data-action="training" data-level="${d[2]}"><span>0${i+1}</span><strong>${d[0]}</strong><p>${d[1]}</p><b>ENTRAR AL CAMPO ▶</b></button>`).join("")}</div></div>`;
  }
  function renderCustomize(){
    return `<div class="panel-screen">${sectionTitle("CENTELLA ID","PERSONALIZAR","Tu juego, tu club, tu forma de jugar.")}
      <div class="settings-grid"><div class="glass-panel"><h3>CONTROLES</h3><label class="setting-row"><span>ESQUEMA</span><select><option>CLÁSICA</option><option>ALTERNATIVA</option></select></label><p class="note">Teclado y mandos Xbox/PlayStation son detectados por la experiencia de menú; el motor recibe el dispositivo al entrar al campo.</p></div>
      <div class="glass-panel"><h3>VÍDEO Y CÁMARA</h3>${settingSelect("CÁMARA","camera",["DINÁMICA","TRANSMISIÓN","COOPERATIVA","CLÁSICA"])}<label class="setting-row"><span>RENDER ESCALADO</span><select><option>75% · RECOMENDADO HD 530</option><option>100%</option><option>60%</option></select></label></div></div></div>`;
  }

  const renderers={play:renderPlay,setup:renderSetup,squad:renderSquad,tactics:renderTactics,roles:renderRoles,instructions:renderInstructions,"match-settings":renderMatchSettings,prematch:renderPrematch,master:renderMaster,transfers:renderTransfers,standings:renderStandings,competitions:renderCompetitions,training:renderTraining,customize:renderCustomize};
  function render(){
    screen.classList.add("changing");
    requestAnimationFrame(()=>{screen.innerHTML=(renderers[current]||renderPlay)(); screen.classList.remove("changing"); bindDynamic(); syncNav(); focusIndex=0; focus(0);});
    save();
  }
  function syncNav(){
    const map={setup:"play",squad:"play",tactics:"play",roles:"play",instructions:"play","match-settings":"play",prematch:"play",transfers:"master",standings:"master"};
    $$("#mainNav button").forEach(b=>b.classList.toggle("active",b.dataset.screen===(map[current]||current)));
  }
  function bindDynamic(){
    $$('[data-screen]',screen).forEach(b=>b.onclick=()=>push(b.dataset.screen));
    $$('[data-action]',screen).forEach(b=>b.onclick=()=>action(b));
    $$('select[data-setting]').forEach(s=>s.onchange=()=>{state[s.dataset.setting]=s.value;render();});
    $$('[data-tactic]').forEach(i=>i.oninput=()=>{state.tactics[i.dataset.tactic]=Number(i.value);i.previousElementSibling.querySelector("b").textContent=i.value;save();});
    $$('[data-tactic-select]').forEach(s=>s.onchange=()=>{state.tactics[s.dataset.tacticSelect]=s.value;save();});
    $$('[data-role]').forEach(s=>s.onchange=()=>{state.roles[s.dataset.role]=Number(s.value);save();});
    $$('[data-instruction]').forEach(s=>s.onchange=()=>{state.instructions[s.dataset.instruction]=s.value;save();});
    $$('[data-match-setting]').forEach(s=>s.onchange=()=>{const k=s.dataset.matchSetting;state.settings[k]=k==="minutes"?Number(s.value):s.value;save();});
    $$('[data-match-toggle]').forEach(s=>s.onchange=()=>{state.settings[s.dataset.matchToggle]=s.checked;save();});
  }
  async function action(el){
    const a=el.dataset.action;
    if(a==="mode"){state.mode=el.dataset.mode;if(state.mode==="coop")state.settings.competitive=false;push(el.dataset.target);return;}
    if(a==="cycle-league"){
      let i=leagues.findIndex(x=>x.id===state.league);i=(i+Number(el.dataset.dir)+leagues.length)%leagues.length;state.league=leagues[i].id;
      state.home=leagues[i].teams[0];state.away=leagues[i].teams[1];state.squadOrder=team(state.home).squad.map(p=>p.id);state.selectedPlayer=0;render();return;
    }
    if(a==="cycle-team"){
      const side=el.dataset.side, ids=league(state.league).teams.concat(Object.keys(teams).filter(x=>!league(state.league).teams.includes(x)));
      let i=ids.indexOf(state[side]);i=(i+Number(el.dataset.dir)+ids.length)%ids.length;state[side]=ids[i];
      if(side==="home"){state.squadOrder=team(state.home).squad.map(p=>p.id);state.selectedPlayer=0;} render();return;
    }
    if(a==="select-player"||a==="bench-select"){state.selectedPlayer=Number(el.dataset.index);render();return;}
    if(a==="swap-player"){
      const sq=orderedSquad(); if(state.selectedPlayer<11&&sq.length>11){[state.squadOrder[state.selectedPlayer],state.squadOrder[11]]=[state.squadOrder[11],state.squadOrder[state.selectedPlayer]];toastMsg("Jugador cambiado con el primer suplente.");render();} return;
    }
    if(a==="move-position"){toastMsg("Selecciona otro jugador y usa CAMBIAR JUGADOR para intercambiar posiciones; el editor de coordenadas libres se añadirá sobre esta misma vista.");return;}
    if(a==="competition"){state.tournament=el.dataset.name;toastMsg(`${state.tournament} seleccionado. El próximo partido utilizará tu configuración actual.`);push("setup");return;}
    if(a==="scout"){toastMsg("Jugador añadido al centro de negociación.");return;}
    if(a==="training"){await launch({level:el.dataset.level,training:true});return;}
    if(a==="launch"){await launch({});return;}
  }

  async function callApi(method,...args){if(!window.pywebview?.api?.[method])throw new Error("Puente nativo no disponible");return window.pywebview.api[method](...args);}
  async function refreshRuntime(){
    try{const r=await callApi("runtime_state");runtimeReady=!!r.ready;updateRuntime();}
    catch(e){runtimeReady=false;updateRuntime();}
  }
  function updateRuntime(){
    enginePill.textContent=runtimeReady?"MOTOR · LISTO":"MOTOR · NO DISPONIBLE";enginePill.className=`engine-pill ${runtimeReady?"ready":"error"}`;
    runtimeLabel.textContent=runtimeReady?"MOTOR · LISTO":"MOTOR · NO DISPONIBLE";
    const p=$("#playStatus");if(p)p.textContent=runtimeReady?"MOTOR LISTO · ENTRAR AL CAMPO":"MOTOR NATIVO NO CARGADO";
  }
  async function launch(extra){
    if(!runtimeReady){toastMsg("El módulo nativo de Gameplay Football todavía no carga en este Python.",true);return;}
    const payload={...state.settings,home:state.home,away:state.away,formation:state.formation,mode:state.mode,level:extra.level||"",training:!!extra.training,local_players:state.mode==="coop"?2:1,versus:state.mode==="coop"};
    const btn=$("#playButton");if(btn)btn.classList.add("loading");
    try{const r=await callApi("play_config",payload);toastMsg(r.message||"Partido iniciado",!r.ok);if(!r.ok){runtimeReady=false;updateRuntime();}}
    catch(e){toastMsg(String(e),true);}
    finally{if(btn)btn.classList.remove("loading");}
  }

  function focusables(){return $$("button:not([disabled]),select:not([disabled]),input:not([disabled])",screen).filter(x=>x.offsetParent!==null);}
  function focus(i){const f=focusables();if(!f.length)return;$$('.ui-focused').forEach(x=>x.classList.remove("ui-focused"));focusIndex=(i+f.length)%f.length;f[focusIndex].classList.add("ui-focused");try{f[focusIndex].focus({preventScroll:true});}catch(_){f[focusIndex].focus();}}
  function move(d){focus(focusIndex+d);}
  function activate(){const f=focusables()[focusIndex];if(f&&f.tagName!=="SELECT"&&f.tagName!=="INPUT")f.click();}
  function dismissIntro(){if(!introActive)return;introActive=false;intro.classList.add("hidden");render();}
  $("#continueButton").onclick=dismissIntro;
  document.addEventListener("keydown",e=>{
    if(introActive){e.preventDefault();dismissIntro();return;}
    if(["ArrowRight","ArrowDown"].includes(e.key)){e.preventDefault();move(1);}
    else if(["ArrowLeft","ArrowUp"].includes(e.key)){e.preventDefault();move(-1);}
    else if(e.key==="Enter"||e.key===" "){e.preventDefault();activate();}
    else if(e.key==="Escape"||e.key==="Backspace"){e.preventDefault();back();}
    else if(e.key.toLowerCase()==="q"||e.key.toLowerCase()==="e"){const n=$$("#mainNav button");let i=n.findIndex(x=>x.classList.contains("active"));i=(i+(e.key.toLowerCase()==="q"?-1:1)+n.length)%n.length;push(n[i].dataset.screen);}
  });
  $$("#mainNav [data-screen],.brand[data-screen]").forEach(b=>b.onclick=()=>push(b.dataset.screen));
  $("#fullscreenButton").onclick=()=>callApi("toggle_fullscreen").catch(()=>{});
  $("#closeButton").onclick=()=>callApi("close").catch(()=>{});

  function pressed(p,i){const k=`${p.index}:${i}`,v=!!p.buttons[i]?.pressed,o=!!lastPad[k];lastPad[k]=v;return v&&!o;}
  function poll(now){
    const p=navigator.getGamepads?.()[0];if(p){
      if(introActive&&p.buttons.some(b=>b.pressed))dismissIntro();
      else if(!introActive){
        if(pressed(p,0))activate();if(pressed(p,1))back();if(pressed(p,4)){const n=$$("#mainNav button");let i=n.findIndex(x=>x.classList.contains("active"));push(n[(i-1+n.length)%n.length].dataset.screen);}
        if(pressed(p,5)){const n=$$("#mainNav button");let i=n.findIndex(x=>x.classList.contains("active"));push(n[(i+1)%n.length].dataset.screen);}
        if(pressed(p,12)||pressed(p,14))move(-1);if(pressed(p,13)||pressed(p,15))move(1);
        const ax=p.axes[0]||0,ay=p.axes[1]||0;if(now-lastAxis>190&&(Math.abs(ax)>.65||Math.abs(ay)>.65)){move(ax>0||ay>0?1:-1);lastAxis=now;}
      }
    }requestAnimationFrame(poll);
  }
  window.addEventListener("pywebviewready",refreshRuntime);
  if(!window.pywebview){runtimeLabel.textContent="MOTOR · PREVISUALIZACIÓN";}
  render(); requestAnimationFrame(poll);
})();