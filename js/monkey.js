/**
 * Copyright (c) 2008 Andreas Blixt <andreas@blixt.org>
 * Project homepage: <http://code.google.com/p/monkey-web/>
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

var ServiceClient = new Class({
    initialize: function (path) {
        this._path = path;
        this._queue = [];
        this._running = false;
    },
    
    call: function (action, args, onSuccess, onError) {
        if (this._running == true) {
            this._queue.push([action, args, onSuccess]);
            return;
        }

        this._running = true;

        var params = { _time: +new Date() };
        $each(args, function (v, p) {
            params[p] = JSON.encode(v);
        });

        var sc = this;
        var req = new Request.JSON({
            url: sc._path + action,
            onComplete: function (result) {
                switch (result.status) {
                    case 'error':
                        if (onError)
                            onError(result.response);
                        else
                            alert(result.response.type + ': ' + result.response.message);
                        break;
                    case 'list':
                        break;
                    case 'success':
                        if (onSuccess) onSuccess(result.response);
                        break;
                    default:
                        alert('Unknown status: ' + result.status);
                        break;
                }

                sc._running = false;
                if (sc._queue.length > 0) {
                    sc.call.apply(sc, sc._queue.shift());
                }
            }
        }).get(params);
    }
});

var MonkeyService = new Class({
    Extends: ServiceClient,

    initialize: function () {
        this.parent('/game/');
    },

    createGame: function (ruleSetId, onSuccess, onError) {
        this.call('create', { rule_set_id: ruleSetId }, onSuccess, onError);
    },

    gameStatus: function (gameId, onSuccess, onError) {
        this.call('status', { game_id: gameId }, onSuccess, onError);
    },

    joinGame: function(gameId, onSuccess, onError) {
        this.call('join', { 'game_id': gameId }, onSuccess, onError);
    },

    listGames: function (onSuccess, onError) {
        this.call('list', { states: ['waiting', 'playing'] }, onSuccess, onError);
    },
    
    move: function (gameId, x, y, onSuccess, onError) {
        this.call('move', { 'game_id': gameId, 'x': x, 'y': y }, onSuccess, onError);
    }
});

var MonkeyClient = new Class({
    initialize: function () {
        var mc = this;

        mc.gameId = null;
        mc.service = new MonkeyService();

        mc.html = {};
        $extend(mc.html, {
            game: new Element('div', {
                'class': 'game'
            }).adopt(
                new Element('p').adopt(
                    new Element('a', {
                        events: {
                            click: function () {
                                mc.setMode(MonkeyClient.Mode.lobby);
                            }
                        },
                        href: '#lobby',
                        text: 'Back to the lobby (this will not end the game)'
                    })
                ),
                mc.html.players = new Element('ol', { 'class': 'players' }),
                new Element('table').adopt(
                    mc.html.gameBoard = new Element('tbody')
                )
            ),

            main: new Element('div', { 'class': 'monkey' }).inject('body'),

            lobby: new Element('div', {
                'class': 'lobby'
            }).adopt(
                new Element('table').adopt(
                    new Element('thead').adopt(
                        new Element('tr').adopt(
                            new Element('th', {
                                'class': 'rule-set',
                                text: 'Rule set'
                            }),
                            new Element('th', {
                                'class': 'players',
                                text: 'Players'
                            }),
                            new Element('th', {
                                'class': 'action',
                                text: 'View/Play'
                            })
                        )
                    ),
                    mc.html.gameList = new Element('tbody')
                )
            )
        });

        mc.setMode(MonkeyClient.Mode.lobby);
    },
    
    goToGame: function (gameId) {
        this.gameId = gameId;
        this.setMode(MonkeyClient.Mode.game);
    },
    
    handleList: function (games) {
        this.html.gameList.empty();

        if (games.length == 0) {
            this.html.gameList.adopt(new Element('tr').adopt(
                new Element('td', {
                    'class': 'no-games',
                    colspan: 3,
                    text: 'There are currently no open games.'
                })
            ));
        } else {
            for (var i = 0; i < games.length; i++) {
                var g = games[i], row;
                this.html.gameList.adopt(new Element('tr').adopt(
                    new Element('td', {
                        'class': 'rule-set',
                        rowspan: g.rule_set.num_players,
                        text: g.rule_set.name
                    }),
                    new Element('td', {
                        'class': 'slot',
                        text: g.players[0]
                    }),
                    new Element('td', {
                        'class': 'action',
                        rowspan: g.rule_set.num_players
                    }).adopt(
                        new Element('a', {
                            events: {
                                click: this.goToGame.bind(this, g.id)
                            },
                            href: '#' + g.id,
                            text: g.playable ? 'Play' : 'View'
                        })
                    )
                ));
                
                for (var j = 1; j < g.rule_set.num_players; j++) {
                    var open = !g.players[j];
                    this.html.gameList.adopt(new Element('tr').adopt(
                        open?
                        new Element('td', {
                            'class': 'open slot'
                        }).adopt(
                            new Element('a', {
                                events: {
                                    click: this.joinGame.bind(this, g.id)
                                },
                                href: '#' + g.id,
                                text: 'Open spot'
                            })
                        ):
                        new Element('td', {
                            'class': 'slot',
                            text: g.players[j]
                        })
                    ));
                }
            }
        }
        
        $clear(this.timer);
        this.timer = this.refresh.delay(5000, this);
    },
    
    handleStatus: function (game) {
        this.html.gameBoard.empty();

        var width = game.board.length, height = game.board[0].length;
        for (var y = 0; y < height; y++) {
            var row = new Element('tr').inject(this.html.gameBoard);

            for (var x = 0; x < width; x++) {
                var player = game.board[x][y];
                new Element('td', {
                    events: {
                        click: this.move.bind(this, [x, y]),
                        mouseenter: function () { this.addClass('hover'); },
                        mouseleave: function () { this.removeClass('hover'); }
                    },
                    'class': player ? 'player-' + player : 'empty'
                }).adopt(
                    new Element('span', { text: player })
                ).inject(row);
            }
        }
        
        $clear(this.timer);
        this.timer = this.refresh.delay(1000, this);
    },
    
    joinGame: function (gameId) {
        var mc = this;
        mc.service.joinGame(gameId, function (game) {
            mc.goToGame(gameId);
            mc.handleStatus(game);
        });
    },
    
    move: function (x, y) {
        if (this.mode == MonkeyClient.Mode.game) {
            this.service.move(this.gameId, x, y, this.handleStatus.bind(this));
        }
    },
    
    refresh: function () {
        $clear(this.timer);

        switch (this.mode) {
            case MonkeyClient.Mode.lobby:
                this.service.listGames(this.handleList.bind(this));
                break;
            case MonkeyClient.Mode.game:
                this.service.gameStatus(this.gameId, this.handleStatus.bind(this));
                break;
        }
    },
    
    setMode: function (newMode) {
        if (newMode == this.mode) return;
        
        switch (this.mode) {
            case MonkeyClient.Mode.lobby:
                this.html.lobby.dispose();
                break;
            case MonkeyClient.Mode.game:
                this.gameId = null;
                this.html.game.dispose();
                break;
        }
        
        this.mode = newMode;
        
        switch (this.mode) {
            case MonkeyClient.Mode.lobby:
                this.html.main.set('class', 'monkey in-lobby');
                this.html.lobby.inject(this.html.main);

                break;
            case MonkeyClient.Mode.game:
                this.html.main.set('class', 'monkey in-game');
                this.html.game.inject(this.html.main);

                break;
        }
        
        this.refresh();
    }
});

MonkeyClient.Mode = {
    lobby: 1,
    game: 2
};
