var Cube = (function () {
	'use strict';
	var tournaments = [],
		activeTournament,
		updateUI = function () {
			var i = this.UI.length;
			while (i--) {
				this.UI[i].refresh(this);
			}
		},
		removeUI = function (controls) {
			var i = this.UI.length;
			while (i--) {
				this.UI[i].remove(controls || this);
			}
		},
		Tournament = function () {
			this.UI = [];
			this.activeEvent = undefined;
			this.name = '';
			this.events = [];
			this.players = [];
			tournaments.push(this);
			activeTournament = this;
		},
		Payout = function () {
		},
		Player = function (tournament, nick, name, skill, location) {
			this.UI = [];
			this.tournament = tournament;
			this.bye = tournament === null;
			this.nick = typeof nick === 'undefined' ? '' : nick;
			this.name = typeof name === 'undefined' ? '' : name;
			this.skill = typeof skill === 'undefined' ? 5 : skill;
			this.location = typeof location === 'undefined' ? '' : location;
		},
		BracketNode = function (type, col, row) {
			this.nodesIn = [];
			this.nodesOut = [];
			this.order = [];
			this.type = type;
			this.col = col;
			this.row = row;
			this.resolved = false;
			this.names = [];
		},
		PlayerNode = function (player, nodeOut, bye) {
			this.player = player;
			if (nodeOut !== true) {
				this.nodesOut = [nodeOut];
			} else {
				this.nodesOut = [];
			}
			this.nodesIn = [];
			this.names = [];
			this.order = this.nodesOut;
			this.type = nodeOut !== true ? BracketNode.PLAYER_NODE : BracketNode.BYE_NODE;
			this.resolved = true;
		},
		bye = new Player(null, 'Bye'),
		Bracket = function (event, entrants, type, seeding, alreadySeeded) {
			this.event = event;
			this.UI = [];
			this.size = Math.findNextPowerOfTwo(entrants.length);
			this.type = type;
			this.seeding = seeding;
			this.entrants = entrants;
			this.rootNodes = [];
			this.playerNodes = [];
			this.nodes = [];
			this.progress = [];
			(function (size, type, seeding, rootNodes, nodes, playerNodes) {
				var randomShuffle = function (a) {
						var b = a.slice(),
							c = [],
							i = b.length;
						while (i) {
							c.push(b.splice(Math.floor(Math.random() * b.length), 1)[0]);
							i--;
						}
						return c;
					},
					byePlacements = { //@temporary until we write an algorithm for it
						4: '00',
						8: '000203',
						16: '00040602030705',
						32: '000812040614100203111507051309',
						64: '00162408122820040622301410261802031927111531230705212913092517'
					},
					byeEntrant = {player: bye, paid: 0, bye: true},
					index,
					byeIndexes = [],
					toLetters = function (n) {
						return (n > 25 ? String.fromCharCode(Math.floor(n / 25) + 64) : '') + String.fromCharCode(n % 26 + 65);
					},
					i;
				if (alreadySeeded !== true) {
					switch (seeding) {
					case Bracket.RANDOM:
						this.entrants = randomShuffle(this.entrants);
						entrants = this.entrants;
						break;
					}
				}
				i = 0;
				while (entrants.length + i < size) {
					if (byePlacements[size]) {
						index = parseInt(byePlacements[size].substr(i * 2, 2), 10);
					} else {
						index = Math.floor(Math.random() * size / 2);
					}
					byeIndexes.push(index);
					i++;
				}
				byeIndexes.sort(function (a, b) {return a - b; }).forEach(function (byeIndex) {
					entrants.splice(byeIndex * 2 + 1, 0, byeEntrant);
				});
				if (type === Bracket.ROUND_ROBIN) {
					this.pools = [];
				}
				if (type === Bracket.SINGLE_ELIM || type === Bracket.DOUBLE_ELIM) { (function () {
					var i,
						index,
						lastLevel,
						thisLevel,
						level = 0,
						node,
						winnerNode,
						winnersNodes = [],
						matchType,
						playerNode,
						grandFinals,
						letter = 0,
						links = { //@temporary solution lol
							4: '00',
							8: '010002',
							16: '02030001040506',
							32: '02030001060704050A0B08090C0D0E',
							64: '04050607000102030C0D0E0F08090A0B151417161110131219181B1A1D1C1E'
						},
						l = Math.floor(size / 2);
					for (i = 0; i < l; i++) {
						node = new BracketNode(BracketNode.WINNERS, level, i);
						if (typeof entrants[i * 2] === 'undefined') {
							entrants[i * 2] = byeEntrant;
						}
						playerNode = new PlayerNode(entrants[i * 2].player, node);
						playerNodes.push(playerNode);
						node.nodesIn.push(playerNode);
						if (typeof entrants[i * 2 + 1] === 'undefined') {
							entrants[i * 2 + 1] = byeEntrant;
						}
						playerNode = new PlayerNode(entrants[i * 2 + 1].player, node);
						playerNodes.push(playerNode);
						node.nodesIn.push(playerNode);
						node.type = BracketNode.ROOT;
						rootNodes.push(node);
						nodes.push(node);
					}
					level++;
					lastLevel = rootNodes;
					while (lastLevel.length > 1) {
						thisLevel = [];
						l = Math.floor(lastLevel.length / 2);
						for (i = 0; i < l; i++) {
							switch (lastLevel.length) {
							case 8:
								matchType = BracketNode.WQF;
								break;
							case 4:
								matchType = BracketNode.WSF;
								break;
							case 2:
								matchType = BracketNode.WF;
								break;
							default:
								matchType = BracketNode.WINNERS;
							}
							node = new BracketNode(matchType, level, i);
							node.letter = toLetters(letter++);
							thisLevel.push(node);
							nodes.push(node);
							winnersNodes.push(node);
							node.nodesIn.push(lastLevel[i * 2]);
							node.nodesIn.push(lastLevel[i * 2 + 1]);
							lastLevel[i * 2].nodesOut.push(node);
							lastLevel[i * 2 + 1].nodesOut.push(node);
						}
						lastLevel = thisLevel;
						level++;
					}
					grandFinals = new BracketNode(BracketNode.GF, level, 0);
					grandFinals.set2 = -1;
					grandFinals.nodesIn[0] = node;
					node.nodesOut[0] = grandFinals;

					if (type === Bracket.DOUBLE_ELIM) {
						lastLevel = rootNodes;
						level = -1;
						index = 0;
						while (lastLevel.length > 1) {
							thisLevel = [];
							switch (lastLevel.length) {
							case 4:
								matchType = BracketNode.LQF;
								break;
							case 2:
								matchType = BracketNode.LSF;
								break;
							case 1:
								matchType = BracketNode.LF;
								break;
							default:
								matchType = BracketNode.LOSERS;
							}
							for (i = 0, l = lastLevel.length; i < l; i += 2) {
								node = new BracketNode(matchType, level, i / 2);
								node.nodesIn.push(lastLevel[i], lastLevel[i + 1]);
								lastLevel[i].nodesOut.push(node);
								lastLevel[i + 1].nodesOut.push(node);
								nodes.push(node);
								thisLevel.push(node);
							}
							lastLevel = thisLevel;
							thisLevel = [];
							level--;
							for (i = 0, l = lastLevel.length; i < l; i++) {
								winnerNode = winnersNodes[parseInt(links[size].substr(index * 2, 2), 16)];
								index++;
								node = new BracketNode(matchType, level, i);
								node.letter = winnerNode.letter;
								node.nodesIn.push(lastLevel[i], winnerNode);
								lastLevel[i].nodesOut.push(node);
								if (typeof winnerNode !== 'undefined') {
									winnerNode.nodesOut.push(node);
								}
								nodes.push(node);
								thisLevel.push(node);
							}
							level--;
							lastLevel = thisLevel;
						}
						grandFinals.nodesIn[1] = node;
						node.nodesOut[0] = grandFinals;
						nodes.push(grandFinals);
					}
				}()); }
			}.call(this, this.size, this.type, this.seeding, this.rootNodes, this.nodes, this.playerNodes));
		},
		Pool = function (bracket, entrants, progress) {
			this.bracket = bracket;
			this.entrants = entrants;
			this.progress = progress;
		},
		Event = function (tournament) {
			this.UI = [];
			this.tournament = tournament;
			this.name = '';
			this.game = '';
			this.type = Event.SINGLES;
			this.date = new Date();
			this.inProgress = false;
			this.manageStations = false;
			this.separateByLocation = false;
			this.winLossNumber = false;
			this.bestOf = 3;
			this.champsBestOf = 5;
			this.entryFee = 0;
			this.houseCutType = Event.PERCENTAGE;
			this.houseCut = 0;
			this.potDistribution = new Payout(Payout.DEFAULT);
			this.seedingType = Bracket.RANDOM;
			this.entrants = [];
			this.bracket = undefined;
			this.activeView = false;
		},
		classList = function (element) {
			var classes = [element.className.split(' ')];
			return {
				add: function (CSSClass) {
					classes.push(CSSClass);
					element.className = classes.join(' ');
				}
			};
		},
		Files = {
			loadFromJSON: function (JSONTournament) {
				var tournament = new Tournament();
				tournament.players = JSONTournament.players.map(function (JSONPlayer) {
					if ((JSONPlayer + '') === JSONPlayer) {
						return new Player(tournament, JSONPlayer);
					} else {
						return new Player(tournament, JSONPlayer.nick || '', JSONPlayer.name || '', JSONPlayer.skill || 5, JSONPlayer.location || '');
					}
				});
				tournament.events = JSONTournament.events.map(function (JSONEvent) {
					var event = new Event(tournament),
						entrants,
						i;
					event.name = JSONEvent.name;
					event.type = JSONEvent.type;
					event.entrants = tournament.players.map(function (player) {
							return {player: player, paid: 0};
						});
					if (typeof JSONEvent.bracket !== 'undefined') {
						if (JSONEvent.bracket.type === Bracket.ROUND_ROBIN) {
							entrants = [];
							JSONEvent.bracket.entrants.forEach(function (pool) {
								entrants.concat(pool);
							});
							event.bracket = new Bracket(event, entrants.map(function (entrant) {
									return event.entrants[entrant];
								}), JSONEvent.bracket.type, JSONEvent.bracket.seeding, true);
						} else {
							event.bracket = new Bracket(event, JSONEvent.bracket.entrants.map(function (entrant) {
									return event.entrants[entrant];
								}), JSONEvent.bracket.type, JSONEvent.bracket.seeding, true);
						}
						if (event.bracket.type === Bracket.DOUBLE_ELIM || event.bracket.type === Bracket.SINGLE_ELIM) {
							event.bracket.progress = JSONEvent.bracket.progress.map(function (result, i) {
								if (result !== -1) {
									var node = event.bracket.nodes[i];
									if (node) {
										node.resolved = true;
										node.order = result === 0 ? [node.nodesIn[0], node.nodesIn[1]] : [node.nodesIn[1], node.nodesIn[0]];
										return node.order;
									} else {
										return undefined;
									}
								}
							});
							if (event.bracket.type === Bracket.DOUBLE_ELIM) {
								event.bracket.nodes[event.bracket.nodes.length - 1].set2 = JSONEvent.bracket.progress[JSONEvent.bracket.progress.length - 1];
							}
						} else if (event.bracket.type === Bracket.ROUND_ROBIN) {
							event.bracket.size = JSONEvent.bracket.entrants.length;
							for (i = 0; i < event.bracket.size; i++) {
								event.bracket.pools.push(new Pool(event.bracket,
									JSONEvent.bracket.entrants[i].map(function (entrant) {
										return event.entrants[i];
									}),
									JSONEvent.bracket.progress[i]
								));
							}
							event.bracket.progress = JSONEvent.bracket.progress;
						}
					}
					return event;
				});
				tournament.activeEvent = tournament.events[JSONTournament.activeEvent];
				return tournament;
			}
		},
		UI = {
			templates: {
				bracket: function (data) {
					var bracket = data,
						container = document.createElement('div'),
						bracketCanvas = document.createElement('canvas'),
						overlayCanvas = document.createElement('canvas'),
						canvases = document.createElement('div'),
						bracketDiv = document.createElement('div'),
						viewImage = document.createElement('input'),
						ctx = bracketCanvas.getContext('2d'),
						overctx = overlayCanvas.getContext('2d'),
						nodes = bracket.nodes,
						node,
						i,
						dragging = false,
						dragX = 0,
						dragY = 0,
						hGap = 100,
						vGap = 30,
						cols = Math.floor(Math.log(bracket.size) / Math.LN2),
						mostLeft = (bracket.type === Bracket.DOUBLE_ELIM ? cols * hGap * 2 - hGap * 2 : 0),
						panX = mostLeft,
						panY = 0,
						completed = false,
						highlighted,
						dragFrom = null,
						dragTo = null,
						bracketLog = [],
						width = (cols * hGap) + panX + (bracket.type === Bracket.DOUBLE_ELIM ? hGap : 0),
						height = Math.floor((bracket.size - 1) * vGap) + panY + vGap,
						connector,
						outDated = false,
						contextMenu,
						overlayUndraws = [],
						connect = function (nodeOut) {
							if (this.type % 2 === 1 && nodeOut.type % 2 === 1) {
								ctx.strokeStyle = 'rgb(128, 128, 128)';
								ctx.beginPath();
								ctx.moveTo(this.x + hGap, this.y + vGap / 2);
								ctx.lineTo(nodeOut.x, nodeOut.y + vGap / 2);
								ctx.stroke();
							} else if ((this.type % 2 === 0 && nodeOut.type % 2 === 0) ||
									(this.type === BracketNode.ROOT || nodeOut.type === BracketNode.ROOT)) {
								ctx.strokeStyle = 'rgb(128, 128, 128)';
								ctx.beginPath();
								ctx.moveTo(nodeOut.x + hGap, nodeOut.y + vGap / 2);
								ctx.lineTo(this.x, this.y + vGap / 2);
								ctx.stroke();
							} else if ((this.type + nodeOut.type) % 2 === 1) {
								if (this.letter && nodeOut.letter) {
									ctx.fillStyle = 'white';
									ctx.textAlign = 'left';
									ctx.fillText(this.letter, this.x + hGap + 4, this.y + vGap / 2 + 4);
									ctx.fillText(nodeOut.letter, nodeOut.x + hGap + 4, nodeOut.y + vGap / 2 + 4);
									ctx.textAlign = 'center';
								}
							} else {
								//console.log('err');
							}
						},
						updateNames = function () {
							var repeat = true,
								updateName = function (node, nodeOut, name, setBye) {
									if (setBye && nodeOut && !nodeOut.resolved && nodeOut.isReady()) {
										nodeOut.setLoser(node);
										nodeOut.resolved = true;
										nodeOut.bye = true;
										return true;
									}
									if (nodeOut && nodeOut.resolved) {
										nodeOut.names[nodeOut.order.indexOf(node)] = name;
										return updateName(nodeOut, nodeOut.nodesOut[nodeOut.order.indexOf(node)], name, setBye);
									}
								},
								startRecursion = function (node) {
									node.names[0] = node.player.nick;
									if (!repeat) {
										repeat = updateName(node, node.nodesOut[0], node.player.nick, node.player === bye);
									}
								};
							while (repeat) {
								repeat = false;
								bracket.playerNodes.forEach(startRecursion, bracket);
							}
						},
						refresh = function (removeDullness) {
							var i = nodes.length,
								name,
								textHeight = 10,
								textWidth,
								scaleBy,
								smallestScale = 0.66,
								breakingPoint,
								undef = 'undefined';
							if (completed) {
								removeDullness = true;
							}
							ctx.save();
							ctx.fillStyle = 'black';
							ctx.fillRect(0, 0, width, height);
							ctx.lineWidth = 2;
							ctx.fillStyle = 'rgb(127, 127, 127)';
							ctx.font = '16pt serif';
							ctx.textAlign = bracket.type === Bracket.SINGLE_ELIM ? 'right' : 'left';
							ctx.fillText(bracket.event.name, bracket.type === Bracket.SINGLE_ELIM ? width - 4 : 4, 18);
							ctx.textAlign = 'center';
							ctx.translate(panX, panY);
							ctx.font = textHeight + 'pt sans-serif';
							while (i--) {
								node = nodes[i];
								if (node.resolved) {
									ctx.fillStyle = 'rgb(32, 32, 32)';
									ctx.fillRect(node.x, node.y - vGap / 2 + vGap * node.nodesIn.indexOf(node.order[0]), hGap, vGap);
								}
								switch (node.type) {
								case BracketNode.ROOT:
									ctx.strokeStyle = 'white';
									break;
								case BracketNode.WINNERS:
									ctx.strokeStyle = 'white';
									break;
								case BracketNode.WQF:
									ctx.strokeStyle = 'rgb(127, 127, 255)';
									break;
								case BracketNode.WSF:
									ctx.strokeStyle = 'rgb(127, 255, 255)';
									break;
								case BracketNode.WF:
									if (node.resolved && bracket.type === Bracket.SINGLE_ELIM) {
										ctx.fillStyle = 'rgba(255, 255, 0, 0.5)';
										ctx.fillRect(node.x, node.y - vGap / 2 + vGap * node.nodesIn.indexOf(node.order[0]), hGap, vGap);
									}
									ctx.strokeStyle = bracket.type === Bracket.SINGLE_ELIM ? 'rgb(255, 255, 127)' : 'rgb(127, 255, 127)';
									break;
								case BracketNode.GF:
									if (node.set2 !== -1) {
										ctx.fillStyle = 'rgba(255, 255, 0, 0.5)';
										ctx.fillRect(node.x, node.y - vGap / 2 + vGap * node.nodesIn.indexOf(node.order[0]), hGap / 2, vGap);
										ctx.fillRect(node.x + hGap / 2, node.y - vGap / 2 + vGap * node.set2, hGap / 2, vGap);
									} else if (node.resolved) {
										ctx.fillStyle = 'rgba(255, 255, 0, 0.5)';
										ctx.fillRect(node.x, node.y - vGap / 2 + vGap * node.nodesIn.indexOf(node.order[0]), hGap, vGap);
									}
									ctx.strokeStyle = 'rgb(255, 255, 127)';
									break;
								default:
									ctx.strokeStyle = 'rgb(' + Math.floor(127 + -node.col / cols * 128) + ',' + Math.floor(-node.col / (cols + 2) * 200) + ',' + Math.floor(-node.col / (cols * 2) * 200) + ')';
								}
								ctx.beginPath();
								ctx.moveTo(node.x, node.y + vGap / 2);
								ctx.lineTo(node.x + hGap, node.y + vGap / 2);
								ctx.stroke();
								ctx.fillStyle = node.order[0] === node.nodesIn[0] && !node.nodesIn[0].bye ? 'white' : 'rgb(200,200,200)';
								if (node.nodesIn[0].resolved === true) {
									name = node.nodesIn[0].names[node.nodesIn[0].nodesOut.indexOf(node)];
									if (typeof name !== undef) {
										ctx.save();
										ctx.translate(node.x, node.y - 4);
										textWidth = ctx.measureText(name).width;
										if (textWidth <= hGap) {
											ctx.fillText(name, hGap / 2, vGap * 0.5);
										} else {
											scaleBy = hGap / textWidth;
											if (scaleBy > smallestScale) {
												ctx.scale(scaleBy, scaleBy);
												ctx.fillText(name, hGap * 0.5 / scaleBy, vGap * 0.5 / scaleBy);
											} else {
												if (textWidth > hGap / smallestScale) {
													while (ctx.measureText(name + '..').width > hGap / smallestScale) {
														name = name.substr(0, name.length - 1);
													}
													name = name.trimRight() + '..';
												}
												ctx.scale(smallestScale, smallestScale);
												ctx.fillText(name, hGap / 2 / smallestScale, vGap * 0.5 / smallestScale);
											}
										}
										ctx.restore();
									}
								}
								ctx.fillStyle = node.order[0] === node.nodesIn[1] && !node.nodesIn[1].bye ? 'white' : 'rgb(200,200,200)';
								if (node.nodesIn[1].resolved === true) {
									name = node.nodesIn[1].names[node.nodesIn[1].nodesOut.indexOf(node)];
									ctx.save();
									ctx.translate(node.x, node.y + textHeight + 4);
									textWidth = ctx.measureText(name).width;
									if (textWidth <= hGap) {
										ctx.fillText(name, hGap / 2, vGap * 0.5);
									} else {
										scaleBy = hGap / textWidth;
										if (scaleBy > smallestScale) {
											ctx.scale(scaleBy, scaleBy);
											ctx.fillText(name, hGap * 0.5 / scaleBy, vGap * 0.5);
										} else {
											if (textWidth > hGap / smallestScale) {
												while (ctx.measureText(name + '..').width > hGap / smallestScale) {
													name = name.substr(0, name.length - 1);
												}
												name = name.trimRight() + '..';
											}
											ctx.scale(smallestScale, smallestScale);
											ctx.fillText(name, hGap / 2 / smallestScale, vGap * 0.5);
										}
									}
									ctx.restore();
								}
								node.nodesOut.forEach(connect, node);
							}
							ctx.restore();
						},
						refreshOverlay = function (highlight, dragFrom, dragTo) {
							var connector,
								undraw;
							overctx.save();
							overctx.lineWidth = 1;
							overctx.translate(panX, panY);
							while (overlayUndraws.length > 0) {
								undraw = overlayUndraws.splice(0, 1)[0];
								overctx.clearRect(undraw[0], undraw[1], undraw[2], undraw[3]);
							}
							if (highlight) {
								if (!highlight.isReady()) {
									overctx.strokeStyle = 'rgb(64, 64, 64)';
								} else {
									overctx.strokeStyle = 'white';
								}
								overctx.strokeRect(highlight.x - 0.5, highlight.y - vGap / 2 - 0.5, hGap + 1, vGap * 2 + 1);
								overlayUndraws.push([highlight.x - 1, highlight.y - vGap / 2 - 1, hGap + 2, vGap * 2 + 2]);
								if (typeof highlight.letter !== 'undefined' && bracket.type === Bracket.DOUBLE_ELIM) {
									if (highlight.type % 2 === 1) {
										connector = [highlight.nodesOut[1].x + hGap, highlight.nodesOut[1].y + vGap / 2,
											highlight.x + hGap, highlight.y + vGap / 2];
									} else {
										connector = [highlight.nodesIn[1].x + hGap, highlight.nodesIn[1].y + vGap / 2,
											highlight.x + hGap, highlight.y + vGap / 2];
									}
									if (typeof connector !== 'undefined') {
										overctx.strokeStyle = 'rgb(64, 255, 64)';
										overctx.beginPath();
										overctx.moveTo(connector[0], connector[1]);
										overctx.lineTo(connector[2], connector[3]);
										overctx.stroke();
										overlayUndraws.push([
											Math.min(connector[0], connector[2]),
											Math.min(connector[1], connector[3]),
											Math.max(connector[0], connector[2]) - Math.min(connector[0], connector[2]),
											Math.max(connector[1], connector[3]) - Math.min(connector[1], connector[3])]);
									}
								}
							}
							overctx.restore();
						},
						controls = {
							refresh: function () {
								updateNames();
								refresh();
							},
							remove: function (bracket) {
								if (bracket instanceof Bracket) {
									bracket.entrants.forEach(function (entrant) {
										entrant.player.UI.splice(entrant.player.UI.indexOf(controls), 1);
									});
									container.parentNode.removeChild(container);
								} else if (bracket instanceof Player) {
									updateNames();
									refresh();
								}
							}
						},
						findNode = function (e) {
							var i = nodes.length,
								col,
								highlight,
								offsetX = e.offsetX,
								offsetY = e.offsetY;
							if (typeof offsetX === 'undefined') {
								offsetX = e.layerX;
								e.offsetX = offsetX;
								offsetY = e.layerY;
								e.offsetY = offsetY;
							}
							offsetX -= panX;
							offsetY -= panY;
							col = Math.floor(offsetX / hGap);
							while (i--) {
								if (nodes[i].col === col && offsetY > nodes[i].y - vGap * 0.5 && offsetY < nodes[i].y + vGap * 1.5) {
									return nodes[i];
								}
							}
							return null;
						},
						topset = 0;

					bracketCanvas.width = width;
					bracketCanvas.height = height;
					bracketCanvas.style.width = width + 'px';
					bracketCanvas.style.height = height + 'px';
					bracketCanvas.style.userSelect = 'none';
					bracketCanvas.style.position = 'relative';
					bracketCanvas.style.top = '0px';
					bracketCanvas.style.zIndex = 0;
					bracketCanvas.className = 'bracketCanvas mainCanvas'

					overlayCanvas.style.position = 'relative';
					overlayCanvas.style.top = -height + 'px';
					overlayCanvas.width = width;
					overlayCanvas.height = height;
					overlayCanvas.style.width = width + 'px';
					overlayCanvas.style.height = height + 'px';
					overlayCanvas.style.userSelect = 'none';
					overlayCanvas.style.zIndex = 1;
					overlayCanvas.className = 'bracketCanvas overlayCanvas'
					canvases.style.width = Math.min(width, window.innerWidth - 20) + 'px';
					canvases.style.height = Math.min(height, window.innerHeight - 20) + 'px';
					canvases.style.overflow = 'hidden';
					canvases.style.cursor = 'move';
					ctx.fillStyle = 'white';
					bracket.UI.push(controls);
					bracket.entrants.forEach(function (entrant) {
						entrant.player.UI.push(controls);
					});
					bracket.event.UI.push(controls);
					i = nodes.length;
					while (i--) {
						node = nodes[i];
						node.x = node.col * hGap;
						if (node.type % 2 === 0) {
							if (node.col % 2 === 0) {
								node.y = Math.floor(Math.pow(2, (Math.abs(node.col)) / 2 + 1)) * vGap * (node.row + 0.5) + (Math.floor(Math.pow(2, (Math.abs(node.col)) / 2)) - 1) * vGap - vGap;
							} else {
								node.y = Math.floor(Math.floor(Math.pow(2, (Math.abs(node.col) + 1) / 2 + 1)) * vGap * (node.row + 0.25) +
									(Math.floor(Math.pow(2, (Math.abs(node.col)) / 2)) - 1) * vGap +
									Math.floor(Math.pow(2, (Math.abs(node.col)) / 2 + 1)) * vGap * (0.25) - vGap / 2);
							}
						} else {
							if (node.type === BracketNode.GF) {
								node.y = node.y = Math.floor(Math.pow(2, Math.abs(node.col - 2) + 1)) * vGap + (Math.floor(Math.pow(2, Math.abs(node.col - 2))) - 1) * vGap;
							} else {
								node.y = Math.floor(Math.pow(2, Math.abs(node.col) + 1)) * vGap * node.row + (Math.floor(Math.pow(2, Math.abs(node.col))) - 1) * vGap;
							}
						}
						node.y += vGap * 0.5;
						if (node.type === (bracket.type === Bracket.SINGLE_ELIM ? BracketNode.WF : BracketNode.GF) && node.resolved) {
							completed = true;
						}
					}
					updateNames();
					refresh();
					overlayCanvas.addEventListener('mousemove', function (e) {
						if (dragging) {
							refreshOverlay();
							highlighted = undefined;
							panX += e.offsetX - dragX;
							panY += e.offsetY - dragY;
							if (panX > mostLeft) {
								panX = mostLeft;
							}
							if (panY > 0) {
								panY = 0;
							}
							dragX = e.offsetX;
							dragY = e.offsetY;
							refresh();
						}
						var node = findNode(e);
						if (node !== highlighted && typeof contextMenu === 'undefined') {
							highlighted = node;
							refreshOverlay(node);
						}
					}, false);
					overlayCanvas.addEventListener('mouseout', function () {
						refreshOverlay(null, dragFrom, null);
						highlighted = null;
						dragging = false;
					}, false);
					overlayCanvas.addEventListener('mousedown', function (e) {
						if (e.button === 0) {
							dragX = e.offsetX;
							dragY = e.offsetY;
							dragging = true;
						}
					}, false);
					overlayCanvas.addEventListener('mouseup', function (e) {
						if (e.button === 0) {
							dragging = false;
						}
					}, false);
					overlayCanvas.oncontextmenu = function (e) {
						e.preventDefault();
						e.stopPropagation();
						return false;
					};
					overlayCanvas.addEventListener('click', function (e) {
					}, false);

					viewImage.type = 'button';
					viewImage.addEventListener('click', function () {
						var tx = panX,
							ty = panY;
						panX = mostLeft;
						panY = 0;
						refresh(true);
						window.open(bracketCanvas.toDataURL());
						panX = tx;
						panY = ty;
						refresh(true);
					}, false);
					viewImage.value = 'View image';
					bracketDiv.appendChild(viewImage);

					canvases.appendChild(bracketCanvas);
					canvases.appendChild(overlayCanvas);
					container.appendChild(canvases);
					bracketDiv.style.position = 'relative';
					bracketDiv.style.left = '0px';
					bracketDiv.style.top = '0px';
					container.appendChild(bracketDiv);
					return container;
				},
				roundRobin: function (data) {
					//WIP
					var bracket = data,
						container = document.createElement('div'),
						bracketCanvas = document.createElement('canvas'),
						overlayCanvas = document.createElement('canvas'),
						canvases = document.createElement('div'),
						width = 600,
						height = 400,
						controls = {
							refresh: function () {
								//updateNames();
								//refresh();
							},
							remove: function (bracket) {
								/*if (bracket instanceof Bracket) {
									bracket.entrants.forEach(function (entrant) {
										entrant.player.UI.splice(entrant.player.UI.indexOf(controls), 1);
									});
									container.parentNode.removeChild(container);
								} else if (bracket instanceof Player) {
									updateNames();
									refresh();
								}*/
							}
						};
					
					/*bracketCanvas.width = width;
					bracketCanvas.height = height;
					bracketCanvas.style.width = width + 'px';
					bracketCanvas.style.height = height + 'px';
					bracketCanvas.style.userSelect = 'none';
					bracketCanvas.style.position = 'relative';
					bracketCanvas.style.top = '0px';
					bracketCanvas.style.zIndex = 0;
					bracketCanvas.className = 'bracketCanvas mainCanvas'

					overlayCanvas.style.position = 'relative';
					overlayCanvas.style.top = -height + 'px';
					overlayCanvas.width = width;
					overlayCanvas.height = height;
					overlayCanvas.style.width = width + 'px';
					overlayCanvas.style.height = height + 'px';
					overlayCanvas.style.userSelect = 'none';
					overlayCanvas.style.zIndex = 1;
					overlayCanvas.className = 'bracketCanvas overlayCanvas'
					canvases.style.width = width + 'px';
					canvases.style.height = height + 'px';
					canvases.style.overflow = 'hidden';
					
					canvases.appendChild(bracketCanvas);
					canvases.appendChild(overlayCanvas);
					container.appendChild(canvases);*/
					var pool,
						match,
						table,
						tr,
						td;
					//table = document.createElement('table');
					//for (pool = 0; pool < bracket.pools.length; pool++) {
					//	
					//}
					return container;
				}
			},
			buildTemplate: function (hostElement, templateName, data, selectInput) {
				var element = UI.templates[templateName](data),
					i = 0,
					inputs = element.getElementsByTagName('input'),
					l = inputs.length;
				hostElement.appendChild(element);
				if (selectInput === true || typeof selectInput === 'undefined') {
					for (i = i; i < l; i++) {
						if (typeof inputs[i] !== 'undefined' && inputs[i].type === 'text') {
							inputs[i].focus();
							break;
						}
					}
				}
				return element;
			}
		},
		init = function () {
			Math.findNextPowerOfTwo = function (n) {
				var power = 1;
				while (power < n) {
					power *= 2;
				}
				return power;
			};
			window.addEventListener('load', function () {
				var brackets = document.getElementsByClassName('bracket'),
					tester,
					tournament,
					i,
					makeDataset = function (element) {
						var i = element.attributes.length,
							dataset = {},
							name;
						while (i--) {
							name = element.attributes[i].name;
							if (name.indexOf('data-') === 0) {
								dataset[name.substr(5)] = element.attributes[i].value;
							}
						}
						element.dataset = dataset;
					};
				for (i = 0; i < brackets.length; i++) {
					if (!brackets[i].dataset) {
						makeDataset(brackets[i]);
					}
					if (brackets[i].dataset.tournament) {
						var bracket = brackets[i];
						tester = bracket.dataset.tournament;
						tournament = Files.loadFromJSON(JSON.parse(tester));
						tournament.events.forEach(function (evt) {
							if (evt.bracket) {
								if (evt.bracket.type === Bracket.ROUND_ROBIN) {
									UI.buildTemplate(bracket, 'roundRobin', evt.bracket);
								} else {
									UI.buildTemplate(bracket, 'bracket', evt.bracket);
								}
							}
						});
					} else if (brackets[i].dataset.src && Site.getFile) {
						var ajaxload = (function () {
								var bracket = brackets[i];
								return function () {
									Site.getFile(bracket.dataset.src, function () {
										tester = this.responseText;
										if (this.responseText !== '0') {
											bracket.innerHTML = '';
											tournament = Files.loadFromJSON(JSON.parse(tester));
											tournament.events.forEach(function (evt) {
												if (evt.bracket) {
													if (evt.bracket.type === Bracket.ROUND_ROBIN) {
													} else {
														UI.buildTemplate(bracket, 'bracket', evt.bracket);
													}
												}
											});
										}
									});
								}
							}()),
							buttons = brackets[i].getElementsByTagName('button'),
							ii = buttons.length;
						if (ii > 0) {
							while (ii--) {
								buttons[ii].addEventListener('click', ajaxload, false);
							}
						} else {
							ajaxload();
						}
					}
				}
			}, false);
		};

	Tournament.prototype = {
		addPlayer: function (player) {
			this.players.push(player);
			this.UI.forEach(function (UI) {
				UI.addPlayer(player);
			});
		},
		update: updateUI,
		remove: removeUI
	};

	Player.prototype = {
		update: updateUI,
		remove: removeUI
	};

	Event.SINGLES = 0;
	Event.DOUBLES = 1;
	Event.prototype = {
		update: updateUI,
		addPlayer: function (player) {
			var i = this.UI.length;
			if (this.entrants.filter(function (val) {
					return val.player === player.player;
				}).length === 0) {
				this.entrants.push(player);
				while (i--) {
					if (typeof this.UI[i].addPlayer !== 'undefined') {
						this.UI[i].addPlayer(player);
					}
				}
			}
		},
		remove: removeUI
	};

	Bracket.SINGLE_ELIM = 0;
	Bracket.DOUBLE_ELIM = 1;
	Bracket.ROUND_ROBIN = 2;
	Bracket.prototype = {
		update: updateUI,
		remove: removeUI,
		refreshProgress: function (fromNode) {
			var bracket = this;
			bracket.progress[bracket.nodes.indexOf(fromNode)] = typeof fromNode.order[0] === 'undefined' ? undefined : fromNode.order;
			fromNode.nodesOut.forEach(function (node) {
				bracket.refreshProgress(node);
			});
		},
		swapNodes: function (dragFrom, dragTo) {
			var playerSwap = this.entrants[this.playerNodes.indexOf(dragFrom)];
			this.entrants[this.playerNodes.indexOf(dragFrom)] = this.entrants[this.playerNodes.indexOf(dragTo)];
			this.entrants[this.playerNodes.indexOf(dragTo)] = playerSwap;
			playerSwap = dragFrom.player;
			dragFrom.player = dragTo.player;
			dragTo.player = playerSwap;
		}
	};

	BracketNode.ROOT = 1;
	BracketNode.WINNERS = 3;
	BracketNode.WQF = 5;
	BracketNode.WSF = 7;
	BracketNode.WF = 9;
	BracketNode.GF = 11;
	BracketNode.GF2 = 13;
	BracketNode.LOSERS = 2;
	BracketNode.LQF = 4;
	BracketNode.LSF = 6;
	BracketNode.LF = 8;
	BracketNode.PLAYER_NODE = 21;
	BracketNode.BYE_NODE = 23;
	BracketNode.prototype = {
		setPlace: function (node, place) {
			this.order[place] = node;
		},
		setLoser: function (node) {
			var winner = this.nodesIn[this.nodesIn.indexOf(node) === 1 ? 0 : 1];
			this.order[0] = winner;
			this.order[1] = node;
		},
		setWinner: function (node) {
			var loser = this.nodesIn[this.nodesIn.indexOf(node) === 1 ? 0 : 1];
			this.order[0] = node;
			this.order[1] = loser;
		},
		reset: function () {
			this.bye = false;
			this.order = [];
			this.resolved = false;
			this.names = [];
			this.nodesOut.forEach(function (node) { node.reset(); });
		},
		findPlayer: function (fromType) {
			var player,
				currentNode = this,
				lastNode,
				findParent = function (nodeIn) {
					return nodeIn === currentNode.order[(nodeIn.type + currentNode.type) & 1];
				};
			while (typeof player === 'undefined') {
				if (currentNode.type === BracketNode.PLAYER_NODE) {
					player = currentNode.player;
				} else if (typeof lastNode !== 'undefined' && currentNode.type === BracketNode.ROOT) {
					player = currentNode.nodesIn[(lastNode.type % 2) === 0 ? 1 : 0].player;
				} else {
					currentNode = currentNode.nodesIn.filter(findParent)[0];
				}
				lastNode = currentNode;
			}
			return player;
		},
		findPlayerName: function (fromType) {
			return this.findPlayer(fromType).nick || 'null';
		},
		isReady: (function () {
			var isResolved = function (node) {
				return !node.resolved;
			};
			return function () {
				return this.nodesIn.filter(isResolved).length === 0;
			};
		}())
	};
	PlayerNode.prototype = BracketNode.prototype;
	return {
		init: init
	};
}());
Cube.init();