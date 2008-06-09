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

class ForcedMove(Exception):
    """Special exception for stopping board scanning and returning a position
    """
    pass

class CpuPlayer(object):
    def __init__(self):
        self.player = Player.from_user(users.User('cpu@mnk'), 'CPU')

    def check(self, cur_player, row_len, x, y, dx, dy):
        """Checks a position to determine if it is part of a row and if so,
        store it in a collection along with its expand points.

        Expand points are points before and after the row that can be filled to
        reach the win length.
        
        Rows that cannot reach win length are ignored.
        """
        prev_player = cur_player
        if self.valid(x, y):
            cur_player = self.board[x][y]
        else:
            cur_player = 0

        wl = self.win_length

        if cur_player > 0 and cur_player == prev_player:
            row_len += 1
        else:
            if prev_player > 0:
                al, bl = True, True
                af, bf = 0, 0
                au, bu = 0, 0
                ac, bc = None, None
                for o in xrange(0, wl - row_len):
                    # After row
                    if al:
                        ox, oy = x + dx * o, y + dy * o
                        if self.valid(ox, oy):
                            if not self.board[ox][oy]:
                                if o == 0: ac = (ox, oy)
                                af += 1
                            elif self.board[ox][oy] == prev_player:
                                au += 1
                            else:
                                al = False

                    # Before row
                    if bl:
                        do = 1 + row_len + o
                        ox, oy = x - dx * do, y - dy * do
                        if self.valid(ox, oy):
                            if not self.board[ox][oy]:
                                if o == 0: bc = (ox, oy)
                                bf += 1
                            elif self.board[ox][oy] == prev_player:
                                bu += 1
                            else:
                                bl = False

                if prev_player == self.index:
                    # Decision making for own row
                    if ac and row_len + au + 1 >= wl:
                        raise ForcedMove(ac)

                    if bc and row_len + bu + 1 >= wl:
                        raise ForcedMove(bc)
                else:
                    # Decision making for opponent row
                    if row_len + au + min(self.per_turn, af) >= wl:
                        raise ForcedMove(ac)

                    if row_len + bu + min(self.per_turn, bf) >= wl:
                        raise ForcedMove(bc)

                if ac and row_len + au + af >= wl and (au > bu or not bc):
                    self.rows.append([row_len + au + bu / 2, ac])
                elif bc and row_len + bu + bf >= wl:
                    self.rows.append([row_len + bu + au / 2, bc])

            row_len = 1

        return cur_player, row_len

    def move(self, game):
        """Performs an "intelligent" move.

        How the CPU player thinks (choose first possible move):
        1. If CPU can win, do so!
        2. If an opponent has a row that can result in a win next turn, block
           it.
        3. Find the longest rows the CPU player has that can grow long enough
           to result in a win and extend one of them.
        4. Place a tile near the middle of the board.
        """
        self.board = game.unpack_board()
        self.index = game.players.index(self.player.key()) + 1

        rules = game.rule_set
        self.board_width = rules.m
        self.board_height = rules.n
        self.win_length = rules.k
        self.per_turn = rules.p
        self.rows = []

        loc = None
        ox = self.board_width - 1

        try:
            # Horizontal checks
            for y in xrange(0, self.board_height):
                cp1, rl1 = 0, 0
                cp2, rl2 = 0, 0
                cp3, rl3 = 0, 0
                for x in xrange(0, self.board_width + 1):
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

            if len(self.rows) > 0:
                # Order rows by importance
                def o(x, y):
                    s = cmp(y[0], x[0])
                    return random.randint(-1, 1) if not s else s

                self.rows.sort(o)
                loc = self.rows[0][1]
        except ForcedMove, (c,):
            loc = c

        if not loc:
            # Crazy, inefficient method of getting all positions, in order of
            # closeness to center
            locs = [(x, y)
                    for y in xrange(self.board_height)
                    for x in xrange(self.board_width)]

            cx, cy = int(self.board_width / 2), int(self.board_height / 2)
            def closer(x, y):
                return cmp((x[0] - cx) ** 2 + (x[1] - cy) ** 2,
                           (y[0] - cx) ** 2 + (y[1] - cy) ** 2)

            locs.sort(closer)

            for loc in locs:
                if not self.board[loc[0]][loc[1]]: break

        game.move(self.player, loc[0], loc[1])

    def valid(self, x, y):
        """Returns True if a position is valid; otherwise, False.
        """
        return (x >= 0 and x < self.board_width and
                y >= 0 and y < self.board_height)

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
            if self.players.index(key) + 1 == self.current_player:
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
