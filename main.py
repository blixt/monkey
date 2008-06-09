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

from google.appengine.ext import db, webapp

import wsgiref.handlers
import monkey, re, util

class GameService(util.ServiceHandler):
    """Methods that can be called through HTTP (intended to be called by
    JavaScript through an XmlHttpRequest object.
    """
    def add_cpu_player(self, game_id):
        """Adds the CPU player to a game.
        """
        game = monkey.Game.get_by_id(game_id)
        if not game: raise ValueError('Invalid game id.')

        cpu = monkey.CpuPlayer()
        cpu.player.join(game)

        return self.status(game_id)
        
    def create(self, rule_set_id):
        """Creates a new game.
        """
        rule_set = monkey.RuleSet.get_by_id(rule_set_id)
        if not rule_set: raise ValueError('Invalid rule set id.')

        player = monkey.Player.get_current()
        game = monkey.Game(rule_set = rule_set)
        game.put()

        player.join(game)

        return game.key().id()
    
    def join(self, game_id):
        """Joins an existing game.
        """
        game = monkey.Game.get_by_id(game_id)
        if not game: raise ValueError('Invalid game id.')

        player = monkey.Player.get_current()
        player.join(game)

        return self.status(game_id)

    def leave(self, game_id):
        """Leaves an existing game.
        """
        game = monkey.Game.get_by_id(game_id)
        if not game: raise ValueError('Invalid game id.')

        player = monkey.Player.get_current()
        player.leave(game)

    def list(self, mode = 'play'):
        """Returns a list of games relevant to the current player.

        Modes:
            play - Returns games that the player is playing or can join.
            view - Returns games that other players are playing.
            past - Returns recent games that the player has played.
        """
        pkey = monkey.Player.get_current().key()

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

            results = filter(lambda g: pkey not in g.players, playing.fetch(15))
        elif mode == 'past':
            history = monkey.Game.gql('WHERE state IN :1 AND '
                                      'players = :2 ORDER BY last_update DESC',
                                      ['aborted', 'win', 'draw'], pkey)

            results = history.fetch(10)
        else:
            raise ValueError('Invalid mode.')

        games = []
        for game in results:
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
        
    def move(self, game_id, x, y):
        """Places a tile on the board of the specified game.
        """
        game = monkey.Game.get_by_id(game_id)
        if not game: raise ValueError('Invalid game id.')

        player = monkey.Player.get_current()
        game.move(player, x, y)

        return self.status(game_id)

    def new_rule_set(self, name, m, n, k, p = 1, q = 1, num_players = 2):
        """Creates a new rule set.
        """
        if not re.match('^[\\w]([\\w&\'\\- ]{0,28}[\\w\'!])$', name):
            raise ValueError('Invalid name.')

        rule_set = monkey.RuleSet(name = name,
                                  author = monkey.Player.get_current(),
                                  num_players = num_players,
                                  m = m, n = n, k = k,
                                  p = p, q = q)
        rule_set.put()

        return rule_set.key().id()

    def rule_sets(self):
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

    def status(self, game_id, turn = None):
        """Gets the status of game.
        """
        game = monkey.Game.get_by_id(game_id)
        if not game: raise ValueError('Invalid game id.')

        if turn != None and game.turn == turn: return False

        pkey = monkey.Player.get_current().key()
        if pkey in game.players:
            playing_as = game.players.index(pkey) + 1
        else:
            playing_as = 0
        
        return {
            'players': game.player_names,
            'board': game.unpack_board(),
            'playing_as': playing_as,
            'current_player': game.current_player,
            'state': game.state,
            'turn': game.turn,
            'rule_set_id': game.rule_set.key().id() }

class HomePage(util.ExtendedHandler):
    def get(self):
        self.template('home.html')

def main():
    application = webapp.WSGIApplication([
        ('/', HomePage),
        ('/game/.*', GameService)
    ])
    wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
    main()
