export type Screen = 'splash' | 'home' | 'teams' | 'kits' | 'gameplan' | 'settings' | 'tunnel';

export type Player = {
  id: string;
  name: string;
  number: number;
  position: string;
  rating: number;
  pace: number;
  shot: number;
  pass: number;
  dribble: number;
  defense: number;
  physical: number;
};

export type Team = {
  id: string;
  name: string;
  short: string;
  league: string;
  country: string;
  primary: string;
  secondary: string;
  accent: string;
  rating: number;
  players: Player[];
};

export type FormationId = '433' | '4231' | '442' | '352';

export type MatchConfig = {
  duration: number;
  difficulty: string;
  weather: string;
  stadium: string;
  time: string;
  camera: string;
  speed: string;
};

export type GameState = {
  homeTeam: Team;
  awayTeam: Team;
  homeKit: number;
  awayKit: number;
  formation: FormationId;
  captainId: string;
  penaltyId: string;
  tactic: string;
  width: number;
  depth: number;
  match: MatchConfig;
};
