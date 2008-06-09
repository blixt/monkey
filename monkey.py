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

class Row(object):
    def __init__(self, length, player, expand_points):
        self.length = length
        self.player = player
        self.expand_points = expand_points

    def __repr__(self):
        return '%s(%d, %d, %s)' % (self.__class__.__name__, self.length,
                                   self.player, self.expand_points)

class RowCombos(object):
    """Represents every relevant horizontal, vertical and diagonal row on a
    board.

    A row is considered relevant if it can result in a win or a loss in the
    next turn, or if no such row exists, the longest row that the player has.
    """
    def __init__(self, board, player, win_length, per_turn):
        self.board = board
        self.board_width = len(board)
        self.board_height = len(board[0])
        self.player = player
        self.win_length = win_length
        self.per_turn = per_turn
        self.longest = 0
        self.must_block = False
        self.rows = []
        self.available = []

        ox = self.board_width - 1

        # Horizontal checks
        for y in xrange(0, self.board_height):
            cp1, rl1 = 0, 0
            cp2, rl2 = 0, 0
            cp3, rl3 = 0, 0
            for x in xrange(0, self.board_width + 1):
                # Keep track of available positions
                if x < self.board_width and not self.board[x][y]:
                    self.available.append((x, y))

                cp1, rl1 = self.check(cp1, rl1, x, y, 1, 0)
                # Skip checks that will be made by vertical checks
                if y == 0: continue
                cp2, rl2 = self.check(cp2, rl2, x, y + x, 1, 1)
                cp3, rl3 = self.check(cp3, rl3, ox - x, y + x, -1, 1)

        # Vertical checks
        for x in xrange(0, self.board_width):
            cp1, rl1 = 0, 0
            cp2, rl2 = 0, 0
            cp3, rl3 = 0, 0
            for y in xrange(0, self.board_height + 1):
                cp1, rl1 = self.check(cp1, rl1, x, y, 0, 1)
                cp2, rl2 = self.check(cp2, rl2, y + x, y, 1, 1)
                cp3, rl3 = self.check(cp3, rl3, -y + x, y, -1, 1)

        # Remove irrelevant rows
        def f(x):
            if self.must_block:
                return x.player != player
            else:
                return x.length >= self.longest and x.player == player

        self.rows = filter(f, self.rows)

    def check(self, cur_player, row_len, x, y, dx, dy):
        """Checks a position to determine if it is part of a row and if so,
        store it in the collection along with its expand points.

        Expand points are points before and after the row that can be filled to
        reach the win length.
        
        Rows that cannot reach win length are ignored.
        """
        prev_player = cur_player
        if self.valid(x, y):
            cur_player = self.board[x][y]
        else:
            cur_player = 0

        if cur_player > 0 and cur_player == prev_player:
            row_len += 1
        else:
            if prev_player > 0:
                # Check for available tiles in both directions along the row
                # We'll call these tiles "expand points"
                expand_points = []
                a, b = True, True
                for o in xrange(0, self.win_length - row_len):
                    # After row
                    if a:
                        ox, oy = x + dx * o, y + dy * o
                        if self.valid(ox, oy):
                            if not self.board[ox][oy]:
                                expand_points.append((ox, oy))
                            elif self.board[ox][oy] == prev_player:
                                if prev_player == self.player: row_len += 1
                            else:
                                a = False

                    # Before row
                    if b:
                        do = 1 + row_len + o
                        ox, oy = x - dx * do, y - dy * do
                        if self.valid(ox, oy):
                            if not self.board[ox][oy]:
                                expand_points.append((ox, oy))
                            elif self.board[ox][oy] == prev_player:
                                if prev_player == self.player: row_len += 1
                            else:
                                b = False

                # Only add rows of strategic value
                add = False
                if prev_player == self.player:
                    # Decision making for own row
                    if row_len >= self.longest and row_len + len(expand_points) >= self.win_length:
                        add = not self.must_block
                        self.longest = row_len
                else:
                    # Decision making for opponent row
                    moves = min(self.per_turn, len(expand_points))
                    if row_len + moves >= self.win_length:
                        add = True
                        self.must_block = True
                
                if add:
                    self.rows.append(Row(row_len, prev_player, expand_points))

            row_len = 1

        return cur_player, row_len

    def valid(self, x, y):
        """Returns True if a position is valid; otherwise, False.
        """
        return (x >= 0 and x < self.board_width and
                y >= 0 and y < self.board_height)

class CpuPlayer(object):
    def __init__(self):
        self.player = Player.from_user(users.User('cpu@mnk'), 'CPU')

    def move(self, game):
        """Performs an "intelligent" move.

        How the CPU player thinks (choose first possible move):
        1. If CPU can win, do so!
        2. If an opponent has a row that can result in a win next turn, block
           it.
        3. Find the longest rows the CPU player has that can grow long enough
           to result in a win and extend one of them.
        4. Place a tile randomly on the board.
        """
        player = game.players.index(self.player.key()) + 1
        rules = game.rule_set
        combos = RowCombos(game.unpack_board(), player, rules.k, rules.p)

        if len(combos.rows) > 0:
            # Get a row to work with (rows will already be filtered according to
            # the rules above)
            row = random.choice(combos.rows)
            # Only choose between some of the first expand points
            x, y = random.choice(row.expand_points[0:1])
        else:
            x, y = random.choice(combos.available)

        game.move(self.player, x, y)

class Player(db.Model):
    user = db.UserProperty()
    nickname = db.StringProperty()
    draws = db.IntegerProperty(default = 0)
    losses = db.IntegerProperty(default = 0)
    wins = db.IntegerProperty(default = 0)
    session = db.StringProperty()
    expires = db.IntegerProperty()

    @staticmethod
    def from_user(user, nickname = None):
        """Gets a Player instance from a User instance.
        """
        player = Player.gql('WHERE user = :1', user).get()
        if not player:
            if not nickname: nickname = user.nickname()
            player = Player(user = user,
                            nickname = nickname)
            player.put()

        return player

    @staticmethod
    def get_current(session = None):
        """Retrieves a Player instance for the currently logged in user.
        """
        curuser = users.get_current_user()
        if curuser:
            # User is logged in with a Google account.
            player = Player.from_user(curuser)
        else:
            player = Player.gql('WHERE session = :1 '
                                'AND expires > :2',
                                session, time.time()).get()
            if not player:
                pass # Require that the user register or log in

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
        for i in xrange(-self.k + 1, self.k):
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
        self.handle_cpu()

    def handle_cpu(self):
        if self.state != 'playing': return

        cpu = CpuPlayer()
        key = cpu.player.key()
        if key in self.players:
            turn = self.players.index(key) + 1
            if turn == self.current_player:
                cpu.move(self)
    
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
        self.handle_cpu()

    def pack_board(self):
        """Packs a list of lists into a list of strings, where each character
        represents a value in a sub-list.
        """
        if not hasattr(self, '_board'): return
        self.data = [string.join([str(self._board[x][y])
                                  for y in xrange(self.rule_set.n)], '')
                     for x in xrange(self.rule_set.m)]

    def put(self):
        """Does some additional processing before the entity is stored to the
        data store.
        """
        if self.is_saved():
            self.pack_board()
        else:
            # Set up a data structure that can store an m by n table.
            self.data = ['0' * self.rule_set.m
                         for i in xrange(self.rule_set.n)]

        db.Model.put(self)

    def remove_player(self, player):
        """Removes a player from the game or deletes the game if removing the
        player would make the game empty from players.
        """
        if player.key() not in self.players:
            raise LeaveError('Player is not in game.')

        if self.state == 'waiting':
            if len(self.players) > 1:
                self.players.remove(player.key())
                self.update_player_names()
                self.put()
            else:
                self.delete()
        elif self.state == 'playing':
            self.state = 'aborted'
            self.turn = -1
            self.put()
        else:
            raise LeaveError('Cannot leave game.')

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
