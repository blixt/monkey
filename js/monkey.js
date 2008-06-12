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
            secure: false,
            url: sc._path + action,
            onComplete: function (result) {
                if (result) {
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
                } else {
                    if (this.attempts >= 3) {
                        alert('A request failed after repeated retries. Please reload the page.');
                    } else {
                        this.attempts++;
                        this.get.delay(500, this, params);
                    }
                }

                sc._running = false;
                if (sc._queue.length > 0) {
                    sc.call.apply(sc, sc._queue.shift());
                }
            }
        });
        req.attempts = 1;
        req.get(params);
    }
});

var MonkeyService = new Class({
    Extends: ServiceClient,

    initialize: function () {
        this.parent('/game/');
    },

    addCpuPlayer: function (gameId, onSuccess, onError) {
        this.call('add_cpu_player', { game: gameId }, onSuccess, onError);
    },

    changeNick: function (newNick, onSuccess, onError) {
        this.call('change_nickname', { nickname: newNick }, onSuccess, onError);
    },

    createGame: function (ruleSetId, onSuccess, onError) {
        this.call('create_game', { rule_set: ruleSetId }, onSuccess, onError);
    },

    gameStatus: function (gameId, turn, onSuccess, onError) {
        this.call('get_game_status', { game: gameId, turn: turn }, onSuccess, onError);
    },
    
    getRuleSets: function (onSuccess, onError) {
        this.call('get_rule_sets', {}, onSuccess, onError);
    },
    
    getPlayerInfo: function (onSuccess, onError) {
        this.call('get_player_info', {}, onSuccess, onError);
    },

    joinGame: function(gameId, onSuccess, onError) {
        this.call('join_game', { game: gameId }, onSuccess, onError);
    },
    
    leaveGame: function (gameId, onSuccess, onError) {
        this.call('leave_game', { game: gameId }, onSuccess, onError);
    },

    listGames: function (mode, onSuccess, onError) {
        var params = mode ? { mode: mode } : {};
        this.call('get_games', params, onSuccess, onError);
    },
    
    move: function (gameId, x, y, onSuccess, onError) {
        this.call('put_tile', { game: gameId, x: x, y: y }, onSuccess, onError);
    }
});

var MonkeyClient = new Class({
    initialize: function () {
        var mc = this;

        mc.game = null;
        mc.gameId = null;
        mc.service = new MonkeyService();

        var ruleSets;

        mc.html = {};
        $extend(mc.html, {
            game: new Element('div', {
                'class': 'game'
            }).adopt(
                new Element('p').adopt(
                    mc.html.joinOrLeave = new Element('button', {
                        text: 'Join'
                    }),
                    mc.html.addCpuPlayer = new Element('button', {
                        text: 'Add CPU player'
                    }),
                    new Element('button', {
                        events: { click: mc.setMode.bind(mc, MonkeyClient.Mode.lobby) },
                        text: 'To the lobby'
                    })
                ),
                mc.html.gameStatus = new Element('p'),
                mc.html.players = new Element('ol', { 'class': 'players' }),
                mc.html.ruleSetName = new Element('p', { 'class': 'rule-set-name' }),
                mc.html.ruleSetDescription = new Element('p', { 'class': 'rule-set-description' }),
                new Element('table').adopt(
                    mc.html.gameBoard = new Element('tbody')
                )
            ),

            main: new Element('div', { 'class': 'monkey' }).adopt(
                mc.html.player = new Element('p', { 'class': 'player', text: 'Please wait...' })
            ).inject('body'),

            lobby: new Element('div', {
                'class': 'lobby'
            }).adopt(
                new Element('p').adopt(
                    ruleSets = new Element('select'),
                    mc.html.createGame = new Element('button', {
                        events: {
                            click: function () {
                                this.disabled = true;
                                mc.createGame(parseInt(ruleSets.value));
                            }
                        },
                        text: 'Create game'
                    })
                ),
                new Element('ul').adopt(
                    new Element('li', { 'class': 'play' }).adopt(new Element('a', {
                        events: {
                            click: mc.setListMode.bind(mc, 'play')
                        },
                        href: '#play',
                        text: 'Play'
                    })),
                    new Element('li', { 'class': 'view' }).adopt(new Element('a', {
                        events: {
                            click: mc.setListMode.bind(mc, 'view')
                        },
                        href: '#view',
                        text: 'View'
                    })),
                    new Element('li', { 'class': 'past' }).adopt(new Element('a', {
                        events: {
                            click: mc.setListMode.bind(mc, 'past')
                        },
                        href: '#past',
                        text: 'Past'
                    }))
                ),
                new Element('table').adopt(
                    new Element('thead').adopt(
                        new Element('tr').adopt(
                            new Element('th', {
                                'class': 'action',
                                text: 'View/Play'
                            }),
                            new Element('th', {
                                'class': 'rule-set',
                                text: 'Rule set'
                            }),
                            new Element('th', {
                                'class': 'players',
                                text: 'Players'
                            })
                        )
                    ),
                    mc.html.gameList = new Element('tbody').adopt(new Element('tr').adopt(
                        new Element('td', {
                            'class': 'no-games',
                            colspan: 3,
                            text: 'Loading...'
                        })
                    ))
                )
            )
        });

        mc.service.getRuleSets(function (list) {
            mc.ruleSets = {};
            for (var i = 0; i < list.length; i++) {
                mc.ruleSets[list[i].id] = list[i];
                new Element('option', { text: list[i].name, value: list[i].id }).inject(ruleSets);
            }
            ruleSets.value = list[0].id;
        });

        mc.setMode(MonkeyClient.Mode.lobby, true);
        mc.setListMode('play');
        mc.refreshPlayer();
    },
    
    addCpuPlayer: function () {
        this.service.addCpuPlayer(this.gameId, this.refresh.bind(this));
    },
    
    createGame: function (ruleSetId) {
        this.service.createGame(ruleSetId, this.goToGame.bind(this));
    },
    
    goToGame: function (gameId, game, skipRefresh) {
        this.gameId = gameId;
        this.setMode(MonkeyClient.Mode.game, skipRefresh);
        
        if (game) this.handleStatus(game);
    },
    
    handleList_playerTd: function (index, game) {
        var mc = this;

        if (game.players[index]) {
            var turn = game.state == 'playing' && game.current_player == index + 1;
            return new Element('td', {
                'class': 'slot',
                text: game.players[index] + (turn ? ' ←' : '')
            });
        } else {
            return new Element('td', {
                'class': 'open slot'
            }).adopt(
                game.playing_as?
                new Element('span', {
                    text: 'Waiting for player to join...'
                }):
                new Element('a', {
                    events: { click: mc.joinGame.bind(mc, [game.id, game]) },
                    href: '#' + game.id,
                    text: 'Join game'
                })
            );
        }
    },
    
    handleList: function (games) {
        var mc = this;

        mc.html.gameList.empty();

        if (games.length == 0) {
            mc.html.gameList.adopt(new Element('tr').adopt(
                new Element('td', {
                    'class': 'no-games',
                    colspan: 3,
                    text: 'There are no games to show here.'
                })
            ));
        } else {
            for (var i = 0; i < games.length; i++) {
                var g = games[i], rs = mc.ruleSets[g.rule_set_id];
                var row, turn = (g.state == 'playing' && g.current_player == 1);

                var cls = g.state;
                if (cls == 'win' && g.playing_as && g.playing_as != g.current_player) {
                    cls = 'loss';
                }

                mc.html.gameList.adopt(new Element('tr', {
                    'class': cls
                }).adopt(
                    new Element('td', {
                        'class': 'action',
                        rowspan: rs.num_players
                    }).adopt(
                        new Element('button', {
                            events: {
                                click: mc.goToGame.bind(mc, [g.id, g])
                            },
                            text: g.state == 'playing' && g.playing_as > 0 ? 'Play' : 'View'
                        })
                    ),
                    new Element('td', {
                        'class': 'rule-set',
                        rowspan: rs.num_players
                    }).adopt(
                        new Element('span', { text: rs.name + ' — ' }),
                        new Element('small', {
                            text: rs.m + '×' + rs.n + ' board, ' + rs.k + ' in a row to win, place ' + rs.q +
                                  (rs.p == rs.q ? ' each turn.' : ' first turn, then ' + rs.p + ' following turns.')
                        })
                    ),
                    mc.handleList_playerTd(0, g)
                ));
                
                for (var j = 1; j < rs.num_players; j++) {
                    mc.html.gameList.adopt(new Element('tr', {
                        'class': cls
                    }).adopt(mc.handleList_playerTd(j, g)));
                }
            }
        }
        
        $clear(mc.timer);
        mc.timer = mc.refresh.delay(5000, mc);
    },
    
    handleStatus: function (game) {
        var mc = this;

        if (game) {
            var pa = game.playing_as;
            var cp = game.current_player;
            var rs = mc.ruleSets[game.rule_set_id];

            var status;
            switch (game.state) {
                case 'waiting':
                    status = 'This game needs more players before it can start.';
                    break;
                case 'playing':
                    var nick = game.players[cp - 1];
                    status = 'This game is currently being played. It\'s ' +
                             (pa == cp ? 'your' : nick + '\'' + (nick.substring(nick.length - 1).toLowerCase() == 's' ? '' : 's')) +
                             ' turn.';
                    break;
                case 'aborted':
                    status = 'This game has been abandoned by a player and cannot continue.';
                    break;
                case 'draw':
                    status = 'This game ended in a draw.';
                    break;
                case 'win':
                    status = 'This game has ended. ';
                    if (pa == cp)
                        status += 'You won!';
                    else
                        status += game.players[cp - 1] + ' won.';
                    break;
            }

            mc.html.game.set('class', 'game player-' + pa);
            mc.html.gameStatus.set('text', status);
            mc.html.ruleSetName.set('text', rs.name);
            mc.html.ruleSetDescription.set('text', rs.m + '×' + rs.n + ' board, ' + rs.k + ' in a row to win, place ' + rs.q +
                                                     (rs.p == rs.q ? ' each turn.' : ' first turn, then ' + rs.p + ' following turns.'));

            var jol = mc.html.joinOrLeave;
            jol.set('text', pa ? (game.state == 'waiting' ? 'Leave' : 'Abandon') : 'Join');
            if (game.state == 'waiting' || (game.state == 'playing' && pa)) {
                jol.disabled = false;
                jol.onclick = pa ? function () {
                    this.disabled = true;
                    $clear(mc.timer);
                    mc.leaveGame();
                } : function () {
                    this.disabled = true;
                    mc.joinGame(mc.gameId);
                };
            } else {
                jol.disabled = true;
            }
            
            var acp = mc.html.addCpuPlayer;
            if (game.state == 'waiting' && pa) {
                acp.disabled = false;
                acp.onclick = function () { this.disabled = true; mc.addCpuPlayer(); };
            } else {
                acp.disabled = true;
            }

            mc.html.players.empty();
            for (var i = 0; i < rs.num_players; i++) {
                var li;
                if (game.players[i])
                    li = new Element('li', {
                        text: game.players[i]
                    }).inject(mc.html.players);
                else
                    li = new Element('li', {
                        'class': 'open',
                        text: 'Open slot'
                    }).inject(mc.html.players);

                if (game.state == 'playing' && i + 1 == cp) {
                    li.set('class', 'current');
                }
            }

            if (game.board) {
                var width = game.board.length, height = game.board[0].length;
                if (!mc.html.cells) {
                    mc.html.cells = [];
                    mc.html.gameBoard.empty();

                    for (var y = 0; y < height; y++) {
                        var row = new Element('tr').inject(mc.html.gameBoard);
                        for (var x = 0; x < width; x++) {
                            if (!mc.html.cells[x]) mc.html.cells[x] = [];

                            var player = game.board[x][y];
                            mc.html.cells[x][y] = new Element('td', {
                                events: {
                                    click: mc.move.bind(mc, [x, y]),
                                    mouseenter: function () { this.addClass('hover'); },
                                    mouseleave: function () { this.removeClass('hover'); }
                                },
                                'class': player ? 'player-' + player : 'empty'
                            }).inject(row);
                        }
                    }
                } else {
                    for (var y = 0; y < height; y++) {
                        for (var x = 0; x < width; x++) {
                            var player = game.board[x][y];
                            mc.html.cells[x][y].set('class', player ? 'player-' + player : 'empty');
                        }
                    }
                }
            }

            mc.game = game;
            if (game.state == 'win' && game.board) mc.markWinTiles();
        }
        
        $clear(mc.timer);
        if (!mc.game) {
            mc.timer = mc.refresh.delay(2500, mc);
        } else if (mc.game.state == 'waiting') {
            mc.timer = mc.refresh.delay(5000, mc);
        } else if (mc.game.state == 'playing') {
            mc.timer = mc.refresh.delay(1000, mc);
        }
    },
    
    handlePlayer: function (player) {
        var mc = this, s = mc.service;

        mc.player = player;

        mc.html.player.empty();

        var a = new Element('a', {
            events: {
                click: function () {
                    var nick = prompt('New nickname', mc.player.nickname);
                    if (nick) s.changeNick(nick, mc.handlePlayer.bind(mc));
                }
            },
            href: '#',
            text: player.nickname
        }).inject(mc.html.player);

        if (player.nickname == 'Anonymous') {
            var flasher = function (i) {
                a.set('text', 'Click here to change nickname!');
                a.toggleClass('alert');
                
                if (i-- > 0) {
                    flasher.delay(500, null, i);
                } else {
                    a.set('text', mc.player.nickname);
                }
            };

            flasher(7);
        }

        mc.html.player.appendText(' — ');

        new Element('a', {
            href: player.log_url,
            text: player.anonymous ? 'Log in' : 'Log out'
        }).inject(mc.html.player);
    },
    
    joinGame: function (gameId, game) {
        var mc = this;

        if (game) mc.goToGame(gameId, game, true);
        mc.service.joinGame(gameId, function (game) {
            mc.goToGame(gameId, game);
        });
    },
    
    leaveGame: function () {
        var q = 'Are you sure you want to abandon this game?';
        if (this.game.state == 'playing' && !confirm(q)) return;
        this.service.leaveGame(this.gameId, this.setMode.bind(this, MonkeyClient.Mode.lobby));
    },
    
    markWinTiles: function () {
        // TODO: Needs optimization
        var self = this.ruleSets[this.game.rule_set_id];
        var board = this.game.board;
        var player = this.game.current_player;

        for (var y = 0; y < self.n; y++) {
            for (var x = 0; x < self.m; x++) {
                var c = this.html.cells[x][y];
                
                if (c.hasClass('w')) continue;
                c.addClass('l');

                var ca = 0, cb = 0, cc = 0, cd = 0;
                for (var i = -self.k + 1; i < self.k; i++) {
                    var tx = x + i, txi = x - i, ty = y + i;
                    // Test horizontal -
                    if (tx >= 0 && tx < self.m)
                        ca += board[tx][y] == player ? 1 : -ca;
                    // Test vertical |
                    if (ty >= 0 && ty < self.n)
                        cb += board[x][ty] == player ? 1 : -cb;
                    // Test diagonal \
                    if (tx >= 0 && ty >= 0 && tx < self.m && ty < self.n)
                        cc += board[tx][ty] == player? 1 : -cc;
                    // Test diagonal /
                    if (txi >= 0 && ty >= 0 && txi < self.m && ty < self.n)
                        cd += board[txi][ty] == player ? 1 : -cd;

                    if (!self.exact && (ca == self.k || cb == self.k || cc == self.k || cd == self.k)) {
                        c.removeClass('l');
                        c.addClass('w');
                        break;
                    }
                }
            }
        }
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
                this.service.listGames(this.listMode, this.handleList.bind(this));
                break;
            case MonkeyClient.Mode.game:
                var t = this.game && this.game.state == 'playing' ? this.game.turn : null;
                this.service.gameStatus(this.gameId, t, this.handleStatus.bind(this));
                break;
        }
    },
    
    refreshPlayer: function () {
        this.service.getPlayerInfo(this.handlePlayer.bind(this));
    },
    
    setListMode: function (newMode) {
        this.html.gameList.empty().adopt(
            new Element('tr').adopt(
                new Element('td', {
                    'class': 'no-games',
                    colspan: 3,
                    text: 'Loading...'
                })
            )
        );

        this.html.lobby.set('class', 'lobby ' + newMode);
        this.listMode = newMode;
        this.refresh();
    },
    
    setMode: function (newMode, skipRefresh) {
        switch (this.mode) {
            case MonkeyClient.Mode.lobby:
                this.html.lobby.dispose();
                break;
            case MonkeyClient.Mode.game:
                this.html.game.dispose();
                break;
        }
        
        this.mode = newMode;
        
        switch (this.mode) {
            case MonkeyClient.Mode.lobby:
                this.game = null;
                this.gameId = null;

                this.html.createGame.disabled = false;
                this.html.main.set('class', 'monkey in-lobby');
                this.html.lobby.inject(this.html.main);

                break;
            case MonkeyClient.Mode.game:
                this.html.cells = null;

                this.html.gameBoard.empty();
                this.html.players.empty();

                this.html.gameStatus.set('text', 'Loading game status...');
                this.html.joinOrLeave.disabled = true;
                this.html.joinOrLeave.set('text', 'Join');

                this.html.main.set('class', 'monkey in-game');
                this.html.game.inject(this.html.main);

                break;
        }
        
        if (!skipRefresh) this.refresh();
    }
});

MonkeyClient.Mode = {
    lobby: 1,
    game: 2
};
