# -*- coding: cp1252 -*-
#
# Copyright (c) 2008 Andreas Blixt <andreas@blixt.org>
# Project homepage: <http://code.google.com/p/monkey-web/>
#
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
#

"""Data structures and game logic for the MoNKey! game.

Trivia:
An m,n,k-game is an abstract board game in which players take turns in placing
a stone of their color on an m×n board, the winner being the player who first
gets k stones of their own color in a row, horizontally, vertically, or
diagonally. Thus, tic-tac-toe is the 3,3,3-game and free-style gomoku is the
19,19,5-game.

See: http://en.wikipedia.org/wiki/m,n,k-game

In addition, this engine supports m,n,k,p,q-games, where q is the number of
stones placed in the very first turn and p the number of stones placed in any
subsequent turns.
"""

from google.appengine.api import users
from google.appengine.ext import db

import re

class Error(Exception):
    """Base of all exceptions in the monkey module."""
    pass

class InvalidMoveError(Error):
    """Thrown when an illegal move is made."""
    pass

class NotYourTurnError(Error):
    """Thrown when a player tries to move when it's another player's turn."""
    pass

class Player(db.Model):
    user = db.UserProperty()

class RuleSet(db.Model):
    """A rule set for an m,n,k,p,q-game.
    """
    name = db.StringProperty()
    author = db.UserProperty()
    num_players = db.IntegerProperty(choices = (2, 3, 4),
                                     verbose_name = 'Number of players')
    m = db.IntegerProperty(default = 19, validator = lambda v: v > 0,
                           verbose_name = 'Board width')
    n = db.IntegerProperty(default = 19, validator = lambda v: v > 0,
                           verbose_name = 'Board height')
    k = db.IntegerProperty(default = 5, validator = lambda v: v > 0,
                           verbose_name = 'Consecutive stones to win')
    p = db.IntegerProperty(default = 1, validator = lambda v: v > 0,
                           verbose_name = 'Stones per turn')
    q = db.IntegerProperty(default = 1, validator = lambda v: v > 0,
                           verbose_name = 'Stones first turn')

class Game(db.Model):
    """The data structure for an m,n,k,p,q-game.
    """
    state = db.StringProperty(default = 'waiting',
                              choices = ('waiting',
                                         'playing',
                                         'finished'))
    players = db.ListProperty(item_type = db.Key)
    turn = db.IntegerProperty(default = 1, choices = (1, 2, 3, 4))
    data = db.StringListProperty()
    rule_set = db.ReferenceProperty(RuleSet)

    @staticmethod
    def new(player, m = 3, n = 3, k = 3, p = 1, q = 1, players = 2, template = None):
        """Creates a new game with the specified parameters (or using the
        specified template) and initializes the board.
        """
        if template:
            m, n, k = template.m, template.n, template.k
            p, q = template.p, template.q
            players = t.num_players

        return Game(players = [player],
                    num_players = players,
                    data = ['0' * height for i in range(width)],
                    m = m,
                    n = n,
                    k = k,
                    p = p,
                    q = q)

    @staticmethod
    def template(name, m, n, k, p = 1, q = 1, players = 2):
        """Creates a template with the specified parameters if it does not
        already exist.
        """
        key = re.sub('\\W|_', '', name).lower()
        template = Game.get_by_key_name(key)
        if not template:
            template = Game(key_name = key,
                            num_players = players,
                            m = m,
                            n = n,
                            k = k,
                            p = p,
                            q = q,
                            template = name)
            template.put()

        return template

    def move(self, player, x, y):
        player_turn = self.players.index(player)
        if self.turn != player_turn: raise NotYourTurnError()

        board = self.unpack_board()
        if board[x][y]: raise InvalidMoveError()

        board[x][y] = player_turn
        if self.test_win(player_turn, x, y):
            pass
        else:
            self.turn = (self.turn - 1) % self.num_players + 1

    def pack_board(self):
        if not self._board: return
        self.data = [string.join([str(self._board[x][y])
                                  for y in range(self.n)], '')
                     for x in range(self.m)]

    def put(self):
        self.pack_board()
        db.Model.put(self)

    def test_win(self, player_turn, x, y):
        board = self.unpack_board()

        cx, cy, cz = 0, 0, 0
        for i in range(-self.k + 1, self.k - 1):
            tx, ty = x + i, y + i
            # Test horizontal
            if tx >= 0 and tx < self.m:
                cx += 1 if board[tx][y] == player_turn else -cx
            # Test vertical
            if ty >= 0 and ty < self.n:
                cy += 1 if board[x][ty] == player_turn else -cy
            # Test diagonal
            if tx >= 0 and ty >= 0 and tx < self.m and ty < self.n:
                cz += 1 if board[tx][ty] == player_turn else -cz

            if self.k in (cx, cy, cz):
                return True

        return False

    def unpack_board(self):
        if not self._board:
            self._board = [[int(val) for val in list(row)]
                           for row in self.data]
        return self._board

# Game templates
Game.template('Connect6', 19, 19, 6, 2, 1)
Game.template('Gomoku', 19, 19, 5)
Game.template('Tic-Tac-Toe', 3, 3, 3)
