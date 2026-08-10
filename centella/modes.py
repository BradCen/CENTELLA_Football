from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Mode:
    key: str
    title: str
    subtitle: str
    description: str
    status: str
    accent: str = "SAPPHIRE"
    route: str = "detail"


TABS = ["HOME", "PLAY", "CAREER", "ONLINE", "CUSTOMIZE"]

MODES: Dict[str, List[Mode]] = {
    "HOME": [
        Mode("continue", "CONTINUAR", "Vuelve al campo", "Retoma la actividad más reciente del perfil.", "READY", route="quick_match"),
        Mode("kickoff", "KICK OFF", "Partido inmediato", "Configura local, mando, duración y presentación antes de jugar.", "PLAYABLE", route="quick_match"),
        Mode("master", "LIGA MÁSTER 2.0", "Dirige o preside", "Carrera de club con roles de DT, Presidente o control total.", "DESIGN LAB", route="career"),
        Mode("street", "STREET / FUTSAL", "Fútbol desde el barrio", "5v5, clubes creados, superficies y reglas configurables.", "DESIGN LAB", route="street"),
        Mode("journey", "MODO LEYENDA", "Tu carrera, tu historia", "Carrera de jugador con decisiones, eventos e identidad propia.", "DESIGN LAB", route="journey"),
        Mode("lab", "CENTELLA LAB", "Rendimiento y motor", "Comprueba runtime, mando, render y estado del motor nativo.", "TOOLS", route="doctor"),
    ],
    "PLAY": [
        Mode("kickoff", "PARTIDO DE EXHIBICIÓN", "11 vs 11 local", "El flujo más corto hacia un partido completo.", "PLAYABLE", route="quick_match"),
        Mode("localcoop", "CO-OP LOCAL", "2 mandos", "Dos personas en el mismo PC contra la IA o en lados opuestos.", "PLAYABLE", route="local_coop"),
        Mode("training", "ENTRENAMIENTO", "Academia", "Pase, definición, control y situaciones reducidas del motor GRF.", "PLAYABLE", route="training"),
        Mode("tournaments", "TORNEOS", "Copa o liga", "Crea formatos, grupos, eliminatorias y reglas personalizadas.", "EDITOR", route="tournament"),
        Mode("futsal", "FÚTBOL SALA", "5v5", "Reglas, balón, superficie y táctica de futsal como modo propio.", "DESIGN LAB", route="street"),
        Mode("street", "FÚTBOL CALLEJERO", "Concreto · tierra · asfalto", "Canchas pequeñas, equipos mixtos y reglas de barrio.", "DESIGN LAB", route="street"),
        Mode("penalties", "PENALES", "Duelo rápido", "Sesión corta para practicar definición y portería.", "PROTOTYPE", route="training"),
        Mode("random", "RANDOM MATCH", "Sin pensar", "Elige automáticamente equipos y configuración.", "PLAYABLE", route="quick_match"),
    ],
    "CAREER": [
        Mode("master", "LIGA MÁSTER 2.0", "DT · Presidente · Completo", "Club, calendario, mercado, scouting, moral, finanzas y estadio.", "DESIGN LAB", route="career"),
        Mode("coopcareer", "CARRERA CO-OP", "DT + Presidente", "Dos usuarios reparten responsabilidades del mismo club.", "DESIGN LAB", route="career"),
        Mode("legend", "MODO LEYENDA", "Carrera de jugador", "Rendimiento, contratos, entrenamiento y narrativa emergente.", "DESIGN LAB", route="journey"),
        Mode("journey", "THE JOURNEY: CENTELLA", "Historia dinámica", "Capas cinematográficas sobre una carrera no guionizada de forma rígida.", "DESIGN LAB", route="journey"),
        Mode("scouting", "CENTRO DE OJEO", "Descubrir, no ordenar", "Informes progresivos y margen de error del ojeador.", "PROTOTYPE", route="career"),
        Mode("clubworld", "MUNDO DEL CLUB", "Finanzas y estadio", "Patrocinio, infraestructura, cantera y decisiones institucionales.", "PROTOTYPE", route="career"),
    ],
    "ONLINE": [
        Mode("ranked", "RANKED 1v1", "Competitivo", "Misma física que offline con matchmaking por nivel.", "NETWORK SPEC", route="online"),
        Mode("friendly", "AMISTOSO ONLINE", "Invita a un amigo", "Partida directa con reglas acordadas.", "NETWORK SPEC", route="online"),
        Mode("clubs", "CENTELLA CLUBS", "Clubes con amigos", "Crea un club persistente y controla un futbolista por persona.", "NETWORK SPEC", route="online"),
        Mode("streetclubs", "STREET CLUBS", "5v5 persistente", "Progresión cosmética y de identidad sin pay-to-win.", "NETWORK SPEC", route="online"),
        Mode("coopmaster", "LIGA MÁSTER CO-OP", "DT + Presidente", "Administra un club a distancia con roles separados.", "NETWORK SPEC", route="online"),
        Mode("communitycup", "COPAS DE COMUNIDAD", "Reglas del creador", "Torneos creados por usuarios con presets verificables.", "NETWORK SPEC", route="online"),
    ],
    "CUSTOMIZE": [
        Mode("edit", "MODO EDICIÓN", "Equipos y jugadores", "Nombres, colores, plantillas, identidad y datos creados por usuario.", "EDITOR", route="edit"),
        Mode("creator", "CREADOR DE JUGADOR", "Tu identidad", "Apariencia, atributos, posición y perfil de animación.", "EDITOR", route="player_creator"),
        Mode("competition", "CREADOR DE COMPETICIÓN", "Tu reglamento", "Ligas, grupos, playoffs, puntos y desempates personalizables.", "EDITOR", route="tournament"),
        Mode("setpieces", "LAB DE JUGADAS", "Balón parado", "Diseña movimientos ensayados y guarda presets tácticos.", "EDITOR", route="setpiece"),
        Mode("controls", "MANDO Y CONTROLES", "Mapeo completo", "Detecta gamepads y reasigna botones del menú y del partido.", "READY", route="controls"),
        Mode("video", "VÍDEO Y RENDIMIENTO", "Escalable", "Resolución, render scale, FPS, motion y perfiles de calidad.", "READY", route="video"),
        Mode("access", "ACCESIBILIDAD", "Juega a tu manera", "Contraste, movimiento reducido, texto y confirmaciones.", "READY", route="accessibility"),
        Mode("mods", "CENTELLA WORKSHOP", "Contenido comunitario", "Catálogo local para instalar paquetes propios o licenciados con hashes.", "FOUNDATION", route="workshop"),
    ],
}
