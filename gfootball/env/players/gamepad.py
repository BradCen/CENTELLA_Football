# coding=utf-8
# Copyright 2019 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");

"""Player with actions coming from gamepad.

CENTELLA extension: mappings are loaded from the same persistent settings used
by the product shell, so remapping in the menu affects the match controller.
"""

from absl import logging
import pygame

from gfootball.env import controller_base
from gfootball.env import football_action_set
from gfootball.env import event_queue

try:
  from centella.settings import SETTINGS
except Exception:
  SETTINGS = None


def _button(name, fallback):
  if SETTINGS is None:
    return fallback
  try:
    return int(SETTINGS.get('controller.buttons.' + name, fallback))
  except Exception:
    return fallback


def _axis(name, fallback):
  if SETTINGS is None:
    return fallback
  try:
    return int(SETTINGS.get('controller.axes.' + name, fallback))
  except Exception:
    return fallback


def _deadzone():
  if SETTINGS is None:
    return 0.22
  try:
    return float(SETTINGS.get('controller.deadzone', 0.22))
  except Exception:
    return 0.22


def button_actions():
  return {
      _button('short_pass', 0): [football_action_set.action_short_pass,
                                 football_action_set.action_pressure],
      _button('shot', 1): [football_action_set.action_shot,
                           football_action_set.action_team_pressure],
      _button('high_pass', 2): [football_action_set.action_high_pass,
                                football_action_set.action_sliding],
      _button('through_pass', 3): [football_action_set.action_long_pass,
                                   football_action_set.action_keeper_rush],
      _button('switch_player', 4): [football_action_set.action_switch],
      _button('teammate_press', 5): [football_action_set.action_dribble],
  }


class Player(controller_base.Controller):
  """Player with actions coming from one physical controller."""

  def __init__(self, player_config, env_config):
    controller_base.Controller.__init__(self, player_config, env_config)
    self._can_play_right = True
    pygame.init()
    self._index = int(player_config['player_gamepad'])
    event_queue.add_controller('gamepad', self._index)
    pygame.joystick.init()
    if pygame.joystick.get_count() <= self._index:
      logging.error('You need %d physical controller(s) connected', self._index + 1)
      raise RuntimeError('CENTELLA Football: controller not connected')
    self._joystick = pygame.joystick.Joystick(self._index)
    self._joystick.init()
    logging.info('CENTELLA controller %d: %s', self._index, self._joystick.get_name())

  def take_action(self, observations):
    assert len(observations) == 1, 'Gamepad does not support multiple player control'
    x_axis = self._axis_value(_axis('move_x', 0))
    y_axis = self._axis_value(_axis('move_y', 1))
    dz = _deadzone()
    left = x_axis < -dz
    right = x_axis > dz
    top = y_axis < -dz
    bottom = y_axis > dz
    active_buttons = {}
    mapping = button_actions()

    for event in event_queue.get('gamepad', self._index):
      if event.type == pygame.JOYBUTTONDOWN:
        for action in mapping.get(event.button, []):
          active_buttons[action] = 1
      if event.type == pygame.JOYAXISMOTION and event.axis == _axis('sprint', 5) and event.value > 0.15:
        active_buttons[football_action_set.action_sprint] = 1

    for button, actions in mapping.items():
      if button < self._joystick.get_numbuttons() and self._joystick.get_button(button):
        for action in actions:
          active_buttons[action] = 1

    sprint_axis = _axis('sprint', 5)
    if sprint_axis < self._joystick.get_numaxes() and self._joystick.get_axis(sprint_axis) > 0.15:
      active_buttons[football_action_set.action_sprint] = 1
    return self.get_env_action(left, right, top, bottom, active_buttons)

  def _axis_value(self, index):
    if index < 0 or index >= self._joystick.get_numaxes():
      return 0.0
    return self._joystick.get_axis(index)
