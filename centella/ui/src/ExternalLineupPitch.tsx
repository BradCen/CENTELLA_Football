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
      color: selected ? '#ffffff' : '#07111f',
      borderColor: selected ? '#7cc8ff' : '#ffffff',
      numberColor: selected ? '#07111f' : '#ffffff',
      numberBackgroundColor: selected ? '#7cc8ff' : '#07111f',
      nameColor: '#ffffff',
      nameBackgroundColor: selected ? 'rgba(11,91,255,.9)' : 'rgba(2,8,18,.82)',
      size: selected ? 40 : 34,
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

  if (formation === '4231') {
    return { gk: p(0), df: [p(1), p(2), p(3), p(4)], cdm: [p(5), p(6)], cam: [p(7), p(8), p(9)], fw: [p(10)] };
  }
  if (formation === '442') {
    return { gk: p(0), df: [p(1), p(2), p(3), p(4)], cm: [p(5), p(6), p(7), p(8)], fw: [p(9), p(10)] };
  }
  if (formation === '352') {
    return { gk: p(0), df: [p(1), p(2), p(3)], cdm: [p(4), p(5)], cm: [p(6), p(7), p(8)], fw: [p(9), p(10)] };
  }
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
      nameBackgroundColor: 'rgba(2,8,18,.82)',
      pattern: 'thin-stripes',
      patternColor: club.secondary,
      nameOverflow: 'ellipsis',
    },
  };

  return (
    <div className="external-pitch-shell">
      <div className="external-pitch-credit">PITCH ENGINE · MIT / react-soccer-lineup</div>
      <SoccerLineUp
        size="fill"
        orientation="vertical"
        color="#123f32"
        pattern="lines"
        homeTeam={homeTeam}
      />
    </div>
  );
}
