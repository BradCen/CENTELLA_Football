import SoccerLineUp, { type Team as LineupTeam } from 'react-soccer-lineup';
import type { FormationId, Player, Team } from './types';

type Props = {
  club: Team;
  starters: Player[];
  formation: FormationId;
  selectedId: string;
  captainId: string;
  onSelect: (id: string) => void;
};

function visualPlayer(player: Player, selected: boolean, captain: boolean, onSelect: (id: string) => void) {
  return {
    name: `${captain ? 'C · ' : ''}${player.name.split(' ').pop() ?? player.name}`,
    number: player.number,
    onClick: () => onSelect(player.id),
    style: {
      color: selected ? '#f7fbff' : '#08121f',
      borderColor: selected ? '#61c6ff' : 'rgba(255,255,255,.92)',
      numberColor: selected ? '#07111c' : '#f7fbff',
      numberBackgroundColor: selected ? '#7cd1ff' : '#08121f',
      nameColor: '#ffffff',
      nameBackgroundColor: selected ? 'rgba(14,129,227,.96)' : 'rgba(2,8,15,.88)',
      size: selected ? 42 : 35,
      nameSize: selected ? 12 : 10,
      nameOverflow: 'ellipsis' as const,
    },
  };
}

function buildSquad(starters: Player[], formation: FormationId, selectedId: string, captainId: string, onSelect: (id: string) => void): LineupTeam['squad'] {
  const p = (index: number) => {
    const player = starters[index];
    return player ? visualPlayer(player, player.id === selectedId, player.id === captainId, onSelect) : undefined;
  };

  if (formation === '4231') return { gk: p(0), df: [p(1), p(2), p(3), p(4)], cdm: [p(5), p(6)], cam: [p(7), p(8), p(9)], fw: [p(10)] };
  if (formation === '442') return { gk: p(0), df: [p(1), p(2), p(3), p(4)], cm: [p(5), p(6), p(7), p(8)], fw: [p(9), p(10)] };
  if (formation === '352') return { gk: p(0), df: [p(1), p(2), p(3)], cdm: [p(4), p(5)], cm: [p(6), p(7), p(8)], fw: [p(9), p(10)] };
  return { gk: p(0), df: [p(1), p(2), p(3), p(4)], cm: [p(5), p(6), p(7)], fw: [p(8), p(9), p(10)] };
}

export default function ExternalLineupPitch({ club, starters, formation, selectedId, captainId, onSelect }: Props) {
  const homeTeam: LineupTeam = {
    squad: buildSquad(starters, formation, selectedId, captainId, onSelect),
    style: {
      color: club.primary,
      borderColor: club.secondary,
      numberColor: '#ffffff',
      numberBackgroundColor: club.primary,
      nameColor: '#ffffff',
      nameBackgroundColor: 'rgba(2,8,15,.88)',
      pattern: 'thin-stripes',
      patternColor: club.secondary,
      nameOverflow: 'ellipsis',
    },
  };

  return <div className="external-pitch-shell"><SoccerLineUp size="fill" orientation="vertical" color="#164f3b" pattern="lines" homeTeam={homeTeam}/></div>;
}
