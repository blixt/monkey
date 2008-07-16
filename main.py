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

"""Google App Engine entry point for the MoNKey! game.

Registers the WSGI web application with request handlers, also defined
in this file.
"""

from google.appengine.api import users
from google.appengine.ext import db, webapp

import wsgiref.handlers

from datetime import datetime, timedelta
import monkey, re, util

class Error(Exception):
    """Base of all exceptions in the MoNKey! game interface."""
    pass

class GameService(util.ServiceHandler):
    """Methods that can be called through HTTP (intended to be called by
    JavaScript through an XmlHttpRequest object.)
    """
    def add_cpu_player(self, game):
        """Adds a CPU player to a game.
        """
        if not isinstance(game, monkey.Game):
            game = monkey.Game.get_by_id(game)
            if not game:
                raise ValueError('Invalid game id.')

        player = monkey.Player.get_current(self)
        if not player.key() in game.players:
            raise Error('You cannot add a CPU player to a game you\'re not in.')

        cpu = monkey.CpuPlayer()
        cpu.join(game)

        return self.get_game_status(game)

    def change_nickname(self, nickname):
        """Changes the nickname of the current player.
        """
        player = monkey.Player.get_current(self)
        player.rename(nickname)
        return self.get_player_info()

    def cpu_battle(self, rule_set):
        """Creates a new game with only CPU players.
        """
        if not isinstance(rule_set, monkey.RuleSet):
            rule_set = monkey.RuleSet.get_by_id(rule_set)
            if not rule_set: raise ValueError('Invalid rule set id.')

        game = monkey.Game(rule_set = rule_set)
        game.put()

        for i in xrange(rule_set.num_players):
            cpu = monkey.CpuPlayer()
            cpu.join(game)

        return game.key().id()
        
    def create_game(self, rule_set):
        """Creates a new game.
        """
        if not isinstance(rule_set, monkey.RuleSet):
            rule_set = monkey.RuleSet.get_by_id(rule_set)
            if not rule_set: raise ValueError('Invalid rule set id.')

        player = monkey.Player.get_current(self)
        game = monkey.Game(rule_set = rule_set)
        game.put()

        player.join(game)

        return game.key().id()

    def create_rule_set(self, name, m, n, k, p = 1, q = 1, num_players = 2):
        """Creates a new rule set.
        """
        if not re.match('^[\\w]([\\w&\'\\- ]{0,28}[\\w\'!])$', name):
            raise ValueError('Invalid name.')

        rule_set = monkey.RuleSet(name = name,
                                  author = monkey.Player.get_current(self),
                                  num_players = num_players,
                                  m = m, n = n, k = k,
                                  p = p, q = q)
        rule_set.put()

        return rule_set.key().id()

    def get_game_status(self, game, turn = None):
        """Gets the status of game.
        """
        if not isinstance(game, monkey.Game):
            game = monkey.Game.get_by_id(game)
            if not game: raise ValueError('Invalid game id.')

        if turn != None and game.turn == turn: return False

        pkey = monkey.Player.get_current(self).key()
        if pkey in game.players:
            playing_as = game.players.index(pkey) + 1
        else:
            playing_as = 0
        
        status = {
            'players': game.player_names,
            'board': game.unpack_board(),
            'playing_as': playing_as,
            'current_player': game.current_player,
            'state': game.state,
            'turn': game.turn,
            'rule_set_id': game.rule_set.key().id() }

        game.handle_cpu()

        return status

    def get_games(self, mode = 'play'):
        """Returns a list of games relevant to the current player.

        Modes:
            play - Returns games that the player is playing or can join.
            view - Returns games that other players are playing.
            past - Returns recent games that the player has played.
        """
        pkey = monkey.Player.get_current(self).key()

        if mode == 'play':
            playing = monkey.Game.all()
            playing.filter('state =', 'playing')
            playing.filter('players =', pkey)
            playing.order('-last_update')

            waiting = monkey.Game.all()
            waiting.filter('state =', 'waiting')
            waiting.order('-last_update')

            results = list(playing) + waiting.fetch(10)
        elif mode == 'view':
            playing = monkey.Game.all()
            playing.filter('state =', 'playing')
            playing.order('-last_update')

            results = playing.fetch(10)
        elif mode == 'past':
            history = monkey.Game.gql('WHERE state IN :1 AND '
                                      'players = :2 ORDER BY last_update DESC',
                                      ['aborted', 'win', 'draw'], pkey)

            results = history.fetch(10)
        else:
            raise ValueError('Invalid mode.')

        now = datetime.utcnow()
        games = []
        for game in results:
            # Don't include games that can be considered abandoned.
            # - Games that are waiting for players are considered abandoned
            #   after six hours.
            # - Games that are in play are considered abandoned after 48 hours.
            age = now - game.last_update
            age = age.seconds / 3600.0 + age.days * 24.0
            if ((game.state == 'waiting' and age > 6) or
                (game.state == 'playing' and age > 48)):
                # Abort the game to speed up future queries.
                game.abort()

                # break instead of continue so that only one game is aborted per
                # request (spreads out load between requests if many games have
                # timed out since last request.)
                break

            # Determine the position of the player if the player is in the game.
            if pkey in game.players:
                playing_as = game.players.index(pkey) + 1
            else:
                playing_as = 0

            games.append({
                'id': game.key().id(),
                'players': game.player_names,
                'current_player': game.current_player,
                'playing_as': playing_as,
                'rule_set_id': game.rule_set.key().id(),
                'state': game.state })

        return games
        
    def get_player_info(self):
        """Gets information about the currently logged in player.
        """
        user = users.get_current_user()
        if user:
            log_url = users.create_logout_url('/')
        else:
            log_url = users.create_login_url('/')
        
        player = monkey.Player.get_current(self)
        return { 'nickname': player.nickname,
                 'anonymous': player.is_anonymous(),
                 'log_url': log_url,
                 'wins': player.wins,
                 'losses': player.losses,
                 'draws': player.draws }

    def get_rule_sets(self):
        """Gets all rule sets.
        """
        rule_sets = []
        for rule_set in monkey.RuleSet.all().order('name'):
            rule_sets.append({ 'id': rule_set.key().id(),
                               'name': rule_set.name,
                               'num_games': rule_set.num_games,
                               'num_players': rule_set.num_players,
                               'exact': rule_set.exact,
                               'm': rule_set.m, 'n': rule_set.n,
                               'k': rule_set.k, 'p': rule_set.p,
                               'q': rule_set.q })
        return rule_sets

    def join_game(self, game):
        """Joins an existing game.
        """
        if not isinstance(game, monkey.Game):
            game = monkey.Game.get_by_id(game)
            if not game: raise ValueError('Invalid game id.')

        player = monkey.Player.get_current(self)
        player.join(game)

        return self.get_game_status(game)

    def leave_game(self, game):
        """Leaves an existing game.
        """
        if not isinstance(game, monkey.Game):
            game = monkey.Game.get_by_id(game)
            if not game: raise ValueError('Invalid game id.')

        player = monkey.Player.get_current(self)
        player.leave(game)

    def put_tile(self, game, x, y):
        """Places a tile on the board of the specified game.
        """
        if not isinstance(game, monkey.Game):
            game = monkey.Game.get_by_id(game)
            if not game: raise ValueError('Invalid game id.')

        player = monkey.Player.get_current(self)
        game.move(player, x, y)

        return self.get_game_status(game)

def main():
    application = webapp.WSGIApplication([
        ('/game/(\\w*)', GameService)
    ])
    wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
    main()
