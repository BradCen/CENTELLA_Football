import type { Player, Team } from './types';

const firstNames = ['Leo','Mateo','Adrián','Thiago','Nicolás','Bruno','Damián','Iker','Lucas','Gael','Martín','Sergio','Álex','Iván','Hugo','Diego','Enzo','Marco'];
const lastNames = ['Silva','Rojas','Costa','Vega','Méndez','Torres','Navarro','Santos','Luna','Paredes','Campos','Reyes','Molina','Suárez','Ferrer','Pinto','Ramos','Ortega'];
const positions = ['GK','RB','CB','CB','LB','CDM','CM','CAM','RW','ST','LW','GK','CB','RB','CM','CAM','ST','LW'];

function squad(seed: number): Player[] {
  return Array.from({ length: 18 }, (_, i) => {
    const rating = 68 + ((seed * 7 + i * 5) % 22);
    return {
      id: `p-${seed}-${i}`,
      name: `${firstNames[(seed + i * 3) % firstNames.length]} ${lastNames[(seed * 2 + i * 5) % lastNames.length]}`,
      number: i === 0 ? 1 : ((i * 3 + seed) % 29) + 2,
      position: positions[i],
      rating,
      pace: Math.min(94, rating + ((i * 7) % 13) - 5),
      shot: Math.min(94, rating + ((i * 5) % 11) - 6),
      pass: Math.min(94, rating + ((i * 3) % 12) - 4),
      dribble: Math.min(94, rating + ((i * 9) % 10) - 4),
      defense: Math.min(94, rating + ((i * 4) % 15) - 7),
      physical: Math.min(94, rating + ((i * 6) % 12) - 5),
    };
  });
}

const raw = [
  ['centella','CENTELLA FC','CEN','Liga Horizonte','Venezuela','#1677ff','#07152b','#8bd3ff',86],
  ['capital','Capital United','CAP','Liga Horizonte','Venezuela','#f6f7fb','#181b24','#d7b35d',84],
  ['orinoquia','Orinoquia SC','ORI','Liga Horizonte','Venezuela','#f7c948','#172418','#24b76b',81],
  ['andes','Andes Athletic','AND','Liga Horizonte','Venezuela','#e63446','#17171c','#ffffff',82],
  ['caribe','Caribe Azul','CAR','Liga Horizonte','Venezuela','#1ec8e5','#032236','#ffffff',79],
  ['metropolitan','Metropolitan 04','MET','Liga Horizonte','Venezuela','#7529ff','#12091e','#e7d7ff',83],
  ['iberia','Iberia Real','IBR','Liga Continental','España','#ffffff','#161b2a','#cbb26a',88],
  ['catalunya','Catalunya City','CAT','Liga Continental','España','#b11c3d','#11255e','#f2c94c',87],
  ['sevilla','Sevilla Sur','SES','Liga Continental','España','#f04444','#ffffff','#111111',83],
  ['valencia','Valencia Marina','VAM','Liga Continental','España','#ff8c32','#111523','#ffffff',82],
  ['london','London Royals','LOR','Premier Division','Inglaterra','#244cff','#f7f7f8','#d7b35d',89],
  ['manchester','Manchester Forge','MFO','Premier Division','Inglaterra','#e22f3e','#111111','#ffffff',88],
  ['mersey','Mersey Red','MER','Premier Division','Inglaterra','#c91232','#ffffff','#f5d05d',86],
  ['north','North London FC','NLF','Premier Division','Inglaterra','#ffffff','#171b2a','#7ba8ff',85],
  ['milan','Milano Nero','MIL','Serie Elite','Italia','#d51f3c','#111111','#ffffff',87],
  ['torino','Torino Piemonte','TOR','Serie Elite','Italia','#f5f5f5','#151515','#d7b35d',86],
  ['paris','Paris Lumière','PAR','Ligue Élite','Francia','#14275c','#e71f43','#ffffff',88],
  ['munich','Munich Rot','MUN','Bundesliga Nova','Alemania','#d71f35','#ffffff','#191919',89],
  ['rio','Rio Atlético','RIO','Liga América','Brasil','#111111','#f5d638','#48c57a',84],
  ['buenosaires','Buenos Aires Azul','BAA','Liga América','Argentina','#1b4cc4','#f2d348','#ffffff',85],
] as const;

export const teams: Team[] = raw.map((t, i) => ({
  id: t[0], name: t[1], short: t[2], league: t[3], country: t[4],
  primary: t[5], secondary: t[6], accent: t[7], rating: t[8], players: squad(i + 1),
}));

export const formations = {
  '433': [[50,88],[18,70],[39,72],[61,72],[82,70],[32,51],[50,46],[68,51],[18,25],[50,18],[82,25]],
  '4231': [[50,88],[18,70],[39,72],[61,72],[82,70],[40,53],[60,53],[20,32],[50,31],[80,32],[50,15]],
  '442': [[50,88],[18,70],[39,72],[61,72],[82,70],[16,45],[39,48],[61,48],[84,45],[38,20],[62,20]],
  '352': [[50,88],[28,70],[50,74],[72,70],[12,47],[35,52],[50,42],[65,52],[88,47],[38,18],[62,18]],
} as const;
