# -*- coding: cp1252 -*-
#
# Copyright (c) 2008-2010 Andreas Blixt <andreas@blixt.org>
# Project homepage: <http://github.com/blixt/monkey>
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
a stone of their color on an m�n board, the winner being the player who first
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

from datetime import datetime, timedelta
import hashlib, random, re, string, time, util, uuid

class Error(Exception):
    """Base of all exceptions in the monkey module."""
    pass

class AbortError(Error):
    """Thrown when a game cannot be aborted."""
    pass

class CpuError(Error):
    """Thrown when the AI fails."""
    pass

class JoinError(Error):
    """Thrown when a player cannot join a game."""
    pass

class LeaveError(Error):
    """Thrown when a player cannot leave a game."""
    pass

class LogInError(Error):
    """Thrown when a login attempt fails."""
    pass

class MoveError(Error):
    """Thrown when a move cannot be made."""
    pass

class PlayerNameError(Error):
    """Thrown when an error related to the name of a player is encountered.
    """

class ForcedMove(Exception):
    """Special exception for stopping board scanning and returning a position
    """
    pass

class CpuPlayer(object):
    def __init__(self, player = None, cleverness = 10.0):
        self.player = player
        self.cleverness = cleverness

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

        if cur_player > 0 and cur_player == prev_player:
            row_len += 1
        elif prev_player > 0:
            al, bl = True, True
            af, bf = 0, 0
            au, bu = 0, 0
            ac, bc = None, None
            for o in xrange(0, self.win_length - row_len):
                # After row.
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
                    else:
                        al = False

                # Before row.
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
                    else:
                        bl = False

            if ac: self.handle_move(ac, prev_player, row_len + au, af, bf)
            if bc: self.handle_move(bc, prev_player, row_len + bu, bf, af)

            row_len = 1
        else:
            row_len = 1

        return cur_player, row_len

    def handle_move(self, move, player, length, avail, oavail):
        """Determines how a move should be handled and the value of the move.
        """
        cpu = player == self.index
        
        # Force a move to win or prevent a loss.
        # Blocking is queued until after all rows have been processed
        # to avoid blocking when a win could have been achieved.
        max_expansion = min(self.turns_left if cpu else self.per_turn, avail)
        if length + max_expansion >= self.win_length:
            if cpu:
                raise ForcedMove(move)
            else:
                self.force.append(move)

        # Ignore the move if it cannot ever result in a win.
        if length + avail + oavail >= self.win_length:
            # Calculate the value of the move.
            score = length * 6.0 + avail
            if cpu: score += self.win_length * 2.0
            self.moves.append([score, move])

    def join(self, game):
        """Adds a CPU player to a game.
        """
        players = Player.all()
        players.filter('user =', users.User('cpu@mnk'))

        # Choose first CPU player that is not already in the game.
        for player in players:
            if player.key() not in game.players:
                player.join(game)
                self.player = player
                return

        # Create a new CPU player.
        player = Player(user = users.User('cpu@mnk'),
                        nickname = 'CPU')
        player.put()

        player.join(game)
        self.player = player

    def move(self, game):
        """Performs an "intelligent" move.

        How the CPU player thinks (choose first possible move):
        1. If CPU can win, do so!
        2. If an opponent has a row that can result in a win next turn, block
           it.
        3. Value all possible moves and choose the one with the highest value.
        4. Place a tile near the middle of the board.
        """
        if not self.player:
            raise CpuError('Can not move before being assigned a player.')
        
        self.board = game.unpack_board()
        self.index = game.players.index(self.player.key()) + 1

        rules = game.rule_set
        self.board_width = rules.m
        self.board_height = rules.n
        self.win_length = rules.k
        self.per_turn = rules.p
        self.turns_left = rules.turns_left(game.turn)
        self.force = []
        self.moves = []

        loc = None
        ox = self.board_width - 1

        try:
            # Horizontal checks.
            for y in xrange(0, self.board_height):
                cp1, rl1 = 0, 0
                cp2, rl2 = 0, 0
                cp3, rl3 = 0, 0
                for x in xrange(0, self.board_width + 1):
                    cp1, rl1 = self.check(cp1, rl1, x, y, 1, 0)

                    # Skip checks that will be made by vertical checks.
                    if y == 0: continue

                    cp2, rl2 = self.check(cp2, rl2, x, y + x, 1, 1)
                    cp3, rl3 = self.check(cp3, rl3, ox - x, y + x, -1, 1)

            # Vertical checks.
            for x in xrange(0, self.board_width):
                cp1, rl1 = 0, 0
                cp2, rl2 = 0, 0
                cp3, rl3 = 0, 0
                for y in xrange(0, self.board_height + 1):
                    cp1, rl1 = self.check(cp1, rl1, x, y, 0, 1)
                    cp2, rl2 = self.check(cp2, rl2, y + x, y, 1, 1)
                    cp3, rl3 = self.check(cp3, rl3, -y + x, y, -1, 1)

            m = self.moves
            if len(m) > 0:
                # Merge moves to the same location.
                for a in xrange(len(m)):
                    try:
                        # Value, coordinate
                        av, ac = m[a][0], m[a][1]
                        
                        # Looping backwards so that index is not affected by
                        # deleting items in the list.
                        for b in xrange(len(m) - 1, a):
                            bv, bc = m[b][0], m[b][1]
                            
                            # Same coordinates?
                            if ac == bc:
                                mn, mx = (av, bv) if av < bv else (bv, av)
                                av = mx + mn / 2.0
                                del m[b]

                        m[a][0] = av
                    except KeyError:
                        # Reached the end of the list; stop the loop.
                        break

                # Order moves by score.
                def o(x, y):
                    s = cmp(int(y[0] * self.cleverness),
                            int(x[0] * self.cleverness))
                    return random.randint(-1, 1) if not s else s

                m.sort(o)

                # Forcing is done after merging and sorting so that the best
                # block can be chosen.
                if len(self.force) > 0:
                    for move in m:
                        if move[1] in self.force:
                            raise ForcedMove(move[1])

                # Perform best move.
                loc = m[0][1]
        except ForcedMove, (c,):
            loc = c

        if not loc:
            # Crazy, inefficient method of getting all positions, in order of
            # closeness to center.
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
    password = db.StringProperty()
    draws = db.IntegerProperty(default = 0)
    losses = db.IntegerProperty(default = 0)
    wins = db.IntegerProperty(default = 0)
    session = db.StringProperty()
    expires = db.DateTimeProperty()

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
    def get_current(handler):
        """Retrieves a Player instance for the currently logged in user.
        """
        curuser = users.get_current_user()
        if curuser:
            # User is logged in with a Google account.
            player = Player.from_user(curuser)
        else:
            try:
                # User has a session.
                session = handler.request.cookies['session']
                query = Player.all()
                query.filter('session =', session)
                query.filter('expires >', datetime.utcnow())
                player = query.get()
            except KeyError:
                player = None

            if not player:
                # Create a new anonymous player.
                player = Player(user = users.User('anonymous@mnk'),
                                nickname = 'Anonymous')
                player.start_session(handler)

        return player

    @staticmethod
    def log_in(nickname, password, handler):
        """Retrieves a player instance, based on a nickname and a password, and
        starts a session.

        The SHA-256 hash of the password must match the hash stored in the
        database, otherwise an exception will be raised.
        """
        player = Player.all().filter('nickname =', nickname).get()
        if not player:
            raise LogInError('Could not find a player with the specified '
                             'nickname.')

        if player.user != users.User('player@mnk'):
            raise LogInError('Cannot log in as that user.')

        if hashlib.sha256(password).hexdigest() != player.password:
            raise LogInError('Invalid password.')

        player.start_session(handler)
        return player

    @staticmethod
    def register(nickname, password, handler = None):
        """Creates a new player that is registered to the application (instead
        of using Google Accounts.)

        Only the SHA-256 hash of the password will be stored so that in case the
        database should be exposed, the passwords would not be of any use to the
        attacker.
        """
        try:
            Player.validate(nickname)
        except PlayerNameError, e:
            raise RegisterError('Could not use nickname (%s)' % (e))

        if len(password) < 4:
            raise RegisterError('Password should be at least 4 characters '
                                'long.')

        player = Player(user = users.User('player@mnk'),
                        nickname = nickname,
                        password = hashlib.sha256(password).hexdigest())

        if handler:
            player.start_session(handler)
        else:
            player.put()

        return player
        
    @staticmethod
    def validate(nickname):
        """Validates a nickname and throws an exception if it's invalid.
        """
        if nickname in ('Anonymous', 'CPU'):
            raise PlayerNameError(nickname + ' is a reserved nickname.')
        
        if not re.match('^[A-Za-z]([\\-\\._ ]?[A-Z0-9a-z]+)*$', nickname):
            raise PlayerNameError('Nickname should start with a letter, '
                                  'followed by letters and/or digits, '
                                  'optionally with dashes, periods, '
                                  'underscores or spaces inbetween.')
        if len(nickname) < 3:
            raise PlayerNameError('Nickname should be at least three '
                                  'characters long.')
        if len(nickname) > 20:
            raise PlayerNameError('Nickname must not be any longer than 20 '
                                  'characters.')

        if Player.all().filter('nickname =', nickname).count() > 0:
            raise PlayerNameError('Nickname is already in use.')

        return True

    def display_name(self):
        return '%s (%d)' % (self.nickname, self.wins)

    def is_anonymous(self):
        return self.user == users.User('anonymous@mnk')

    def join(self, game):
        """Convenience method for adding a player to a game.
        """
        game.add_player(self)

    def leave(self, game):
        """Convenience method for removing a player from a game.
        """
        game.remove_player(self)

    def rename(self, nickname):
        """Changes the nickname of the player.
        """
        if nickname == self.nickname: return

        if nickname == 'Anonymous' and self.user == users.User('anonymous@mnk'):
            pass
        else:
            Player.validate(nickname)

        self.nickname = nickname
        self.put()

        # This results in very long query times and might have to be disabled.
        # Everything would still work, it's just that games created before the
        # player changed nickname will still show the old nickname.
        games = Game.all().filter('players =', self.key())
        for game in games:
            game.update_player_names()
            game.put()

    def end_session(self, handler):
        """Removes a session from the database and the client, effectively
        logging the player out.
        """
        self.session = None
        self.expires = None
        self.put()
        
        cookie = 'session=; expires=Fri, 31-Jul-1987 03:00:00 GMT'
        handler.response.headers['Set-Cookie'] = cookie
        del handler.request.cookies['session']

    def start_session(self, handler):
        """Gives the player a session id and stores it as a cookie in the user's
        browser.
        """
        self.session = uuid.uuid4().get_hex()
        self.expires = datetime.utcnow() + timedelta(days = 7)
        self.put()

        # Build and set cookie
        ts = time.strftime('%a, %d-%b-%Y %H:%M:%S GMT',
                           self.expires.timetuple())
        cookie = '%s=%s; expires=%s' % ('session', self.session, ts)

        handler.response.headers['Set-Cookie'] = cookie
        handler.request.cookies['session'] = self.session

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

    @classmethod
    def get_list(cls):
        rule_sets = list(cls.all().order('name'))
        if not rule_sets:
            rule_sets = [
                cls(name='Tic-tac-toe', m=3, n=3, k=3),
                cls(name='Free-style gomoku', m=19, n=19, k=5),
                cls(name='Four player gomoku', m=19, n=19, k=5, num_players=4),
                cls(name='Connect6', m=19, n=19, k=6, p=2, q=1),
            ]
            db.put(rule_sets)
        return rule_sets

    def is_win(self, board, player, x, y):
        """Tests whether a winning line for the specified player crosses the
        given coordinates on the supplied board.
        """
        if self.exact:
            raise NotImplementedError('Support for exact k requirement has not '
                                      'been implemented yet.')

        ca, cb, cc, cd = 0, 0, 0, 0
        for i in xrange(-self.k + 1, self.k):
            tx, txi, ty = x + i, x - i, y + i
            # Test horizontal. --
            if tx >= 0 and tx < self.m:
                ca += 1 if board[tx][y] == player else -ca
            # Test vertical. |
            if ty >= 0 and ty < self.n:
                cb += 1 if board[x][ty] == player else -cb
            # Test diagonal. \
            if tx >= 0 and ty >= 0 and tx < self.m and ty < self.n:
                cc += 1 if board[tx][ty] == player else -cc
            # Test diagonal. /
            if txi >= 0 and ty >= 0 and txi < self.m and ty < self.n:
                cd += 1 if board[txi][ty] == player else -cd

            if not self.exact and self.k in (ca, cb, cc, cd):
                return True

        return False

    def turns_left(self, turn):
        """Determine the number of turns until it's another player's turn.
        """
        if turn < self.q: return self.q - turn
        return self.p - (turn - self.q) % self.p

    def whose_turn(self, turn):
        """Determines whose turn it is based on the rule set and a zero-based
        turn index.
        """
        if turn < self.q: return 1
        return int((turn - self.q) / self.p + 1) % self.num_players + 1

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
    last_update = db.DateTimeProperty(auto_now_add = True)

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
        self.put(True)

    def abort(self):
        """Aborts a game if it is in play or removes it if it's waiting for more
        players.
        """
        if self.state == 'waiting':
            self.delete()
        elif self.state == 'playing':
            self.state = 'aborted'
            self.turn = -1
            self.put(True)
        else:
            raise AbortError('Cannot abort a game that has already been '
                             'completed.')

    def handle_cpu(self):
        """If the current player is a CPU player, makes a move.
        """
        if self.state != 'playing': return

        player = db.get(self.players[self.current_player - 1])
        if player.user == users.User('cpu@mnk'):
            cpu = CpuPlayer(player)
            cpu.move(self)
    
    def move(self, player, x, y):
        """Puts a tile at the specified coordinates and makes sure all game
        rules are followed.
        """
        pkey = player.key()
        if pkey not in self.players: raise MoveError('Player not in game.')

        if self.state != 'playing': raise MoveError('Game not in play.')

        whose_turn = self.current_player
        player_turn = self.players.index(pkey) + 1
        if whose_turn != player_turn: raise MoveError('Not player\'s turn.')

        rs = self.rule_set
        np = rs.num_players
        m, n, k, p, q = rs.m, rs.n, rs.k, rs.p, rs.q

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

        self.put(True)

    def pack_board(self):
        """Packs a list of lists into a list of strings, where each character
        represents a value in a sub-list.
        """
        if not hasattr(self, '_board'): return
        self.data = [string.join([str(self._board[x][y])
                                  for y in xrange(self.rule_set.n)], '')
                     for x in xrange(self.rule_set.m)]

    def put(self, update_time = False):
        """Does some additional processing before the entity is stored to the
        data store.
        """
        if self.is_saved():
            self.pack_board()
        else:
            # Set up a data structure that can store an m by n table.
            self.data = ['0' * self.rule_set.m
                         for i in xrange(self.rule_set.n)]

        if update_time: self.last_update = datetime.utcnow()
        db.Model.put(self)

    def remove_player(self, player):
        """Removes a player from the game or deletes the game if removing the
        player would make the game empty from players.
        """
        if player.key() not in self.players:
            raise LeaveError('Player is not in game.')

        if self.state == 'waiting':
            self.players.remove(player.key())

            # Determine the number of non-CPU players.
            humans = len(self.players)
            for pkey in self.players:
                if db.get(pkey).user == users.User('cpu@mnk'):
                    humans -= 1

            # Only keep the game if there are non-CPU players left in the game.
            if humans > 0:
                self.update_player_names()
                self.put(True)
            else:
                self.delete()
        elif self.state == 'playing':
            # A player cannot actually leave a game that is in play. Instead,
            # the game is aborted and becomes unplayable.
            self.abort()
        else:
            raise LeaveError('Cannot leave a game that has already been '
                             'completed.')

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
