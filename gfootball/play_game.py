# coding=utf-8
# Copyright 2019 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Script allowing humans to play Google Research Football.

CENTELLA additions keep the original entry point compatible while exposing the
render resolution and physics/action cadence to the product shell.
"""

from __future__ import absolute_import, division, print_function

from absl import app
from absl import flags
from absl import logging

from gfootball.env import config
from gfootball.env import football_env

FLAGS = flags.FLAGS

flags.DEFINE_string('players', 'keyboard:left_players=1',
                    'Semicolon separated player definitions.')
flags.DEFINE_string('level', '', 'Level to play')
flags.DEFINE_enum('action_set', 'default', ['default', 'full'], 'Action set')
flags.DEFINE_bool('real_time', True,
                  'If true, environment will slow down so humans can play.')
flags.DEFINE_bool('render', True, 'Whether to do game rendering.')
flags.DEFINE_integer('render_resolution_x', 1280,
                     'Horizontal native render resolution. Height keeps 16:9.')
flags.DEFINE_integer('physics_steps_per_frame', 10,
                     'Native physics steps grouped before the next environment action.')


def main(_):
  players = FLAGS.players.split(';') if FLAGS.players else ''
  assert not any(['agent' in player for player in players]), (
      'Player type \'agent\' can not be used with play_game.')
  cfg_values = {
      'action_set': FLAGS.action_set,
      'dump_full_episodes': True,
      'players': players,
      'real_time': FLAGS.real_time,
      'render_resolution_x': max(640, int(FLAGS.render_resolution_x)),
      'physics_steps_per_frame': max(1, min(20, int(FLAGS.physics_steps_per_frame))),
  }
  if FLAGS.level:
    cfg_values['level'] = FLAGS.level
  cfg = config.Config(cfg_values)
  env = football_env.FootballEnv(cfg)
  if FLAGS.render:
    env.render()
  env.reset()
  try:
    while True:
      _, _, done, _ = env.step([])
      if done:
        env.reset()
  except KeyboardInterrupt:
    logging.warning('Game stopped, writing dump...')
    env.write_dump('shutdown')
  finally:
    env.close()


if __name__ == '__main__':
  app.run(main)
