"""CENTELLA Football Beta Shell v2.

A controller-first product shell layered over the open Gameplay Football / GRF
simulation. The shell never imports GRF itself, so it remains usable while the
native Windows runtime is being repaired.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

from .brand import BRAND
from .content import COMPETITIONS, TEAMS, load_user_content, save_user_content
from .controller import ControllerManager, GAMEPLAY_ACTION_LABELS, InputAction
from .modes import MODES, TABS, Mode
from .runtime import launch_match, open_bootstrap, runtime_summary
from .settings import SETTINGS
from .ui import (
    LOGICAL_SIZE, Viewport, clamp, draw_glow, draw_player_silhouette,
    draw_stadium_scene, draw_text, ease_in_out, ease_out_cubic, font,
    hex_color, rounded_panel,
)

ASSET_DIR = Path(__file__).resolve().parent / "assets"


def load_png(name: str) -> Optional[pygame.Surface]:
    path = ASSET_DIR / name
    if not path.exists():
        return None
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except pygame.error as exc:
        print(f"[CENTELLA UI] {path.name}: {exc}", file=sys.stderr)
        return None


def fit(image: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    iw, ih = image.get_size()
    r = min(max_w / iw, max_h / ih)
    return pygame.transform.smoothscale(image, (max(1, int(iw*r)), max(1, int(ih*r))))


class App:
    def __init__(self) -> None:
        pygame.init(); pygame.font.init(); pygame.joystick.init()
        w = int(SETTINGS.get("display.width", 1600)); h = int(SETTINGS.get("display.height", 900))
        flags = pygame.RESIZABLE | pygame.DOUBLEBUF
        if SETTINGS.get("display.fullscreen", False): flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption("CENTELLA Football — Beta Experience")
        self.viewport = Viewport(self.screen); self.clock = pygame.time.Clock(); self.controller = ControllerManager()
        self.running = True; self.scene = "splash"; self.scene_started = time.perf_counter()
        last_tab = SETTINGS.get("profile.last_tab", "HOME"); self.tab = TABS.index(last_tab) if last_tab in TABS else 0
        self.selected = 0; self.page_cursor = 0; self.detail_mode: Optional[Mode] = None
        self.message = ""; self.message_until = 0.0; self.performance_overlay = False
        self.mouse_regions: List[Tuple[pygame.Rect, str, object]] = []; self.rebinding: Optional[str] = None
        self.runtime_cache: Optional[Dict] = None; self.runtime_cache_at = 0.0
        self.user = load_user_content()
        for key in ("careers", "tournaments", "players", "street_presets", "setpieces"):
            self.user.setdefault(key, [])
        self.quick = {"home":0, "away":1, "minutes":10, "difficulty":"PROFESSIONAL", "time":"NOCHE", "weather":"DESPEJADO", "players":1, "versus":False}
        self.training = 0
        self.training_levels = [
            ("PASE + DEFINICIÓN", "academy_pass_and_shoot_with_keeper"),
            ("CORRER Y DEFINIR", "academy_run_to_score_with_keeper"),
            ("PORTERÍA VACÍA", "academy_empty_goal_close"),
            ("11 vs 11", "11_vs_11_stochastic"),
        ]
        self.career = {"role":0, "team":0, "difficulty":1, "negotiations":1}
        self.street = {"type":0, "surface":0, "size":0, "mixed":True, "rules":0}
        self.tournament = {"format":0, "teams":1, "legs":0, "custom_rules":True}
        self.player = {"position":4, "foot":0, "archetype":1, "number":10}
        self.setpiece = [[530,400],[630,340],[710,455],[800,365],[860,500]]; self.setpiece_selected = 0
        self.symbol = load_png("centella_symbol_white.png"); self.wordmark = load_png("centella_wordmark_white.png")
        self.f12=font(16); self.f16=font(20); self.f20=font(24); self.f24=font(30,True); self.f30=font(38,True)
        self.f40=font(50,True); self.f52=font(64,True); self.f72=font(88,True); self.f96=font(118,True)

    @property
    def elapsed(self): return time.perf_counter()-self.scene_started
    @property
    def tab_name(self): return TABS[self.tab]
    def motion(self): return bool(SETTINGS.get("display.motion", True)) and not bool(SETTINGS.get("accessibility.reduce_motion", False))
    def enter(self, scene, reset=True):
        self.scene=scene; self.scene_started=time.perf_counter(); self.mouse_regions=[]
        if reset: self.page_cursor=0
    def notify(self, text, seconds=3.0): self.message=text; self.message_until=time.perf_counter()+seconds
    def save_user(self): save_user_content(self.user)
    def runtime(self, force=False):
        now=time.monotonic()
        if force or self.runtime_cache is None or now-self.runtime_cache_at>5:
            self.runtime_cache=runtime_summary(); self.runtime_cache_at=now
        return self.runtime_cache
    def set_tab(self, index):
        self.tab=index%len(TABS); self.selected=0; SETTINGS.set("profile.last_tab", self.tab_name); self.enter("hub",False)
    def open_mode(self, mode: Mode):
        self.detail_mode=mode; SETTINGS.set("profile.last_mode",mode.title)
        route={"quick_match":"quick","local_coop":"coop","training":"training","career":"career","street":"street","journey":"journey","online":"online","edit":"edit","player_creator":"player","tournament":"tournament","setpiece":"setpiece","controls":"controls","video":"video","accessibility":"access","workshop":"workshop","doctor":"doctor"}.get(mode.route,"detail")
        self.enter(route)

    def handle_event(self,event):
        if event.type==pygame.QUIT: self.running=False; return
        if event.type==pygame.VIDEORESIZE:
            self.screen=pygame.display.set_mode(event.size,pygame.RESIZABLE|pygame.DOUBLEBUF); self.viewport.screen=self.screen; self.viewport.update(); return
        if self.scene=="controls" and self.rebinding and event.type==pygame.JOYBUTTONDOWN:
            self.controller.rebind_button(self.rebinding,int(event.button)); self.notify(f"{self.rebinding.upper()} = BOTÓN {event.button}"); self.rebinding=None; return
        action=self.controller.translate(event)
        if action: self.handle_action(action)
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            p=self.viewport.mouse_to_logical(event.pos)
            if p: self.handle_click(p)
        if self.scene=="setpiece" and event.type==pygame.MOUSEMOTION and event.buttons[0]:
            p=self.viewport.mouse_to_logical(event.pos)
            if p:
                self.setpiece[self.setpiece_selected][0]=int(clamp(p[0],415,950)); self.setpiece[self.setpiece_selected][1]=int(clamp(p[1],315,730))

    def handle_click(self,pos):
        for rect,kind,payload in reversed(self.mouse_regions):
            if rect.collidepoint(pos):
                if kind=="tab": self.set_tab(int(payload))
                elif kind=="mode": self.open_mode(payload)
                elif kind=="cursor": self.page_cursor=int(payload)
                elif kind=="action": self.handle_action(InputAction(str(payload),source="mouse"))
                return

    def handle_action(self,a:InputAction):
        if a.name=="performance": self.performance_overlay=not self.performance_overlay; return
        if a.name=="doctor": self.enter("doctor"); return
        if a.name=="device_changed": self.notify(f"DISPOSITIVO: {self.controller.primary_name().upper()}"); return
        if self.scene=="splash": self.enter("hub"); return
        if a.name=="back":
            if self.scene=="hub": self.enter("splash")
            else: self.enter("hub")
            return
        if self.scene=="hub": self.action_hub(a); return
        if a.name=="tab_left": self.set_tab(self.tab-1); return
        if a.name=="tab_right": self.set_tab(self.tab+1); return
        getattr(self,f"action_{self.scene}",self.action_detail)(a)

    def action_hub(self,a):
        modes=MODES[self.tab_name]
        if a.name=="left": self.selected=(self.selected-1)%len(modes)
        elif a.name=="right": self.selected=(self.selected+1)%len(modes)
        elif a.name=="up": self.set_tab(self.tab-1)
        elif a.name=="down": self.set_tab(self.tab+1)
        elif a.name=="tab_left": self.set_tab(self.tab-1)
        elif a.name=="tab_right": self.set_tab(self.tab+1)
        elif a.name=="confirm": self.open_mode(modes[self.selected])

    def cycle_row(self,a,rows):
        if a.name=="up": self.page_cursor=(self.page_cursor-1)%rows; return 0
        if a.name=="down": self.page_cursor=(self.page_cursor+1)%rows; return 0
        return -1 if a.name=="left" else 1 if a.name in ("right","confirm") else 0

    def action_quick(self,a): self.quick_common(a,False)
    def action_coop(self,a): self.quick_common(a,True)
    def quick_common(self,a,coop):
        d=self.cycle_row(a,8)
        if not d:return
        row=self.page_cursor
        if row==0:self.quick["home"]=(self.quick["home"]+d)%len(TEAMS)
        elif row==1:self.quick["away"]=(self.quick["away"]+d)%len(TEAMS)
        elif row==2:
            vals=[4,6,8,10,12,15,20]; cur=self.quick["minutes"]; self.quick["minutes"]=vals[(vals.index(cur)+d)%len(vals)] if cur in vals else 10
        elif row==3:
            vals=["AMATEUR","PROFESSIONAL","TOP PLAYER","LEGEND"]; self.quick["difficulty"]=vals[(vals.index(self.quick["difficulty"])+d)%len(vals)]
        elif row==4:
            vals=["DÍA","TARDE","NOCHE"]; self.quick["time"]=vals[(vals.index(self.quick["time"])+d)%len(vals)]
        elif row==5:
            vals=["DESPEJADO","NUBLADO","LLUVIA"]; self.quick["weather"]=vals[(vals.index(self.quick["weather"])+d)%len(vals)]
        elif row==6 and coop:self.quick["versus"]=not self.quick["versus"]
        elif row==7:self.start_match(coop)

    def start_match(self,coop=False):
        if self.quick["home"]==self.quick["away"]:self.quick["away"]=(self.quick["away"]+1)%len(TEAMS)
        SETTINGS.set("gameplay.match_minutes",self.quick["minutes"]); SETTINGS.set("gameplay.difficulty",self.quick["difficulty"])
        players=2 if coop else 1
        ok,msg=launch_match(controller_count=len(self.controller.joysticks),local_players=players,versus=self.quick["versus"] if coop else False)
        self.notify(msg,5)
        if not ok:self.enter("doctor")

    def action_training(self,a):
        if a.name in ("left","up"):self.training=(self.training-1)%len(self.training_levels)
        elif a.name in ("right","down"):self.training=(self.training+1)%len(self.training_levels)
        elif a.name=="confirm":
            ok,msg=launch_match(level=self.training_levels[self.training][1],controller_count=len(self.controller.joysticks));self.notify(msg,5)
            if not ok:self.enter("doctor")

    def action_career(self,a):
        d=self.cycle_row(a,5)
        if not d:return
        if self.page_cursor==0:self.career["role"]=(self.career["role"]+d)%4
        elif self.page_cursor==1:self.career["team"]=(self.career["team"]+d)%len(TEAMS)
        elif self.page_cursor==2:self.career["difficulty"]=(self.career["difficulty"]+d)%4
        elif self.page_cursor==3:self.career["negotiations"]=(self.career["negotiations"]+d)%3
        elif self.page_cursor==4:
            self.user["careers"].append(dict(self.career,created=time.time()));self.save_user();self.notify("CARRERA LOCAL CREADA · HUB DE TEMPORADA ES EL SIGUIENTE MÓDULO")

    def action_street(self,a):
        d=self.cycle_row(a,6)
        if not d:return
        k=self.page_cursor
        if k==0:self.street["type"]=(self.street["type"]+d)%3
        elif k==1:self.street["surface"]=(self.street["surface"]+d)%4
        elif k==2:self.street["size"]=(self.street["size"]+d)%3
        elif k==3:self.street["mixed"]=not self.street["mixed"]
        elif k==4:self.street["rules"]=(self.street["rules"]+d)%4
        else:self.user["street_presets"].append(dict(self.street));self.save_user();self.notify("PRESET STREET/FUTSAL GUARDADO")

    def action_journey(self,a):
        if a.name=="confirm":self.enter("player")

    def action_online(self,a):
        if a.name in ("left","up"):self.page_cursor=(self.page_cursor-1)%3
        elif a.name in ("right","down"):self.page_cursor=(self.page_cursor+1)%3
        elif a.name=="confirm":self.notify("LA RED AÚN NO ESTÁ CONECTADA: ESTA BETA NO FINGE MATCHMAKING.",4)

    def action_edit(self,a):
        if a.name in ("left","up"):self.page_cursor=(self.page_cursor-1)%len(TEAMS)
        elif a.name in ("right","down"):self.page_cursor=(self.page_cursor+1)%len(TEAMS)
        elif a.name=="confirm":
            team=TEAMS[self.page_cursor]; overrides=self.user.setdefault("team_overrides",{}); current=overrides.setdefault(team.key,{})
            colors=[team.primary,"#2359AA","#FFFFFF","#171717","#8B1D2C","#1F6D42","#552A91"]
            cur=current.get("primary",team.primary); current["primary"]=colors[(colors.index(cur)+1)%len(colors)] if cur in colors else team.primary
            self.save_user();self.notify("IDENTIDAD DE EQUIPO GUARDADA")

    def action_player(self,a):
        d=self.cycle_row(a,5)
        if not d:return
        if self.page_cursor==0:self.player["position"]=(self.player["position"]+d)%6
        elif self.page_cursor==1:self.player["foot"]=(self.player["foot"]+d)%2
        elif self.page_cursor==2:self.player["archetype"]=(self.player["archetype"]+d)%5
        elif self.page_cursor==3:self.player["number"]=(self.player["number"]+d-1)%99+1
        else:self.user["players"].append(dict(self.player));self.save_user();self.notify("JUGADOR GUARDADO PARA LEYENDA / STREET")

    def action_tournament(self,a):
        d=self.cycle_row(a,5)
        if not d:return
        if self.page_cursor==0:self.tournament["format"]=(self.tournament["format"]+d)%4
        elif self.page_cursor==1:self.tournament["teams"]=(self.tournament["teams"]+d)%5
        elif self.page_cursor==2:self.tournament["legs"]=(self.tournament["legs"]+d)%2
        elif self.page_cursor==3:self.tournament["custom_rules"]=not self.tournament["custom_rules"]
        else:self.user["tournaments"].append(dict(self.tournament));self.save_user();self.notify("COMPETICIÓN PERSONALIZADA GUARDADA")

    def action_setpiece(self,a):
        if a.name=="tab_left":self.setpiece_selected=(self.setpiece_selected-1)%len(self.setpiece)
        elif a.name=="tab_right":self.setpiece_selected=(self.setpiece_selected+1)%len(self.setpiece)
        elif a.name in ("left","right","up","down"):
            dx=(-8 if a.name=="left" else 8 if a.name=="right" else 0);dy=(-8 if a.name=="up" else 8 if a.name=="down" else 0)
            p=self.setpiece[self.setpiece_selected];p[0]=int(clamp(p[0]+dx,415,950));p[1]=int(clamp(p[1]+dy,315,730))
        elif a.name=="confirm":self.user["setpieces"].append([p[:] for p in self.setpiece]);self.save_user();self.notify("JUGADA PREPARADA GUARDADA")

    def action_controls(self,a):
        if a.name=="up":self.page_cursor=(self.page_cursor-1)%len(GAMEPLAY_ACTION_LABELS)
        elif a.name=="down":self.page_cursor=(self.page_cursor+1)%len(GAMEPLAY_ACTION_LABELS)
        elif a.name=="confirm":
            if not self.controller.connected:self.notify("CONECTA UN MANDO PARA REASIGNAR BOTONES");return
            self.rebinding=GAMEPLAY_ACTION_LABELS[self.page_cursor][0];self.notify("PRESIONA AHORA EL BOTÓN FÍSICO…",5)

    def action_video(self,a):
        d=self.cycle_row(a,6)
        if not d:return
        row=self.page_cursor
        if row==0:SETTINGS.set("display.fullscreen",not SETTINGS.get("display.fullscreen",False));self.notify("SE APLICA AL REINICIAR EL SHELL")
        elif row==1:
            vals=["PERFORMANCE","BALANCED","QUALITY"];cur=SETTINGS.get("display.quality","BALANCED");SETTINGS.set("display.quality",vals[(vals.index(cur)+d)%3])
        elif row==2:
            vals=[.5,.67,.75,.85,1.0];cur=float(SETTINGS.get("display.render_scale",.75));i=min(range(len(vals)),key=lambda n:abs(vals[n]-cur));SETTINGS.set("display.render_scale",vals[(i+d)%len(vals)])
        elif row==3:
            vals=[30,60,90,120,144];cur=int(SETTINGS.get("display.fps_cap",60));i=vals.index(cur) if cur in vals else 1;SETTINGS.set("display.fps_cap",vals[(i+d)%len(vals)])
        elif row==4:SETTINGS.set("display.motion",not SETTINGS.get("display.motion",True))
        else:SETTINGS.set("gameplay.low_latency_experimental",not SETTINGS.get("gameplay.low_latency_experimental",False))

    def action_access(self,a):
        keys=["high_contrast","reduce_motion","large_text","hold_to_confirm"]
        if a.name=="up":self.page_cursor=(self.page_cursor-1)%4
        elif a.name=="down":self.page_cursor=(self.page_cursor+1)%4
        elif a.name in ("left","right","confirm"):
            k=keys[self.page_cursor];SETTINGS.set(f"accessibility.{k}",not SETTINGS.get(f"accessibility.{k}",False))

    def action_workshop(self,a):
        if a.name=="confirm":self.notify("WORKSHOP: ÍNDICE .CFMOD + HASHES PREPARADO COMO ARQUITECTURA; DESCARGA REMOTA AÚN NO CONECTADA.",5)
    def action_doctor(self,a):
        if a.name in ("left","up"):self.page_cursor=(self.page_cursor-1)%2
        elif a.name in ("right","down"):self.page_cursor=(self.page_cursor+1)%2
        elif a.name=="confirm":
            if self.page_cursor==0:self.runtime(True);self.notify("DIAGNÓSTICO ACTUALIZADO")
            else:
                _,msg=open_bootstrap();self.notify(msg,5)
    def action_detail(self,a):
        if a.name=="confirm":self.notify("RUTA DE PRODUCTO REGISTRADA; SU CORE TODAVÍA NO ESTÁ CONECTADO EN ESTA BETA.",4)

    def add_region(self,rect,kind,payload):self.mouse_regions.append((rect.copy(),kind,payload))
    def draw_brand(self,c,x=72,y=55):
        if self.wordmark:
            im=fit(self.wordmark,240,70);c.blit(im,(x,y));draw_text(c,"FOOTBALL",self.f12,BRAND.sapphire_light,(x+2,y+im.get_height()+4))
        else:draw_text(c,"CENTELLA",self.f30,BRAND.white,(x,y));draw_text(c,"FOOTBALL",self.f12,BRAND.sapphire_light,(x,y+44))
    def backdrop(self,c,intensity=.8):draw_stadium_scene(c,self.elapsed,BRAND.sapphire,intensity,self.motion())
    def draw_tabs(self,c):
        x=650
        for i,name in enumerate(TABS):
            sel=i==self.tab;r=draw_text(c,name,self.f16,BRAND.white if sel else BRAND.muted,(x,68))
            if sel:pygame.draw.rect(c,BRAND.sapphire_light,(r.x,r.bottom+10,r.width,4),border_radius=2)
            self.add_region(pygame.Rect(r.x-14,r.y-14,r.width+28,58),"tab",i);x=r.right+44
        draw_text(c,"F2 · CENTELLA LAB",self.f12,BRAND.muted,(1845,78),"topright")
    def draw_splash(self,c):
        t=self.elapsed;self.backdrop(c,.95);draw_player_silhouette(c,1435,1065,1.06,BRAND.sapphire_light,230)
        shade=pygame.Surface(LOGICAL_SIZE,pygame.SRCALPHA);pygame.draw.polygon(shade,(0,0,0,92),[(0,0),(1210,0),(970,1080),(0,1080)]);c.blit(shade,(0,0))
        a=ease_out_cubic((t-.15)/.65);b=ease_out_cubic((t-.55)/.8);p=ease_in_out((t-1.5)/.6)
        if self.symbol:
            im=fit(self.symbol,90,165);im.set_alpha(int(255*a));c.blit(im,im.get_rect(center=(485,385)));draw_glow(c,(485,385),125,BRAND.sapphire,int(70*a))
        if self.wordmark:
            im=fit(self.wordmark,580,165);im.set_alpha(int(255*b));c.blit(im,im.get_rect(midleft=(190,505)))
        else:draw_text(c,"CENTELLA",self.f96,BRAND.white,(190,470),alpha=int(255*b))
        draw_text(c,"F O O T B A L L",self.f24,BRAND.sapphire_light,(196,645),alpha=int(245*b));draw_text(c,"BETA EXPERIENCE",self.f12,BRAND.muted,(200,700),alpha=int(200*b))
        pulse=.62+.38*math.sin(t*3.2) if self.motion() else 1
        rounded_panel(c,pygame.Rect(190,835,520,72),(15,18,27),BRAND.sapphire_light,18,2,int(230*p));draw_text(c,"PRESIONA CUALQUIER BOTÓN",self.f20,BRAND.white,(450,871),"center",int(255*p*pulse));draw_text(c,self.controller.primary_name().upper(),self.f12,BRAND.muted,(450,935),"center",int(230*p))
    def draw_hub(self,c):
        self.backdrop(c,1);self.draw_brand(c);self.draw_tabs(c);draw_player_silhouette(c,1460,1070,.92,BRAND.sapphire_light,235)
        ov=pygame.Surface(LOGICAL_SIZE,pygame.SRCALPHA);pygame.draw.polygon(ov,(0,0,0,94),[(0,130),(1090,130),(850,1080),(0,1080)]);c.blit(ov,(0,0))
        hero={"HOME":("CENTELLA FOOTBALL","EL FÚTBOL RESPONDE A TI."),"PLAY":("JUGAR","ENTRA AL CAMPO."),"CAREER":("CARRERA","CONSTRUYE UNA HISTORIA."),"ONLINE":("ONLINE","COMPITE SIN PAY-TO-WIN."),"CUSTOMIZE":("PERSONALIZAR","TU JUEGO. TUS REGLAS.")}[self.tab_name]
        draw_text(c,hero[0],self.f16,BRAND.sapphire_light,(90,200));draw_text(c,hero[1],self.f52,BRAND.white,(90,240));draw_text(c,"Respuesta directa · balón independiente · defensa manual · rendimiento escalable",self.f16,BRAND.muted,(94,328))
        modes=MODES[self.tab_name];start=max(0,min(self.selected-1,max(0,len(modes)-4)));x=90
        for j,mode in enumerate(modes[start:start+4]):
            idx=start+j;sel=idx==self.selected;w=430 if sel else 350;h=250 if sel else 205;y=690-(h-205);rect=pygame.Rect(x,y,w,h)
            rounded_panel(c,rect,(21,27,41) if sel else (13,17,27),BRAND.sapphire_light if sel else (47,54,70),18,2 if sel else 1,246)
            if sel:pygame.draw.rect(c,BRAND.sapphire,(x,y,w,8),border_radius=4)
            draw_text(c,mode.status,self.f12,BRAND.sapphire_light if sel else BRAND.muted,(x+26,y+24));draw_text(c,mode.title,self.f24 if sel else self.f20,BRAND.white,(x+26,y+61));draw_text(c,mode.subtitle,self.f16,BRAND.muted,(x+26,y+111))
            if sel:draw_text(c,mode.description,self.f12,(184,194,211),(x+26,y+162))
            self.add_region(rect,"mode",mode);x+=w+18
        for i in range(len(modes)):pygame.draw.circle(c,BRAND.sapphire_light if i==self.selected else (78,85,99),(95+i*18,1000),4 if i==self.selected else 3)
        ready=self.runtime().get("ready",False);draw_text(c,"MOTOR LISTO" if ready else "MOTOR REQUIERE REPARACIÓN",self.f12,(105,220,150) if ready else (245,182,69),(90,1032))
    def page_header(self,c,title,subtitle=""):
        self.backdrop(c,.55);shade=pygame.Surface(LOGICAL_SIZE,pygame.SRCALPHA);shade.fill((0,0,0,62));c.blit(shade,(0,0));self.draw_brand(c);self.draw_tabs(c);draw_text(c,title,self.f40,BRAND.white,(90,175));draw_text(c,subtitle,self.f16,BRAND.muted,(94,240));pygame.draw.line(c,BRAND.sapphire,(90,282),(1830,282),2)
    def option(self,c,y,label,value,index):
        sel=self.page_cursor==index;rect=pygame.Rect(90,y,1000,72);rounded_panel(c,rect,(21,27,40) if sel else (13,17,26),BRAND.sapphire_light if sel else (45,51,65),14,2 if sel else 1,245);draw_text(c,label,self.f16,BRAND.white,(118,y+19));draw_text(c,str(value),self.f16,BRAND.sapphire_light,(1050,y+19),"topright");self.add_region(rect,"cursor",index)
    def draw_team_pair(self,c):
        h=TEAMS[self.quick["home"]];a=TEAMS[self.quick["away"]]
        for team,x in ((h,1280),(a,1580)):
            col=hex_color(team.primary);draw_glow(c,(x,505),125,col,75);pygame.draw.circle(c,col,(x,505),78);draw_text(c,team.short,self.f24,BRAND.white,(x,505),"center");draw_text(c,team.name,self.f16,BRAND.white,(x,625),"center");draw_text(c,str(team.rating),self.f30,BRAND.sapphire_light,(x,665),"center")
    def draw_quick(self,c,coop=False):
        self.page_header(c,"CO-OP LOCAL" if coop else "KICK OFF","Configura el partido antes de entrar al motor nativo")
        vals=[TEAMS[self.quick["home"]].name,TEAMS[self.quick["away"]].name,f'{self.quick["minutes"]} MIN',self.quick["difficulty"],self.quick["time"],self.quick["weather"],("VERSUS" if self.quick["versus"] else "MISMO EQUIPO") if coop else "1 JUGADOR","JUGAR PARTIDO"]
        for i,(lab,val) in enumerate(zip(["LOCAL","VISITANTE","DURACIÓN","DIFICULTAD","HORA","CLIMA","LADO LOCAL","INICIAR"],vals)):self.option(c,320+i*78,lab,val,i)
        self.draw_team_pair(c);draw_text(c,f"MANDOS DETECTADOS: {len(self.controller.joysticks)}",self.f16,BRAND.muted,(1190,820))
    def draw_training(self,c):
        self.page_header(c,"ENTRENAMIENTO","Academias existentes del motor GRF accesibles desde la beta");name,_=self.training_levels[self.training];rounded_panel(c,pygame.Rect(90,350,900,300),(14,19,29),BRAND.sapphire_light,22,2,245);draw_text(c,name,self.f40,BRAND.white,(135,405));draw_text(c,"← / →  CAMBIAR EJERCICIO",self.f16,BRAND.muted,(140,510));draw_text(c,"A / ENTER  INICIAR",self.f20,BRAND.sapphire_light,(140,570));draw_player_silhouette(c,1450,930,.72,BRAND.sapphire_light,220)
    def draw_career(self,c):
        self.page_header(c,"LIGA MÁSTER 2.0","DT, Presidente, control completo o carrera cooperativa")
        roles=["DT","PRESIDENTE","CONTROL TOTAL","DT + PRESIDENTE CO-OP"];diffs=["AMATEUR","PROFESSIONAL","TOP PLAYER","LEGEND"];neg=["FLEXIBLES","REALISTAS","ESTRICTAS"]
        vals=[roles[self.career["role"]],TEAMS[self.career["team"]].name,diffs[self.career["difficulty"]],neg[self.career["negotiations"]],"CREAR CARRERA"]
        for i,(l,v) in enumerate(zip(["ROL","CLUB","DIFICULTAD","NEGOCIACIONES","NUEVA PARTIDA"],vals)):self.option(c,335+i*85,l,v,i)
        rounded_panel(c,pygame.Rect(1190,340,630,390),(11,16,25),(51,59,74),22,1,245);draw_text(c,"SIMULACIÓN DE CLUB",self.f20,BRAND.sapphire_light,(1230,380))
        for i,t in enumerate(["Mercado · scouting · contratos","Moral · físico · entrenamiento","Finanzas · estadio · patrocinio","Ruedas de prensa IA: arquitectura prevista","Co-op DT/Presidente: perfil persistente"]):draw_text(c,"●",self.f12,BRAND.sapphire_light,(1230,445+i*52));draw_text(c,t,self.f16,BRAND.white,(1260,438+i*52))
    def draw_street(self,c):
        self.page_header(c,"STREET / FUTSAL","Una rama propia; no es 11v11 encogido")
        vals=[["FUTSAL","STREET","BARRIO"][self.street["type"]],["PARQUET","CONCRETO","ASFALTO","TIERRA"][self.street["surface"]],["5v5","4v4","3v3"][self.street["size"]],"SÍ" if self.street["mixed"] else "NO",["FIFA FUTSAL","LIBRE","SIN SAQUE","ARCOS DE PIEDRA"][self.street["rules"]],"GUARDAR PRESET"]
        for i,(l,v) in enumerate(zip(["MODALIDAD","SUPERFICIE","FORMATO","EQUIPOS MIXTOS","REGLAS","PRESET"],vals)):self.option(c,330+i*82,l,v,i)
        rounded_panel(c,pygame.Rect(1190,335,620,390),(12,17,24),(55,62,74),22,1,245);draw_text(c,"IDENTIDAD",self.f20,BRAND.sapphire_light,(1230,375));draw_text(c,"Fútbol de barrio sin estética arcade.",self.f24,BRAND.white,(1230,425));draw_text(c,"Concreto, asfalto, tierra, muros y focos reales.",self.f16,BRAND.muted,(1230,490));draw_text(c,"Balón y reglas tendrán perfiles propios.",self.f16,BRAND.muted,(1230,528))
    def draw_journey(self,c):
        self.page_header(c,"MODO LEYENDA","Carrera personal + historia emergente");draw_player_silhouette(c,1460,925,.72,BRAND.sapphire_light,230);draw_text(c,"NO ERES UNA CARTA.",self.f52,BRAND.white,(110,380));draw_text(c,"Eres una carrera que cambia con el campo, vestuario, contratos y decisiones.",self.f20,BRAND.muted,(115,475))
        for i,t in enumerate(["Progresión contextual","Contratos y reputación","Eventos no guionizados rígidamente","Street/Futsal conectado a tu perfil","Self-scan facial: pipeline previsto","Cinemática como capa, no como jaula"]):draw_text(c,f"0{i+1}",self.f16,BRAND.sapphire_light,(120,575+i*52));draw_text(c,t,self.f16,BRAND.white,(175,575+i*52))
        draw_text(c,"A / ENTER  ABRIR CREADOR DE JUGADOR",self.f20,BRAND.sapphire_light,(112,930))
    def draw_online(self,c):
        self.page_header(c,"ONLINE","Mismo gameplay offline; cero estadísticas compradas")
        for i,(t,s) in enumerate([("RANKED 1v1","Matchmaking competitivo"),("CLUBS","Un jugador por persona"),("STREET CLUBS","5v5 persistente")]):
            x=90+i*580;sel=i==self.page_cursor;rounded_panel(c,pygame.Rect(x,355,540,315),(20,26,39) if sel else (12,16,25),BRAND.sapphire_light if sel else (47,54,68),22,2 if sel else 1,245);draw_text(c,t,self.f30,BRAND.white,(x+34,395));draw_text(c,s,self.f16,BRAND.muted,(x+34,455));draw_text(c,"ROLLBACK / PREDICTION SPEC",self.f12,BRAND.sapphire_light,(x+34,590))
        draw_text(c,"La red todavía no está conectada al core. Esta beta no simula jugadores online que no existen.",self.f20,BRAND.white,(90,760));draw_text(c,"La siguiente fase de red es transporte + sincronización determinista + matchmaking.",self.f16,BRAND.muted,(90,812))
    def draw_edit(self,c):
        self.page_header(c,"MODO EDICIÓN","Identidad y datos de usuario fuera del código fuente");team=TEAMS[self.page_cursor%len(TEAMS)];ov=self.user.get("team_overrides",{}).get(team.key,{});col=hex_color(ov.get("primary",team.primary));draw_glow(c,(420,520),180,col,85);pygame.draw.circle(c,col,(420,520),115);draw_text(c,team.short,self.f40,BRAND.white,(420,520),"center");draw_text(c,ov.get("name",team.name),self.f40,BRAND.white,(700,420));draw_text(c,team.city.upper(),self.f16,BRAND.muted,(705,490));draw_text(c,f"RATING BASE {team.rating}",self.f20,BRAND.sapphire_light,(705,545));draw_text(c,"← / → EQUIPO   ·   A / ENTER CAMBIAR COLOR",self.f16,BRAND.white,(705,650));draw_text(c,"Los cambios se guardan como datos de usuario para preparar Option Files/Workshop.",self.f16,BRAND.muted,(705,705))
    def draw_player(self,c):
        self.page_header(c,"CREADOR DE JUGADOR","Perfil local para Modo Leyenda y Street");vals=[["POR","DFC","MC","MCO","EXT","DC"][self.player["position"]],["DERECHO","IZQUIERDO"][self.player["foot"]],["TÉCNICO","RÁPIDO","CREADOR","FINALIZADOR","FÍSICO"][self.player["archetype"]],self.player["number"],"GUARDAR JUGADOR"]
        for i,(l,v) in enumerate(zip(["POSICIÓN","PIE","ARQUETIPO","DORSAL","PERFIL"],vals)):self.option(c,340+i*88,l,v,i)
        draw_player_silhouette(c,1450,900,.70,BRAND.sapphire_light,230)
    def draw_tournament(self,c):
        self.page_header(c,"CREADOR DE COMPETICIÓN","Liga, copa, grupos o híbrido con reglamento propio");vals=[["LIGA","COPA","GRUPOS + KO","SUIZO + KO"][self.tournament["format"]],[8,12,16,24,32][self.tournament["teams"]],"IDA Y VUELTA" if self.tournament["legs"] else "PARTIDO ÚNICO","ACTIVAS" if self.tournament["custom_rules"] else "ESTÁNDAR","GUARDAR COMPETICIÓN"]
        for i,(l,v) in enumerate(zip(["FORMATO","EQUIPOS","ELIMINATORIAS","REGLAS PERSONALIZADAS","CREAR"],vals)):self.option(c,340+i*88,l,v,i)
        draw_text(c,"IDENTIDADES CENTELLA",self.f16,BRAND.sapphire_light,(1210,355))
        for i,comp in enumerate(COMPETITIONS):rounded_panel(c,pygame.Rect(1210,405+i*82,560,66),(14,18,27),(48,54,68),12,1,235);draw_text(c,comp["name"],self.f16,BRAND.white,(1230,423+i*82));draw_text(c,comp["format"],self.f12,BRAND.muted,(1740,427+i*82),"topright")
    def draw_setpiece(self,c):
        self.page_header(c,"LAB DE JUGADAS PREPARADAS","Mueve cinco atacantes; L1/R1 o Q/E cambia el jugador")
        board=pygame.Rect(390,320,600,430);rounded_panel(c,board,(20,61,46),(150,190,170),18,2,245);pygame.draw.rect(c,(185,215,195),board,2,border_radius=16);pygame.draw.line(c,(185,215,195),(690,320),(690,750),2);pygame.draw.circle(c,(185,215,195),(690,535),72,2)
        for i,p in enumerate(self.setpiece):pygame.draw.circle(c,BRAND.sapphire_light if i==self.setpiece_selected else BRAND.white,p,17 if i==self.setpiece_selected else 13);draw_text(c,str(i+1),self.f12,(10,14,22),p,"center")
        draw_text(c,"A / ENTER  GUARDAR JUGADA",self.f20,BRAND.white,(1130,430));draw_text(c,"L1/R1 · Q/E  JUGADOR",self.f16,BRAND.muted,(1130,485));draw_text(c,"STICK / FLECHAS  MOVER",self.f16,BRAND.muted,(1130,525));draw_text(c,f"PRESETS: {len(self.user['setpieces'])}",self.f16,BRAND.sapphire_light,(1130,600))
    def draw_controls(self,c):
        self.page_header(c,"MANDO Y CONTROLES",f"{self.controller.primary_name()} · {len(self.controller.joysticks)} mando(s) detectado(s)");mapping=SETTINGS.get("controller.buttons",{})
        for i,(key,label) in enumerate(GAMEPLAY_ACTION_LABELS):
            y=325+i*78;sel=i==self.page_cursor;rect=pygame.Rect(90,y,1030,64);rounded_panel(c,rect,(21,27,40) if sel else (13,17,26),BRAND.sapphire_light if sel else (45,51,65),12,2 if sel else 1,245);draw_text(c,label,self.f16,BRAND.white,(116,y+16));draw_text(c,f"BOTÓN {mapping.get(key,'—')}",self.f16,BRAND.sapphire_light,(1085,y+16),"topright");self.add_region(rect,"cursor",i)
        rounded_panel(c,pygame.Rect(1190,325,640,405),(11,15,24),(48,57,75),20,1,245);draw_text(c,"MAPEO",self.f20,BRAND.sapphire_light,(1230,365));draw_text(c,"A / ENTER",self.f24,BRAND.white,(1230,420));draw_text(c,"Selecciona la acción y presiona el botón físico.",self.f16,BRAND.muted,(1230,470));draw_text(c,"El partido lee el mismo archivo de configuración.",self.f16,BRAND.muted,(1230,510))
        if self.rebinding:draw_text(c,"ESPERANDO BOTÓN…",self.f30,(255,203,88),(1230,665))
    def draw_video(self,c):
        self.page_header(c,"VÍDEO Y RENDIMIENTO","Escala el partido sin sacrificar el control")
        vals=["SÍ" if SETTINGS.get("display.fullscreen",False) else "NO",SETTINGS.get("display.quality","BALANCED"),f"{int(float(SETTINGS.get('display.render_scale',.75))*100)}%",SETTINGS.get("display.fps_cap",60),"SÍ" if SETTINGS.get("display.motion",True) else "NO","SÍ" if SETTINGS.get("gameplay.low_latency_experimental",False) else "NO"]
        for i,(l,v) in enumerate(zip(["PANTALLA COMPLETA","PERFIL DE CALIDAD","ESCALA RENDER PARTIDO","LÍMITE FPS","MOVIMIENTO DE MENÚ","LOW LATENCY EXPERIMENTAL"],vals)):self.option(c,325+i*82,l,v,i)
        draw_text(c,"La escala de render deja margen para conectar CENTELLA SR al frame final.",self.f16,BRAND.muted,(1190,390))
    def draw_access(self,c):
        self.page_header(c,"ACCESIBILIDAD","Preferencias persistentes");keys=[("high_contrast","ALTO CONTRASTE"),("reduce_motion","REDUCIR MOVIMIENTO"),("large_text","TEXTO GRANDE"),("hold_to_confirm","MANTENER PARA CONFIRMAR")]
        for i,(k,l) in enumerate(keys):self.option(c,350+i*92,l,"SÍ" if SETTINGS.get(f"accessibility.{k}",False) else "NO",i)
    def draw_workshop(self,c):
        self.page_header(c,"CENTELLA WORKSHOP","Browse → Preview → Install → Verify → Play")
        for i,(a,b) in enumerate([("TEAMS","Option files y plantillas"),("KITS","Uniformes y branding"),("STADIUMS","Geometría y presentación"),("AUDIO","Cánticos y comentarios"),("COMPETITIONS","Reglas e identidades")]):
            x=90+(i%3)*580;y=350+(i//3)*220;rounded_panel(c,pygame.Rect(x,y,540,185),(14,18,28),(48,56,72),18,1,245);draw_text(c,a,self.f24,BRAND.white,(x+28,y+30));draw_text(c,b,self.f16,BRAND.muted,(x+28,y+90));draw_text(c,"HASH + DEPENDENCIAS",self.f12,BRAND.sapphire_light,(x+28,y+140))
        draw_text(c,"A / ENTER  PREPARAR ÍNDICE LOCAL .CFMOD",self.f20,BRAND.white,(90,840))
    def draw_doctor(self,c):
        self.page_header(c,"CENTELLA LAB","Diagnóstico del shell, Python 3.10, dependencias y motor nativo");data=self.runtime();ready=data.get("ready",False);draw_text(c,"READY" if ready else "REPAIR REQUIRED",self.f40,(105,220,150) if ready else (245,180,65),(90,335));y=430
        for p in data.get("runtimes",[]):
            mods=p.get("modules") or {};engine=bool(p.get("engine"));rounded_panel(c,pygame.Rect(90,y,1110,118),(13,18,27),(55,62,76),16,1,245);draw_text(c,Path(p.get("executable","")).name+"  "+p.get("version",""),self.f20,BRAND.white,(118,y+22));draw_text(c,p.get("executable",""),self.f12,BRAND.muted,(118,y+59));summary=" · ".join(f"{m}:{'OK' if mods.get(m) else '—'}" for m in ["absl","numpy","pygame","gfootball_engine"]);draw_text(c,summary,self.f12,(110,218,155) if engine else (242,188,82),(118,y+87));y+=132
        for i,(t,s) in enumerate([("VOLVER A COMPROBAR","Escanea runtimes y motor"),("INSTALAR / REPARAR","Reutiliza TOOLCHAIN/Python310 + vcpkg")]):
            x=1270;y2=430+i*155;sel=self.page_cursor==i;rounded_panel(c,pygame.Rect(x,y2,560,125),(22,28,42) if sel else (13,17,26),BRAND.sapphire_light if sel else (49,56,70),18,2 if sel else 1,245);draw_text(c,t,self.f20,BRAND.white,(x+28,y2+25));draw_text(c,s,self.f12,BRAND.muted,(x+28,y2+72))
        draw_text(c,"El shell abre aunque el motor falle. El partido usa el Python 3.10 dedicado cuando esté listo.",self.f16,BRAND.muted,(90,925))
    def draw_detail(self,c):
        m=self.detail_mode;self.page_header(c,m.title if m else "CENTELLA",m.subtitle if m else "");draw_text(c,m.description if m else "",self.f24,BRAND.white,(110,380));draw_text(c,"A / ENTER  REGISTRAR RUTA DE PRODUCTO",self.f20,BRAND.sapphire_light,(110,520))
    def draw_bottom(self,c):
        if self.scene=="splash":return
        pygame.draw.rect(c,(7,10,17),(0,1025,1920,55));draw_text(c,"B / ESC  VOLVER",self.f12,BRAND.muted,(60,1042));draw_text(c,self.controller.ui_hint(),self.f12,BRAND.white,(1860,1042),"topright")
    def draw_message(self,c):
        if not self.message or time.perf_counter()>=self.message_until:return
        im=self.f16.render(self.message,True,BRAND.white);w=min(1650,im.get_width()+70);r=pygame.Rect((1920-w)//2,945,w,58);rounded_panel(c,r,(15,20,31),BRAND.sapphire_light,15,2,248);c.blit(im,im.get_rect(center=r.center))
    def draw_perf(self,c):
        if not self.performance_overlay:return
        r=pygame.Rect(1610,125,240,50);rounded_panel(c,r,(0,0,0),(70,80,95),10,1,190);draw_text(c,f"UI {self.clock.get_fps():5.1f} FPS",self.f12,BRAND.white,r.center,"center")
    def render(self):
        self.mouse_regions=[];c=pygame.Surface(LOGICAL_SIZE).convert();fn={"splash":self.draw_splash,"hub":self.draw_hub,"quick":lambda x:self.draw_quick(x,False),"coop":lambda x:self.draw_quick(x,True),"training":self.draw_training,"career":self.draw_career,"street":self.draw_street,"journey":self.draw_journey,"online":self.draw_online,"edit":self.draw_edit,"player":self.draw_player,"tournament":self.draw_tournament,"setpiece":self.draw_setpiece,"controls":self.draw_controls,"video":self.draw_video,"access":self.draw_access,"workshop":self.draw_workshop,"doctor":self.draw_doctor,"detail":self.draw_detail}.get(self.scene,self.draw_hub);fn(c);self.draw_bottom(c);self.draw_message(c);self.draw_perf(c);self.viewport.present(c)
    def run(self):
        while self.running:
            self.clock.tick(max(30,int(SETTINGS.get("display.fps_cap",60))))
            for e in pygame.event.get():self.handle_event(e)
            self.render()
        pygame.quit()


def main(): App().run()
if __name__=="__main__": main()
