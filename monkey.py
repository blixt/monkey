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

This engine also supports Connect(m,n,k,p,q)-games, where q is the number of
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

class LeaveError(Error):
    """Thrown when a player cannot leave a game."""
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
        """Retrieves a Player instance for the currently logged in user.
        """
        curuser = users.get_current_user()
        player = Player.gql('WHERE user = :1', curuser).get()
        if not player:
            player = Player(user = curuser,
                            nickname = curuser.nickname())
            player.put()

        return player

    def join(self, game):
        """Convenience method for adding a player to a game.
        """
        game.add_player(self)

    def leave(self, game):
        """Convenience method from removing a player from a game.
        """
        game.remove_player(self)

class RuleSet(db.Model):
    """A rule set for an m,n,k,p,q-game.
    """
    name = db.StringProperty(required = True)
    author = db.ReferenceProperty(Player)
    num_players = db.IntegerProperty(choices = (2, 3, 4, 5, 6, 7, 8, 9),
                                     default = 2,
                                     verbose_name = 'Number of players')
    num_games = db.IntegerProperty(default = 0)
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
    players = db.ListProperty(item_type = db.Key)
    player_names = db.StringListProperty()
    current_player = db.IntegerProperty()
    turn = db.IntegerProperty(default = -1)
    data = db.StringListProperty()
    rule_set = db.ReferenceProperty(reference_class = RuleSet,
                                    required = True,
                                    collection_name = 'games')
    added = db.DateTimeProperty(auto_now_add = True)
    last_update = db.DateTimeProperty(auto_now = True)

    def add_player(self, player):
        """Adds a player to the game and starts the game if it has enough
        players.
        """
        if player.key() in self.players:
            raise JoinError('Player is already in game.')
        if len(self.players) >= self.rule_set.num_players:
            raise JoinError('Game is full.')
        if self.state != 'waiting':
            raise JoinError('Game is not accepting new players.')
        
        self.players.append(player.key())

        # Start the game when it has enough players.
        if len(self.players) == self.rule_set.num_players:
            random.shuffle(self.players)
            self.state = 'playing'
            self.turn = 0
            self.current_player = 1

        self.update_player_names()
        self.put()

    def move(self, player, x, y):
        """Puts a tile at the specified coordinates and makes sure all game
        rules are followed.
        """
        if self.state != 'playing': raise MoveError('Game not in play.')

        rs = self.rule_set
        np = rs.num_players
        m, n, k, p, q = rs.m, rs.n, rs.k, rs.p, rs.q

        whose_turn = self.current_player

        player_turn = self.players.index(player.key()) + 1
        if whose_turn != player_turn: raise MoveError('Not player\'s turn.')

        board = self.unpack_board()
        if (x < 0 or x >= m or
            y < 0 or y >= n or
            board[x][y]): raise MoveError('Invalid tile position.')

        board[x][y] = whose_turn

        # Next turn.
        self.turn += 1

        # There's a win according to the rule set.
        if rs.is_win(board, player_turn, x, y):
            self.state = 'win'

            player.wins += 1
            player.put()
            for pkey in self.players:
                if pkey == player.key(): continue
                p = db.get(pkey)
                p.losses += 1
                p.put()

            self.rule_set.num_games += 1
            self.rule_set.put()
        # Board has been filled; draw.
        elif not util.contains(board, 0):
            self.state = 'draw'

            for pkey in self.players:
                p = db.get(pkey)
                p.draws += 1
                p.put()

            self.rule_set.num_games += 1
            self.rule_set.put()
        else:
            self.current_player = rs.whose_turn(self.turn)

        self.put()

    def pack_board(self):
        """Packs a list of lists into a list of strings, where each character
        represents a value in a sub-list.
        """
        if not hasattr(self, '_board'): return
        self.data = [string.join([str(self._board[x][y])
                                  for y in range(self.rule_set.n)], '')
                     for x in range(self.rule_set.m)]

    def put(self):
        """Does some additional processing before the entity is stored to the
        data store.
        """
        if self.is_saved():
            self.pack_board()
        else:
            # Set up a data structure that can store an m by n table.
            self.data = ['0' * self.rule_set.m
                         for i in range(self.rule_set.n)]

        db.Model.put(self)

    def remove_player(self, player):
        """Removes a player from the game or deletes the game if removing the
        player would make the game empty from players.
        """
        if player.key() not in self.players:
            raise LeaveError('Player is not in game.')
        if self.state != 'waiting':
            raise LeaveError('Cannot leave game.')

        if len(self.players) > 1:
            self.players.remove(player.key())
            self.update_player_names()
            self.put()
        else:
            self.delete()

    def unpack_board(self):
        """Unpacks a list of strings into a list of lists where each character
        in the list of strings represents a value in a sub-list.
        """
        if not hasattr(self, '_board'):
            self._board = [[int(val) for val in list(row)]
                           for row in self.data]
        return self._board

    def update_player_names(self):
        """Synchronizes the 'player_names' list with the names of the players in
        the game.
        """
        self.player_names = [db.get(p).nickname
                             for p in self.players]
