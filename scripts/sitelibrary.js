(function () {
	var Site = {},
		linkRegex = /\bhttps?:\/\/[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|]/ig,
		success = 200,
		authCheck = '<AUTH>',
		authPath = '/auth/',
		authkey = null,
		root,
		rl;
	Site.getRoot = function () {
		if (!Site.root) {
			Site.root = document.getElementById('weblocation').value;
			root = Site.root;
			rl = root.length;
		}
		return (Site.getRoot = function () {
			return root;
		})();
	};
	Site.makeDataset = function (element) {
		var i,
			dataset,
			name;
		if (!element.dataset) {
			dataset = {}
			i = element.attributes.length;
			while (i--) {
				name = element.attributes[i].name;
				if (name.indexOf('data-') === 0) {
					dataset[name.substr(5)] = element.attributes[i].value;
				}
			}
			element.dataset = dataset;
		}
	};
	Site.getFile = function (path, onSuccess, onFailure) {
		try {
			var client = new XMLHttpRequest();
		} catch (e) {
			//console.log('This browser does not support XMLHttpRequest.');
			return;
		}
		var success = 200;
		client.addEventListener('readystatechange', function () {
			if (this.readyState == XMLHttpRequest.DONE && this.status == success) {
				if (this.responseText.substring(0, 6) === authCheck) {
					authkey = this.responseText.substring(6);
					Site.getFile(path, onSuccess, onFailure)
				} else {
					if (typeof onSuccess !== 'undefined' && onSuccess instanceof Function) {
						onSuccess.apply(this);
					}
				}
			} else if (this.readyState == XMLHttpRequest.DONE && this.status != success) {
				if (typeof onFailure !== 'undefined' && onFailure instanceof Function) {
					onFailure.apply(this);
				}
			}
		}, false);
		if (authkey === null) {
			client.open('GET', path);
		} else {
			console.log(root, authPath, authkey, path.substring(rl), path, rl);
			client.open('GET', root + authPath + authkey + path.substring(rl));
		}
		client.send();
	};
	Site.parseLinks = function (text) {
		var textnodes = text.split(linkRegex),
			links = text.match(linkRegex),
			container = document.createElement('span'),
			a, i, l;
		console.log(textnodes, links);
		if (links === null) {
			return document.createTextNode(text);
		} else {
			l = links.length;
			for (i = 0; i < l; i++) {
				container.appendChild(document.createTextNode(textnodes[i]));
				a = document.createElement('a');
				a.href = links[i];
				a.appendChild(document.createTextNode(links[i]))
				container.appendChild(a);
			}
			container.appendChild(document.createTextNode(textnodes[i]));
			console.log(container);
			return container;
		}
	};
	window.addEventListener('load', function () {
		var autocomplete = document.getElementsByClassName('autocomplete'),
			autocheck = document.getElementsByClassName('autocheck'),
			flag = document.getElementsByClassName('flag'),
			startFlag = function (e) {
				var target = e.target,
					href = target.href.substring(target.href.indexOf('/', 7)),
					parent = target.parentNode,
					container = document.createElement('span'),
					remove = document.createElement('button'),
					submit = document.createElement('button'),
					comment = document.createElement('input'),
					status = document.createElement('button');
				remove.appendChild(document.createTextNode('x'));
				remove.style.border = '1px dashed red';
				comment.type = 'text';
				comment.placeholder = 'Comment';
				submit.appendChild(document.createTextNode('OK'));
				submit.style.border = '1px dashed blue';
				status.appendChild(document.createTextNode(''));
				status.style.border = '1px dashed blue';
				remove.addEventListener('click', function () {
					parent.replaceChild(target, container);
					comment.value = '';
				}, false);
				submit.addEventListener('click', function () {
					status.firstChild.textContent = 'Waiting..';
					parent.replaceChild(status, container);
					Site.getFile(href + '&ajax=1&comment=' + encodeURIComponent(comment.value), function () {
						status.firstChild.textContent = this.responseText;
					});
				}, false);
				status.addEventListener('click', function () {
					parent.replaceChild(target, status);
				}, false);
				container.appendChild(remove);
				container.appendChild(comment);
				container.appendChild(submit);
				parent.replaceChild(container, target)
				comment.focus();
				e.preventDefault();
			},
			i,
			l,
			j,
			el,
			flags,
			arrowKeys = [37, 38, 39, 40];
		Site.root = Site.getRoot();

		//flag submit controls
		for (i = 0, l = flag.length; i < l; i++) {
			el = flag[i];
			flags = el.getElementsByTagName('a');
			j = flags.length;
			while (j--) {
				flags[j].addEventListener('click', startFlag, false);
			}
		}

		//autocomplete for input fields
		for (i = 0, l = autocomplete.length; i < l; i++) {
			el = autocomplete[i];
			Site.makeDataset(el);
			if (el.type == 'text' && el.dataset.script) {
				(function () {
					var element = el,
						id = 0,
						state = element.value,
						autosuggest = function () {
							var response,
								evt;
							if (this.responseText.length > 0) {
								response = JSON.parse(this.responseText);
								if (response.hasOwnProperty('msg') && response.msg !== null) {
									if (parseInt(response.id, 10) === id) {
										element.value = state + response.msg.substr(state.length);
										element.selected = element.setSelectionRange(state.length, element.value.length);
										if (element.dataset.forcematch) {
											if (state.toLowerCase() === response.msg.toLowerCase()) {
												element.classList.add('confirmed');
												element.classList.remove('denied');
											} else {
												element.classList.add('denied');
											}
										}
										evt = new Event('autocomplete');
										response.status = state.toLowerCase() === response.msg.toLowerCase();
										evt.response = response;
										element.dispatchEvent(evt);
									}
								}
							}
						};
					element.addEventListener('keydown', function (e) {
						if (e.keyCode === 37) {
							//left arrow
							if (element.selectionEnd === element.value.length) {
								element.value = element.value.substring(0, element.selectionStart);
							}
						}
						if (e.keyCode !== 8) {
							state = element.value;
						} else if (element.selectionEnd === element.value.length) {
							element.value = element.value.substring(0, element.selectionStart);
							state = element.value;
						}
						id++;
					}, false);
					element.addEventListener('keyup', function (e) {
						if (arrowKeys.indexOf(e.keyCode) === -1) {
							if (element.selectionEnd === element.value.length) {
								state = element.value.substring(0, element.selectionStart);
							} else {
								state = element.value;
							}
							Site.getFile(Site.root + element.dataset.script + '?val=' + encodeURIComponent(state) + (element.dataset.params || '') + '&id=' + id, autosuggest);
						}
					}, false);
				}());
			}
		}
		
		//autocheck for input fields
		for (i = 0, l = autocheck.length; i < l; i++) {
			el = autocheck[i];
			Site.makeDataset(el);
			if (el.type == 'text' && el.dataset.script) {
				(function () {
					var element = el,
						id = 0,
						state = element.value,
						autosuggest = function () {
							var response,
								evt;
							if (this.responseText.length > 0) {
								response = JSON.parse(this.responseText);
								if (response.hasOwnProperty('status')) {
									if (parseInt(response.id, 10) === id) {
										response.status = response.status === 'ok';
										evt = new Event('autocheck');
										evt.response = response;
										element.dispatchEvent(evt);
										if (element.dataset.msg && response.hasOwnProperty('msg')) {
											element.nextSibling.firstChild.data = element.dataset.msg;
										}
										if (response.status) {
											element.classList.add('confirmed');
											element.classList.remove('denied');
										} else {
											element.classList.add('denied');
										}
									}
								}
							}
						};
					element.addEventListener('keydown', function (e) {
						state = element.value;
						id++;
					}, false);
					element.addEventListener('keyup', function (e) {
						state = element.value;
						Site.getFile(Site.root + element.dataset.script + '?val=' + encodeURIComponent(state) + (element.dataset.params || '') + '&id=' + id, autosuggest);
					}, false);
				}());
			}
		}
	}, false);
	window.Site = Site;
}());