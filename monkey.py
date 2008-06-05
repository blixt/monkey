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

import math, random, re, string, util

class Error(Exception):
    """Base of all exceptions in the monkey module."""
    pass

class JoinError(Error):
    """Thrown when a player cannot join a game."""
    pass

class MoveError(Error):
    """Thrown when a move cannot be made."""
    pass

class Player(db.Model):
    user = db.UserProperty()
    nickname = db.StringProperty()
    draws = db.IntegerProperty(default = 0)
    losses = db.IntegerProperty(default = 0)
    wins = db.IntegerProperty(default = 0)

    @staticmethod
    def get_current():
        curuser = users.get_current_user()
        player = Player.gql('WHERE user = :1', curuser).get()
        if not player:
            player = Player(user = curuser,
                            nickname = curuser.nickname())
            player.put()

        return player

    def join(self, game):
        game.add_player(self)

class RuleSet(db.Model):
    """A rule set for an m,n,k,p,q-game.
    """
    name = db.StringProperty(required = True)
    author = db.ReferenceProperty(Player)
    num_players = db.IntegerProperty(choices = (2, 3, 4, 5, 6, 7, 8, 9),
                                     default = 2,
                                     verbose_name = 'Number of players')
    exact = db.BooleanProperty(default = False,
                               verbose_name = 'Number of consequtive stones '
                                              'must be exact for a win')
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

    def is_win(self, board, player, x, y):
        """Tests whether a winning line for the specified player crosses the
        given coordinates on the supplied board.
        """
        if self.exact:
            raise NotImplementedError('Support for exact k requirement has not '
                                      'been implemented yet')

        ca, cb, cc, cd = 0, 0, 0, 0
        for i in range(-self.k + 1, self.k):
            tx, txi, ty = x + i, x - i, y + i
            # Test horizontal -
            if tx >= 0 and tx < self.m:
                ca += 1 if board[tx][y] == player else -ca
            # Test vertical |
            if ty >= 0 and ty < self.n:
                cb += 1 if board[x][ty] == player else -cb
            # Test diagonal \
            if tx >= 0 and ty >= 0 and tx < self.m and ty < self.n:
                cc += 1 if board[tx][ty] == player else -cc
            # Test diagonal /
            if txi >= 0 and ty >= 0 and txi < self.m and ty < self.n:
                cd += 1 if board[txi][ty] == player else -cd

            if not self.exact and self.k in (ca, cb, cc, cd):
                return True

        return False

    def whose_turn(self, turn):
        """Determines whose turn it is based on the rule set and a zero-based
        turn index.
        """
        if turn < self.q: return 1
        return int(
            (math.floor((turn - self.q) / self.p) + 1) % self.num_players + 1)

class Game(db.Model):
    """The data structure for an m,n,k,p,q-game.
    """
    state = db.StringProperty(default = 'waiting',
                              choices = ('waiting', 'playing', 'aborted',
                                         'draw', 'win'))
    added = db.DateTimeProperty(auto_now_add = True)
    last_update = db.DateTimeProperty(auto_now = True)
    players = db.ListProperty(item_type = db.Key)
    turn = db.IntegerProperty(default = -1)
    data = db.StringListProperty()
    rule_set = db.ReferenceProperty(reference_class = RuleSet,
                                    required = True,
                                    collection_name = 'games')

    def add_player(self, player):
        if player.key() in self.players:
            raise JoinError('Player is already in game.')
        if len(self.players) >= self.rule_set.num_players:
            raise JoinError('Game is full.')
        if self.state != 'waiting':
            raise JoinError('Game is not accepting new players.')
        
        self.players.append(player.key())

        if len(self.players) == self.rule_set.num_players:
            random.shuffle(self.players)
            self.state = 'playing'
            self.turn = 0
        
        self.put()

    def move(self, player, x, y):
        if self.state != 'playing': raise MoveError('Game not in play.')

        rs = self.rule_set
        np = rs.num_players
        m, n, k, p, q = rs.m, rs.n, rs.k, rs.p, rs.q

        whose_turn = rs.whose_turn(self.turn)
        player_turn = self.players.index(player.key()) + 1

        if whose_turn != player_turn: raise MoveError('Not player\'s turn.')

        board = self.unpack_board()
        if (x < 0 or x >= m or
            y < 0 or y >= n or
            board[x][y]): raise MoveError('Invalid tile position.')

        board[x][y] = whose_turn
        # There's a win according to the rule set.
        if rs.is_win(board, player_turn, x, y):
            player.wins += 1
            player.put()
            for pkey in self.players:
                if pkey == player.key(): continue
                p = Player.get(pkey)
                p.losses += 1
                p.put()
            self.state = 'win'
        # Board has been filled; draw.
        elif not util.contains(board, 0):
            for pkey in self.players:
                p = Player.get(pkey)
                p.draws += 1
                p.put()
            self.state = 'draw'

        # Next turn.
        self.turn += 1

        self.put()

    def pack_board(self):
        if not hasattr(self, '_board'): return
        self.data = [string.join([str(self._board[x][y])
                                  for y in range(self.rule_set.n)], '')
                     for x in range(self.rule_set.m)]

    def put(self):
        self.pack_board()

        if not self.data:
            self.data = ['0' * self.rule_set.m
                         for i in range(self.rule_set.n)]

        db.Model.put(self)

    def unpack_board(self):
        if not hasattr(self, '_board'):
            self._board = [[int(val) for val in list(row)]
                           for row in self.data]
        return self._board
