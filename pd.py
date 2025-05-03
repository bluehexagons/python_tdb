import xml.etree.cElementTree as ET
import re
import json
import time
import datetime
import calendar
import cgi
from cgi import escape
from urllib import quote, unquote
import os.path
import sys
import sqlite3
import struct
import gzip
import random
from urlparse import parse_qs
from hashlib import sha256
from Cookie import SimpleCookie
from pprint import pformat
from ConfigParser import SafeConfigParser

sys.path.append(os.path.dirname(__file__))
import pbkdf2

dataLocation = os.path.abspath(os.path.dirname(__file__)) + '/' #location on local disk
cache = sqlite3.connect(':memory:')

config = SafeConfigParser()
config.read(dataLocation + 'conf.ini')
webloc = config.get('location', 'webloc')
locationIndex = len(webloc)
tiostore = dataLocation + config.get('location', 'tiostore')
content = dataLocation + config.get('location', 'content')
pwsalt = config.get('location', 'pwsalt')
snsalt = config.get('location', 'snsalt')
pwrepetitions = config.getint('location', 'pwrepetitions')
snduration = 2700000 #login session duration, just over one month
lastpurge = 0 #last purge of expired session IDs

def now():
	#returns current time in seconds since epoch (GMT)
	return calendar.timegm(time.gmtime())

def passhash(password, pwreps):
	#hashes a password for storage
	return pbkdf2.crypt(password, pwsalt, pwreps).split('$', 4)[4]

def sessionid():
	#generates a new sessionid to use with cookies
	return hex(random.getrandbits(128))[2:-1] + hex(int(time.time() * 1000))[2:-1]

def totoken(sessionid):
	#hashes supplied sessionid and returns a sha256 hash, used for storage
	a = sha256()
	a.update(snsalt)
	a.update(sessionid)
	return a.hexdigest()

def ftime(inttime):
	return time.strftime('%b %d, %Y', time.gmtime(inttime))

def research(regex, text):
	return re.search(regex, text, re.IGNORECASE) is not None

def startswith(text, what):
	return text.lower().startswith(what.lower())

class commaseparate:
	def __init__(self):
		self.values = []
	
	def step(self, value):
		self.values.append(str(value))
	
	def finalize(self):
		return ', '.join(self.values)

class joinstr:
	def __init__(self):
		self.values = []
	
	def step(self, value, separator):
		self.values.append(str(value))
		self.separator = separator
	
	def finalize(self):
		return self.separator.join(self.values)

class playerlist:
	def __init__(self):
		self.lines = []
	
	def step(self, game, type, rating):
		if rating != None:
			if type != 'Singles':
				self.lines.append((str(game), ' - ', str(type), ' (', str(int(rating)), ')'))
			else:
				self.lines.append((str(game), ' (', str(int(rating)), ')'))
		else:
			self.lines.append((str(game), ' - ', str(type)))
	def finalize(self):
		return ', '.join((''.join(line) for line in self.lines))

class slashseparate:
	def __init__(self):
		self.values = []
	
	def step(self, value):
		self.values.append(str(value))
	
	def finalize(self):
		return '/'.join(self.values)

conn = None
def connect(reconnect=False):
	global conn
	try:
		conn.commit()
		conn.close()
	except:
		pass
	conn = sqlite3.connect(dataLocation + 'data.sqlite')
	conn.row_factory = sqlite3.Row
	conn.create_function('passhash', 2, passhash)
	conn.create_function('totoken', 1, totoken)
	conn.create_function('now', 0, now)
	conn.create_function('REGEXP', 2, research)
	conn.create_function('startswith', 2, startswith)
	conn.create_aggregate('joinstr', 2, joinstr)
	conn.create_aggregate('commaseparate', 1, commaseparate)
	conn.create_aggregate('slashseparate', 1, slashseparate)
	conn.create_aggregate('playerlist', 3, playerlist)
	conn.create_aggregate('quote', 1, quote)

#establish a connection to the database
if os.path.exists(dataLocation + 'data.sqlite'):
	connect()
else:
	with open(dataLocation + 'dbbuildscript') as file:
		#build the database if the file isn't there
		#TODO: restore from most recent backup
		buildscript = file.read()
		conn = sqlite3.connect(dataLocation + 'data.sqlite')
		conn.executescript(buildscript)
		conn.commit()

def application(environ, start_response):
	status = '200 OK'
	cookie = None #cookie retrieved from client
	user = None
	userid = None #userid of the client
	certified = 0 #raw certification level of user
	canupload = False #if user can upload tournaments
	username = None
	if 'HTTP_COOKIE' in environ:
		cookie = SimpleCookie(environ['HTTP_COOKIE'])
	else:
		cookie = SimpleCookie()
	addtimer = True
	cookiedata = SimpleCookie()
	redirect = None
	page = '<html lang="en-us"><head><title>Player Database</title><meta http-equiv="Content-Language" content="en"/><link rel="stylesheet" href="/styles/style.css" type="text/css" /><script type="text/javascript" src="/scripts/bracket.js"></script><script type="text/javascript" src="/scripts/sitelibrary.js"></script></head><body>%s</body></html>'
	path = environ['REQUEST_URI'][locationIndex:].split('?', 1)[0].replace('.', '')
	query = parse_qs(environ['QUERY_STRING'])
	if path == '/unlockdb':
		conn.interrupt()
		connect(True)
	global lastpurge
	if now() - lastpurge > 86400:
		try:
			conn.execute('DELETE FROM usersession WHERE expires<now()')
			conn.commit()
			lastpurge = now()
		except:
			#conn.rollback()
			#conn.close()
			connect(True)
	if 'session' in cookie:
		#load the session data of the client
		try:
			user = conn.execute('SELECT userid FROM usersession WHERE token=totoken(?)', (cookie['session'].value,)).fetchone()
		except:
			#conn.rollback()
			#conn.close()
			connect(True)
		if user is not None:
			#load the actual user
			user = conn.execute('SELECT userid, username, certified FROM user WHERE userid=?', (user['userid'],)).fetchone()
			if user is not None:
				userid = user['userid']
				certified = user['certified']
				canupload = certified > 0
				moderator = certified > 1
				admin = certified > 2
				username = user['username']
	
	def preprocess(filecontent):
		#active tag processing, switch to less lazy solution later
		processed = filecontent
		if userid is not None:
			processed = re.sub('<loggedout>.*?</loggedout>', '', processed, re.DOTALL)
		else:
			processed = re.sub('<loggedin>.*?</loggedin>', '', processed, re.DOTALL)
		if canupload == False:
			processed = re.sub('<canupload>.*?</canupload>', '', processed, re.DOTALL)
		if moderator == False:
			processed = re.sub('<moderator>.*?</moderator>', '', processed, re.DOTALL)
		if admin == False:
			processed = re.sub('<admin>.*?</admin>', '', processed, re.DOTALL)
		processed = re.sub('(</?loggedout>|</?loggedin>|</?canupload>|</?moderator>|</?admin>)', '', processed, re.DOTALL)
		processed = re.sub('<username />', str(username), processed)
		processed = re.sub('<userid />', str(userid), processed)
		processed = re.sub('<root />', webloc, processed)
		return processed
	
	def tsearch(name=None, region=None, date=None, game=None, type=None, rated=True):
		conditions = [] #'published=1' later
		params = []
		order = 'timestamp DESC, name ASC'
		if name is not None:
			conditions.append('name REGEXP ?')
			params.append('\\b' + re.escape(name) + '\\b')
		if region is not None:
			conditions.append('regionid IN (SELECT regionid FROM regions WHERE name REGEXP ?)')
			params.append('\\b' + re.escape(region) + '\\b')
		if rated:
			conditions.append('0 < (SELECT COUNT(*) FROM event WHERE event.tournamentid = tournament.tournamentid AND rated=1)')
		if game is not None:
			if type is None and game.split(' ')[-1].lower() in ('doubles', 'singles', 'teams'):
				type = game.split(' ')[-1]
				game = game[0:game.rfind(' ')]
			if type is not None:
				conditions.append('tournamentid IN (SELECT tournamentid FROM event WHERE gameid IN (SELECT gameid FROM game WHERE name REGEXP ? AND category = ?))')
				params.append('\\b' + re.escape(game) + '\\b')
				if type.lower() in ('doubles', 'teams'):
					type = 'Teams'
				params.append(re.escape(type))
			else:
				conditions.append('tournamentid IN (SELECT tournamentid FROM event WHERE gameid IN (SELECT gameid FROM game WHERE name REGEXP ?))')
				params.append('\\b' + re.escape(game) + '\\b')
		elif type is not None:
			if type.lower() in ('doubles', 'teams'):
				type = 'Teams'
			conditions.append('tournamentid IN (SELECT tournamentid FROM event WHERE gameid IN (SELECT gameid FROM game WHERE category = ?))')
			params.append(re.escape(type))
		if date is not None:
			datedigit = None
			maxdiff = now()
			try:
				datedigit = calendar.timegm(time.strptime(date, '%b %d, %Y'))
				order = 'abs(timestamp - ?) ASC, timestamp DESC LIMIT 25'
				params.append(int(datedigit))
			except:
				try:
					datedigit = calendar.timegm(time.strptime(date, '%b %d %Y'))
					order = 'abs(timestamp - ?) ASC, timestamp DESC LIMIT 25'
					params.append(int(datedigit))
				except:
					try:
						datedigit = calendar.timegm(time.strptime(date, '%b %Y')) + 1314871
						maxdiff = 1314871
						conditions.append('abs(timestamp - ?) < ?')
						params.append(int(datedigit))
						params.append(int(maxdiff))
					except:
						try:
							datedigit = calendar.timegm(time.strptime(date, '%B %Y')) + 1314871
							maxdiff = 1314871
							conditions.append('abs(timestamp - ?) < ?')
							params.append(int(datedigit))
							params.append(int(maxdiff))
						except:
							try:
								datedigit = calendar.timegm(time.strptime(date, '%Y')) + 15778463
								maxdiff = 15778463
								params.append(int(datedigit))
								conditions.append('abs(timestamp - ?) < ?')
								params.append(int(datedigit))
								params.append(int(maxdiff))
							except:
								datedigit = None
		if len(conditions) > 0:
			return conn.execute('SELECT tournamentid, name, timestamp FROM tournament WHERE %s ORDER BY %s' % (' AND '.join(conditions), order), params)
		#elif name is not None or region is not None or date is not None or game is not None:
		#	return conn.execute('SELECT tournamentid, name, timestamp FROM tournament ORDER BY %s' % order, params)
		else:
			return conn.execute('SELECT tournamentid, name, timestamp FROM tournament ORDER BY %s' % order)
	
	def psearch(name=None, region=None, character=None, game=None, type=None, rating=None):
		conditions = []
		params = []
		order = 'nickname ASC'
		if name is not None:
			conditions.append('(nickname = ? OR nickname REGEXP ?)')
			params.append(name)
			params.append('\\b' + re.escape(name) + '\\b')
		if region is not None:
			conditions.append('regionid IN (SELECT regionid FROM regions WHERE name REGEXP ?)')
			params.append('\\b' + re.escape(region) + '\\b')
		if rating is not None:
			if rating.isdigit():
				conditions.append('currentelo = ?')
				params.append(int(rating))
			elif rating[-1] == '+' and rating[:-1].isdigit():
				conditions.append('currentelo >= ?')
				params.append(int(rating[:-1]))
			elif rating[0] == '<' and rating[1:].isdigit():
					conditions.append('currentelo < ?')
					params.append(int(rating[1:].isdigit()))
			elif '-' in rating and rating.count('-') == 1:
				if rating[0] == '-' and rating[1:].isdigit():
					conditions.append('currentelo <= ?')
					params.append(int(rating[1:].isdigit()))
				elif rating.split('-')[0].isdigit() and rating.split('-')[1].isdigit() and int(rating.split('-')[0]) < int(rating.split('-')[1]):
					conditions.append('currentelo >= ?')
					params.append(int(rating.split('-')[0]))
					conditions.append('currentelo <= ?')
					params.append(int(rating.split('-')[1]))
		if game is not None:
			if type is None and game.split(' ')[-1].lower() in ('doubles', 'singles', 'teams'):
				game = game[0:game.rfind(' ')]
				type = game.split(' ')[-1]
			if type is not None:
				conditions.append('player.gameid IN (SELECT gameid FROM game WHERE name REGEXP ? AND category = ?)')
				params.append('\\b' + re.escape(game) + '\\b')
				if type.lower() in ('doubles', 'teams'):
					type = 'Teams'
				params.append(re.escape(type))
			else:
				conditions.append('player.gameid IN (SELECT gameid FROM game WHERE name REGEXP ?)')
				params.append('\\b' + re.escape(game) + '\\b')
		elif type is not None:
			if type.lower() in ('doubles', 'teams'):
				type = 'Teams'
			conditions.append('player.gameid IN (SELECT gameid FROM game WHERE category = ?)')
			params.append(re.escape(type))
		if len(conditions) > 0:
			return conn.execute('SELECT nickname, slashseparate(playerid) AS ids, playerlist(name, category, currentelo) AS names FROM player JOIN game ON player.gameid = game.gameid WHERE %s GROUP BY nickname ORDER BY %s' % (' AND '.join(conditions), order), params)
		#elif name is not None or region is not None or game is not None:
		#	return conn.execute('SELECT nickname, commaseparate(playerid) AS ids, commaseparate(name) AS names FROM player JOIN game ON player.gameid = game.gameid GROUP BY nickname ORDER BY %s' % order, params)
		else:
			return conn.execute('SELECT nickname, slashseparate(playerid) AS ids, playerlist(name, category, currentelo) AS names FROM player JOIN game ON player.gameid = game.gameid GROUP BY nickname ORDER BY %s' % order)
	
	start = time.clock() #times loading of the page
	#TODO: cache header and other content files
	header = preprocess(open(dataLocation + 'header.htm').read())
	if os.path.exists(content + path + '.htm'):
		#if the requested location is the name of a content file
		output = preprocess(open(content + path + '.htm', 'r').read())
		if path == '/register':
			#registration page
			#TODO: change this mess
			if len(environ['QUERY_STRING']) > 0:
				page = '%s'
				header = ''
				addtimer = False
				if conn.execute('SELECT userid FROM user WHERE username=?', (environ['QUERY_STRING'],)).fetchone() is None:
					output = '1'
				else:
					output = '0'
			elif 'CONTENT_LENGTH' in environ:
				form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ)
				if 'username' in form and 'password' in form:
					if 'nickname' in form:
						output = registeruser(form['username'].value, form['password'].value, cookiedata, form['nickname'].value)
					else:
						output = registeruser(form['username'].value, form['password'].value, cookiedata)
		elif path == '/login':
			#login page
			if 'CONTENT_LENGTH' in environ:
				form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ)
				if 'username' in form and 'password' in form:
					user = conn.execute('SELECT userid, username FROM user WHERE username=? AND pwhash=passhash(?, pwreps)', (form['username'].value, form['password'].value)).fetchone()
					if (user is not None):
						makesession(user['userid'], 'rememberme' in form and form['rememberme'].value == 'on', cookiedata)
						output = 'Welcome back, ' + escape(str(user['username'])) + '!' + (' Your browser will keep you logged in for a month.' if 'rememberme' in form and form['rememberme'].value == 'on' else '')
						redirect = webloc
					else:
						output += 'Username and password do not match.'
		elif path == '/logout':
			#logout page
			if userid is not None:
				cookiedata['session'] = ''
				cookiedata['session']['expires'] = 0
				conn.execute('DELETE FROM usersession WHERE token=totoken(?)', (cookie['session'].value,))
				conn.commit()
				redirect = webloc
		elif path == '/profile':
			#profile page
			pass
		elif path == '/profile/tournaments':
			#uploaded tournaments page
			if userid is not None:
				listoutput = []
				listoutput.append('Your tournaments:<br />')
				for tourney in conn.execute('SELECT tournamentid, name, timestamp, regionid, original FROM tournament WHERE uploaderid=?', (userid,)):
					listoutput.extend(('#', str(tourney['tournamentid']), ' <a href="', webloc, '/tournament/', str(tourney['tournamentid']), '">', escape(tourney['name']), '</a>: ', time.strftime('%b %d, %Y', time.gmtime(tourney['timestamp'])), '<br /><div class="bracket" data-src="', webloc, '/jsondata/', str(tourney['tournamentid']),'"><button>View brackets</button></div><br />'))
				output = ''.join(listoutput)
		elif path == '/tournaments':
			output = re.sub('<tournamentname />', escape(query['name'][0], '"') if 'name' in query else '', output)
			output = re.sub('<tournamentregion />', escape(query['region'][0], '"') if 'region' in query else '', output)
			output = re.sub('<tournamentdate />', escape(query['date'][0], '"') if 'date' in query else '', output)
			output = re.sub('<tournamentgame />', escape(query['game'][0], '"') if 'game' in query else '', output)
			output = re.sub('<tournamenttype />', escape(query['type'][0], '"') if 'type' in query else '', output)
			output = re.sub('<tournamentrated />', '' if 'rated' in query and query['rated'][0] != 'true' else 'checked', output)
			#conn.execute('SELECT tournamentid, name, timestamp FROM tournament WHERE name REGEXP ? ORDER BY timestamp DESC', ('.*' + re.escape(query['name'][0]) + '.*',))
			rows = tsearch(query['name'][0] if 'name' in query else None, query['region'][0] if 'region' in query else None, query['date'][0] if 'date' in query else None, query['game'][0] if 'game' in query else None, query['type'][0] if 'type' in query else None, query['rated'][0] == 'true' if 'rated' in query else True)
			results = []
			for row in rows:
				results.extend(('<li><a href="', webloc, '/tournament/', str(row['tournamentid']), '">', escape(row['name']), '</a> on ', ftime(row['timestamp']), '</li>'))
			output = output.replace('<results />', ''.join(results))
		elif path == '/players':
			output = re.sub('<playername />', query['name'][0] if 'name' in query else '', output)
			output = re.sub('<playerregion />', query['region'][0] if 'region' in query else '', output)
			output = re.sub('<playercharacter />', query['character'][0] if 'character' in query else '', output)
			output = re.sub('<playergame />', query['game'][0] if 'game' in query else '', output)
			output = re.sub('<playertype />', query['type'][0] if 'type' in query else '', output)
			output = re.sub('<playerrating />', query['rating'][0] if 'rating' in query else '', output)
			output = re.sub('<playerrated />', '' if 'rated' in query and query['rated'][0] != 'true' else 'checked', output)
			#conn.execute('SELECT tournamentid, name, timestamp FROM tournament WHERE name REGEXP ? ORDER BY timestamp DESC', ('.*' + re.escape(query['name'][0]) + '.*',))
			rows = psearch(query['name'][0] if 'name' in query else None, query['region'][0] if 'region' in query else None, query['character'][0] if 'character' in query else None, query['game'][0] if 'game' in query else None, query['type'][0] if 'type' in query else None, query['rating'][0] if 'rating' in query else None)
			results = []
			for row in rows:
				results.extend(('<li><a href="', webloc, '/player/', str(row['ids']), '">', escape(row['nickname']), '</a> (', escape(row['names']),')</li>'))
			output = output.replace('<results />', ''.join(results))
		elif path == '/upload':
			#upload page
			if not canupload:
				if userid is None:
					output = 'This page requires uploading privileges. <a href="login">Please log in</a>.'
				else:
					output = 'This page requires uploading privileges. Please ask another user who is able to upload to grant them to you.'
		elif path == '/submitfile':
			#page accessed after submitting files
			if canupload:
				form = cgi.FieldStorage(fp=environ['wsgi.input'], environ=environ)
				if 'file' in form:
					if hasattr(form['file'], 'file'):
						#output += loadFromTio(form['file'].file)
						#form['file'].file.seek(0)
						output += '<br />' + pformat(form['file'].filename)
						result = processupload(form['file'].file, form['file'].filename, userid, cookiedata)
						if str(result).isdigit():
							conn.commit()
							redirect = webloc + '/tournament/' + str(result)
						else:
							conn.rollback()
						output += str(result)
						#debug = gzip.open(dataLocation + os.path.basename(form['file'].filename) + 'debug.txt.gz', 'wb')
						#debug.write(form['file'].file.read())
						#debug.close()
					else:
						results = []
						error = False
						for uploaded in form['file']:
							if hasattr(uploaded, 'file'):
								#output += loadFromTio(file.file)
								#file.file.seek(0)
								output += '<br />' + escape(str(uploaded.filename))
								result = processupload(uploaded.file, uploaded.filename, userid, cookiedata)
								if not str(result).isdigit():
									error = True
								results.append(str(result))
								output += escape(str(result))
								#debug = gzip.open(dataLocation + os.path.basename(file.filename) + 'debug.txt.gz', 'wb')
								#debug.write(file.file.read())
								#debug.close()
						if error:
							conn.rollback()
						else:
							conn.commit()
							redirect = webloc + '/tournament/' + '/'.join(results)
				else:
					output += pformat(form)
			else:
				if userid is None:
					output = 'This page requires uploading privileges. Please log in.'
				else:
					output = 'This page requires uploading privileges. Please ask another user who is able to upload to grant them to you.'
	elif path == '/dump':
		#TODO: remove for production
		#dumps some database stuff
		output = ''
		for row in conn.execute('SELECT * FROM game'):
			output += escape(row['name']) + ' - ' + escape(row['category']) + ' - ' + str(row['gameid']) + '<br />'
		for row in conn.execute('SELECT * FROM player'):
			output += escape(row['nickname']) + ' - ' + str(row['gameid']) + '<br />'
	elif path == '/uploadtester':
		#TODO: remove for production
		#gives uploader privileges to client user
		if not canupload:
			if userid is not None:
				conn.execute('UPDATE user SET certified=1, referredby=-1 WHERE userid=?', (userid,))
				conn.commit()
		output = 'uploadtester'
		redirect = webloc
	elif path == '/modtester':
		#TODO: remove for production
		#gives moderator privileges to client user
		if not moderator:
			if userid is not None:
				conn.execute('UPDATE user SET certified=2, referredby=-1 WHERE userid=?', (userid,))
				conn.commit()
		output = 'modtester'
		redirect = webloc
	elif path.startswith('/recalculate'):
		output = reprocessratings(path.split('/')[2:])
	elif path.startswith('/jsondata/'):
		row = conn.execute('SELECT jsondata FROM tournament WHERE tournamentid=?', (path.split('/')[2],)).fetchone()
		addtimer = False
		page = '%s'
		header = ''
		if row is not None:
			output = row['jsondata']
		else:
			output = '0'
	elif path.startswith('/tournament/'):
		tournamentid = path.split('/')[2]
		row = None
		output = ''
		if tournamentid.isdigit():
			tourneyids = path.split('/')[2:]
			rows = conn.execute('SELECT * FROM tournament JOIN user ON userid = uploaderid WHERE tournamentid in (%s)' % ', '.join('?' for unused in tourneyids), tourneyids)
			#row = conn.execute('SELECT * FROM tournament WHERE tournamentid=?', (tournamentid,)).fetchone()
			for row in rows:
				tourneyinfo = []
				tournamentid = row['tournamentid']
				name = escape(row['name'])
				date = row['timestamp']
				added = ftime(row['timeprocessed'])
				tourneyinfo.extend((name, '<br />', ftime(date), '<br /><br />Added on: ', added, ' by ', row['username'], '<br />', '<div class="bracket" data-src="', webloc, '/jsondata/', str(tournamentid),'"><button>View brackets</button></div>'))
				matches = conn.execute('SELECT winnerid, winner.nickname AS winner, loserid, loser.nickname AS loser, wins, losses, match.rated AS rated, event.timestamp AS eventtime, tournament.name AS tournamentname, event.name AS eventname, match.round AS round, game.name AS gamename, game.category AS gamecategory, winnerelo, winnergain, loserelo, losergain, match.eventid AS eventid FROM match JOIN game ON match.gameid = game.gameid JOIN player AS winner ON match.winnerid = winner.playerid JOIN player AS loser ON match.loserid = loser.playerid JOIN event ON match.eventid = event.eventid JOIN tournament ON match.tournamentid = tournament.tournamentid WHERE match.tournamentid = ? ORDER BY event.timestamp DESC', (tournamentid,))
				currentevent = None
				for match in matches:
					if match['eventname'] != currentevent:
						currentevent = match['eventname']
						tourneyinfo.extend(('<br /><div>', escape(match['eventname']), ' (', escape(match['gamename']), ' - ', escape(match['gamecategory']), ')'))
						if match['rated'] == 0:
							tourneyinfo.extend((' <a href="', webloc, '/rate/', str(match['eventid']), '?url=', quote(path), '">Make rated</a>'))
						if match['eventtime'] != date:
							tourneyinfo.extend((' ', ftime(match['eventtime'])))
						tourneyinfo.append('</div>')
					#tourneyinfo.append(''.join('<a href="', webloc, '/player/%(winnerid)i">', escape(match['winner']), '</a> (%(winnerelo)i, %(winnergain)+i) beat <a href="', webloc, '/player/%(loserid)i">', escape(match['loser']), '</a> (%(loserelo)i, %(losergain)+i) %(wins)i-%(losses)i<br />') % match)
					tourneyinfo.extend(('<a href="', webloc, '/player/', str(match['winnerid']), '">', escape(match['winner']), '</a> (', str(match['winnerelo']), ', ' , str(match['winnergain']) if match['rated'] != 0 else 'unrated', ') beat <a href="', webloc, '/player/', str(match['loserid']), '">', escape(match['loser']), '</a> (', str(match['loserelo']), ', ' , str(match['losergain']) if match['rated'] != 0 else 'unrated', ') ', str(match['wins']), '-', str(match['losses']), '<br />'))
				tourneyinfo.append('<br /><br />')
				output += ''.join(tourneyinfo)
		if output == '':
			output = 'Tournament not found.'
	elif path.startswith('/modify/'):
		#/modify/evt|trn/id/field/value?url=redirect
		#if url isn't specified, treat as ajax request
		params = path.split('/')
		if len(params) == 6:
			values = {'type': params[2], 'id': params[3], 'field': params[4], 'value': params[5]}
			if values['type'] == 'evt':
				if values['field'] == 'name':
					pass
				elif values['field'] == 'game':
					pass
				elif values['field'] == 'category':
					pass
			elif values['type'] == 'trn':
				pass
			if 'url' in query:
				redirect = url
				output = 'Returning to previous page'
			else:
				output = '1'
				header = ''
				page = '%s'
				addtimer = False
		else:
			output = 'Invalid request.'
	elif path.startswith('/rate/'):
		eventid = path.split('/')[2]
		eventrated = conn.execute('SELECT rated FROM event WHERE eventid=?', (eventid,)).fetchone()
		if eventrated is not None and eventrated['rated'] == 0:
			output = 'Updated ' + str(conn.execute('UPDATE match SET rated=1 WHERE eventid=?', (eventid,)).rowcount) + ' matches. <br />'
			output += 'Now rating ' + str(conn.execute('UPDATE event SET rated=1 WHERE eventid=?', (eventid,)).rowcount) + ' events.'
			conn.commit()
		else:
			output = 'Event does not exist or already rated.'
		if 'url' in query:
			redirect = webloc + query['url'][0]
	elif path == '/rateall':
		#debug
		output = 'Updated ' + str(conn.execute('UPDATE match SET rated=1').rowcount) + ' matches. <br />'
		output += 'Now rating ' + str(conn.execute('UPDATE event SET rated=1').rowcount) + ' events.'
	elif path.startswith('/player/'):
		playerid = path.split('/')[2]
		gameid = None
		rows = []
		if playerid.isdigit():
			playerids = path.split('/')[2:]
			rows = conn.execute('SELECT * FROM player JOIN game ON player.gameid = game.gameid WHERE playerid in (%s)' % ', '.join('?' for unused in playerids), playerids)
		elif playerid.isalnum():
			if path.count('/') > 2:
				gameid = path.split('/')[3]
				rows = conn.execute('SELECT * FROM player WHERE nickname=? AND gameid=?', (playerid, gameid))
			else:
				redirect = webloc + '/psearch?player=' + playerid
		output = ''
		for row in rows:
			playerinfo = []
			playerid = row['playerid']
			playerinfo.extend((row['nickname'], ' (', str(row['currentelo']), ')<br />', row['name'], ' - ', row['category'], '<br />'))
			matches = conn.execute('SELECT winner.nickname AS winner, loser.nickname AS loser, wins, losses, event.timestamp, tournament.name, event.name, match.round, game.name, winnerid, loserid, match.tournamentid AS tourneyid, winnerelo, winnergain, loserelo, losergain FROM match JOIN game ON match.gameid = game.gameid JOIN player AS winner ON match.winnerid = winner.playerid JOIN player AS loser ON match.loserid = loser.playerid JOIN event ON match.eventid = event.eventid JOIN tournament ON match.tournamentid = tournament.tournamentid WHERE winnerid=? OR loserid=? ORDER BY event.timestamp DESC, event.orderstamp DESC', (playerid, playerid))
			lasttime = None
			for match in matches:
				currenttime = ('<br />On ', time.strftime('%b %d, %Y', time.gmtime(match[4])), ' at <a href="', webloc, '/tournament/', str(match['tourneyid']), '">', escape(match[5]), '</a> during ', escape(match[6]), '<br />')
				if currenttime != lasttime:
					lasttime = currenttime
					playerinfo.extend(currenttime)
				if (match['winner'] == row['nickname']):
					playerinfo.extend(('Defeated <a href="', webloc, '/player/', str(match['loserid']), '">', escape(match['loser']), '</a> (', str(match['loserelo']), ')'))
				else:
					playerinfo.extend(('Lost to <a href="', webloc, '/player/', str(match['winnerid']), '">', escape(match['winner']), '</a> (', str(match['winnerelo']), ')'))
				if (match['losses'] != 0):
					playerinfo.extend((' ', str(match['wins']), '-', str(match['losses'])))
				playerinfo.extend((' round ', str(match['round'])))
				if (match['winner'] == row['nickname']):
					playerinfo.extend((' (', str(match['winnerelo']), ', ', str(match['winnergain']), ')<br />'))
				else:
					playerinfo.extend((' (', str(match['loserelo']), ', ', str(match['losergain']), ')<br />'))
			output += ''.join(playerinfo) + '<br /><br />'
		if output == '':
			output = 'Player not found.'
	elif path == '/psearch':
		gameid = None
		if 'game' in query:
			gameid = query['game']
		if 'player' in query:
			name = query['player'][0]
			if gameid is None:
				rows = conn.execute('SELECT playerid, nickname FROM player WHERE nickname REGEXP ?', ('\\b' + name + '\\b',))
				redirect = webloc + '/player'
				found = 0
				nickname = None
				output = 'Redirecting.'
				for row in rows:
					if nickname == None:
						nickname = row['nickname']
					found += 1
					redirect += '/' + str(row['playerid'])
					if row['nickname'] != nickname:
						found = 0
						break
				if found == 0:
					output = 'Player not found, or more than one match.'
					redirect = webloc + '/players?name=' + quote(name)
				else:
					output = redirect
			else:
				output = 'Search by game'
				redirect = webloc + '/players?name=' + quote(name)
		else:
			output = 'Player not specified.'
			redirect = webloc + '/players'
	elif path == '/psauto':
		output = ''
		header = ''
		page = '%s'
		addtimer = False
		if 'val' in query:
			if 'gameid' in query:
				row = conn.execute('SELECT nickname, playerid FROM player WHERE gameid=? AND startswith(nickname, ?) ORDER BY length(nickname) ASC, nickname ASC', (int(query['gameid'][0]), query['val'][0])).fetchone()
			else:
				row = conn.execute('SELECT nickname, playerid FROM player WHERE startswith(nickname, ?) ORDER BY length(nickname) ASC, nickname ASC', (query['val'][0],)).fetchone()
			if row is not None:
				output = json.dumps({'id': query['id'][0], 'msg': row['nickname'], 'playerid': row['playerid']})
	elif path == '/modgamefetch':
		output = ''
		header = ''
		page = '%s'
		addtimer = False
		if 'val' in query:
			if 'gameid' in query:
				row = conn.execute('SELECT nickname, playerid FROM player WHERE gameid=? AND startswith(nickname, ?) ORDER BY length(nickname) ASC, nickname ASC', (int(query['gameid'][0]), query['val'][0])).fetchone()
				if row is not None:
					output = json.dumps({'id': query['id'][0], 'msg': row['nickname'], 'playerid': row['playerid']})
			else:
				row = conn.execute('SELECT nickname, playerid, commaseparate(gameid) AS gameids, commaseparate(name + \' - \' + category) AS games FROM player JOIN game ON player.gameid = game.gameid WHERE startswith(nickname, ?) ORDER BY length(nickname) ASC, nickname ASC', (query['val'][0],)).fetchone()
				if row is not None:
					output = json.dumps({'id': query['id'][0], 'msg': row['nickname'], 'playerid': row['playerid'], 'games': row['games']})
	elif path == '/tsearch':
		if 'tournament' in query:
			rows = conn.execute('SELECT tournamentid FROM tournament WHERE name = ?', (query['tournament'][0],))
			row = rows.fetchone()
			if row is not None and rows.fetchone() is None:
				#originally
				#results = []
				#results.append(str(row['tournamentid']))
				#for row in rows:
				#	results.append(str(row['tournamentid']))
				#redirect = webloc + '/tournament/' + '/'.join(results)
				redirect = webloc + '/tournament/' + str(row['tournamentid'])
			else:
				redirect = webloc + '/tournaments?name=' + quote(query['tournament'][0])
		else:
			redirect = webloc + '/tournaments'
		output = 'Processing search.'
	elif path == '/tsajax':
		output = '[]'
		header = ''
		page = '%s'
		addtimer = False
		rows = tsearch(query['name'][0] if 'name' in query else None, query['region'][0] if 'region' in query else None, query['date'][0] if 'date' in query else None, query['game'][0] if 'game' in query else None, query['type'][0] if 'type' in query else None, query['rated'][0] == 'true' if 'rated' in query else True)
		rowslist = []
		if 'id' in query:
			rowslist.append(query['id'][0])
		for row in rows:
			rowdict = {}
			rowdict['id'] = row['tournamentid']
			rowdict['name'] = row['name']
			rowdict['date'] = ftime(row['timestamp'])
			rowslist.append(rowdict)
		output = json.dumps(rowslist, separators=(',', ':'))
	elif path == '/psajax':
		output = '[]'
		header = ''
		page = '%s'
		addtimer = False
		rows = psearch(query['name'][0] if 'name' in query else None, query['region'][0] if 'region' in query else None, query['character'][0] if 'character' in query else None, query['game'][0] if 'game' in query else None, query['type'][0] if 'type' in query else None, query['rating'][0] if 'rating' in query else None)
		rowslist = []
		if 'id' in query:
			rowslist.append(query['id'][0])
		for row in rows:
			rowdict = {}
			rowdict['ids'] = row['ids']
			rowdict['nickname'] = row['nickname']
			rowdict['names'] = row['names']
			rowslist.append(rowdict)
		output = json.dumps(rowslist, separators=(',', ':'))
	else:
		#if the page was not a content page, open the index
		#TODO: 404
		output = open(content + 'index.htm', 'r').read() + '<br />'
		recenttournaments = []
		rows = conn.execute('SELECT * FROM tournament ORDER BY timestamp DESC LIMIT 7')
		for row in rows:
			recenttournaments.extend(('<li><a href="', webloc, '/tournament/', str(row['tournamentid']), '">', escape(row['name']), '</a> on ', ftime(row['timestamp']), '</li>'))
		output = output.replace('<recent />', ''.join(recenttournaments))
	end = time.clock() #times page generation time
	if addtimer:
		output += '<div id="timer">Page generated in ' + str(end - start) + ' seconds.</div>'
	output = (page % header + output).encode('utf-8') #make sure everything is utf-8 encoded before sending
	response_headers = [('Content-type', 'text/html; charset=utf-8'),
						('Content-Length', str(len(output)))]
	if redirect is not None:
		status = '303 See Other'
		response_headers.append(('Location', redirect))
	#cookiedata stores data about setting values to the client's cookie, dump that into the response headers
	for item in cookiedata.items():
		response_headers.append(('Set-Cookie', item[0] + '=' + item[1].value))
	start_response(status, response_headers)
	return [output]

def reprocessratings(gameids=[], startdate=0):
	players = {}
	updated = {}
	group = [1]
	groupcursor = 1
	eventid = None
	defaultelo = 1200 #make alorithm later?
	processed = [] #(winnerelo, winnergain, loserelo, losergain, matchid)
	tournaments = []
	appendresult = processed.append
	
	def pushmatch(match):
		if group[0] == len(group):
			group.append(match)
		else:
			group[group[0]] = match
		group[0] += 1
	
	def makeplayer(id):
		players[id] = defaultelo
	
	def processmatch(match, gaininto):
		rA = players[match['winnerid']]
		rB = players[match['loserid']]
		qA = 10.0 * rA / 400.0
		qB = 10.0 * rB / 400.0
		eA = qA / (qA + qB)
		eB = qB / (qA + qB)
		if rA < 2100:
			kA = 32.0
		elif rA <= 2400:
			kA = 24
		else:
			kA = 16
		if rB < 2100:
			kB = 32.0
		elif rB <= 2400:
			kB = 24
		else:
			kB = 16
		
		if match['wins'] == match['losses']:
			sA = 0.5
			sB = 0.5
		else:
			sA = 1
			sB = 0
		gA = kA * (sA - eA)
		gB = kB * (sB - eB)
		
		processed.append((rA, gA, rB, gB, match['matchid']))
		gaininto[match['winnerid']] += gA
		gaininto[match['loserid']] += gB
	
	def processgroup():
		if group[0] == 2:
			processmatch(group[1], players)
		else:
			gains = {}
			for match in (group[i] for i in xrange(1, group[0])):
				if match['winnerid'] not in gains:
					gains[match['winnerid']] = 0
				if match['loserid'] not in gains:
					gains[match['loserid']] = 0
				processmatch(match, gains)
			for item in gains.iteritems():
				players[item[0]] += item[1]
		group[0] = 1
	
	if len(gameids) == 0 or len(gameids[0]) == 0:
		gameids = []
		for game in conn.execute('SELECT gameid FROM game'):
			gameids.append(int(game['gameid']))
	else:
		for index in xrange(0, len(gameids)):
			gameids[index] = int(gameids[index])
	
	for gameid in gameids:
		matches = conn.execute('SELECT match.tournamentid, matchid, match.eventid AS eventid, round, orderstamp, matchorder, timestamp, winnerid, loserid, wins, losses, winnerelo, loserelo, winnergain, losergain FROM match JOIN event ON match.eventid=event.eventid WHERE match.gameid=? AND match.rated=1 ORDER BY timestamp ASC, orderstamp ASC, matchorder ASC', (gameid,))
		if startdate > 0:
			for match in matches:
				if match.timestamp >= startdate:
					pushmatch(match)
					order = match['matchorder']
					eventid = match['eventid']
					break
				else:
					players[match['winnerid']] = match['winnerelo'] + match['winnergain']
					players[match['loserid']] = match['loserelo'] + match['losergain']
		
		for match in matches:
			if str(match['tournamentid']) not in tournaments:
				tournaments.append(str(match['tournamentid']))
			if match['winnerid'] not in players:
				makeplayer(match['winnerid'])
			if match['loserid'] not in players:
				makeplayer(match['loserid'])
			
			if match['winnerid'] not in updated or updated[match['winnerid']] < match['timestamp']:
				updated[match['winnerid']] = match['timestamp']
			if match['loserid'] not in updated or updated[match['loserid']] < match['timestamp']:
				updated[match['loserid']] = match['timestamp']
			
			if match['eventid'] != eventid:
				#new event
				processgroup()
				pushmatch(match)
				eventid = match['eventid']
			elif match['matchorder'] != order:
				#different match by order, same event
				processgroup()
				pushmatch(match)
			else:
				#same event, same order; concurrent match calculation needed
				pushmatch(match)
			order = match['matchorder']
		processgroup()
	matchcursor = conn.executemany('UPDATE match SET winnerelo=?, winnergain=?, loserelo=?, losergain=? WHERE matchid=?', processed)
	playercursor = conn.executemany('UPDATE player SET currentelo=?, lastchanged=? WHERE playerid=?', ((players[item[0]], item[1], item[0]) for item in players.iteritems()))
	conn.commit()
	return ('Modified: %i<br />' % len(processed)) + '<br />'.join(tournaments)

def makesession(userid, rememberme, cookie):
	#performs the entire operation necessary to give the client a session cookie
	session = sessionid()
	conn.execute('UPDATE user SET lastactive=now() WHERE userid=?', (userid,))
	conn.execute('INSERT INTO usersession (userid, token, created, expires) VALUES (?, totoken(?), ?, ?)', (userid, session, now(), now() + snduration))
	conn.commit()
	cookie['session'] = session
	cookie['session'].clear() #if there was an expiration, make sure it's removed
	cookie['session']['HttpOnly'] = True
	cookie['session']['path'] = '/'
	if rememberme:
		cookie['session']['expires'] = snduration

def registeruser(username, password, cookie, nickname=None):
	#performs a couple checks, then registers the user and returns a related message for the client
	if len(username) > 0 and len(password) > 0 and conn.execute('SELECT userid FROM user WHERE username=?', (username,)).fetchone() is None:
		cursor = conn.execute('INSERT INTO user (username, pwhash, pwreps, created) VALUES (?, passhash(?, ?), ?, now())', (username, password, pwrepetitions, pwrepetitions))
		conn.commit()
		makesession(cursor.lastrowid, True, cookie)
		return 'Thanks for registering, ' + username + '!'
	else:
		return 'Error registering. Username or password may be too short, or username may be taken.'

def processupload(uploaded, filename, userid, cookiedata):
	#hopefully validates the file to be a proper .tio file, saves it to disk, then loads it
	#later, may determine type of file (lite json data version, universal tournament save data, whatever else) and perform related operations to load
	format = None
	processed = uploaded
	fn = os.path.basename(filename)
	if os.path.splitext(fn)[1] == '.gz':
		#if it's a .gz, try to use gzip
		try:
			processed = gzip.GzipFile(fileobj=processed, mode='rb')
			fn = os.path.splitext(fn)[0]
		except:
			return 'Could not extract .gz file.'
	if os.path.splitext(fn)[1] == '.tio':
		try:
			tree = ET.ElementTree(file=processed)
			root = tree.getroot()
			if root.tag == 'AppData' and root.find('EventList/Event/Games'):
				processed.seek(0)
				format = 'tio'
		except Exception as error:
			format = pformat(error)
		else:
			if format == 'tio':
				return loadFromTio(processed, os.path.basename(fn), userid, cookiedata)
		return 'Unknown file format provided. ' + format
	return 'Unknown error.'

def loadFromTio(uploaded, filename, userid, cookiedata):
	#temp: returns debug string of tournament representation
	#TODO: enters tournament data into database, returns tournament ID
	#does not commit to database
	STARTING_ELO = 1200
	tree = ET.ElementTree(file=uploaded)
	root = tree.getroot()
	#output = []
	savedata = {} #this is used for the lite json data version
	savedata['events'] = []
	matches = {} #dict of lists of tuples, one list per game, one tuple per match
	#match: (eventindex, matchindex, gameid, winner, loser, round, wins1, wins2)
	games = []
	matchindex = {} #dict of integers
	bracketStart = 0
	players = {} #key: identifier; value: player nickname
	byes = [] #stores identifiers of bye players, since IDs seems to vary from file to file
	playerIndex = [] #stores ordered player list, for use in lite json data version
	playerReference = {} #reverse-lookup of the player index, used for building lite json data version
	playerReference['Bye'] = -1
	playercache = {} #key: (player identifier, gameid) value: userid
	savedata['players'] = playerIndex
	tournament = root.find('EventList/Event')
	events = [] #stores tuples of data about events for database storage: (name, index, gameid, timestamp, order)
	playerdata = [] #stores tuples of data about players to be stored in the database (nickname, gameid)
	playerattr = [] #stores tuple of extra attributes to add to players (name, gameid, key, value)
	teamcomps = {}
	name = tournament.findtext('Name')
	try:
		date = calendar.timegm(time.strptime(tournament.findtext('StartDate'), '%m/%d/%Y %I:%M:%S %p'))
	except ValueError:
		try:
			date = calendar.timegm(time.strptime(tournament.findtext('StartDate'), '%m/%d/%Y %H:%M:%S'))
		except:
			date = now()
	organizer = tournament.findtext('Organizer')
	location = tournament.findtext('Location')
	regions = []
	gamenames = {}
	mostcommongame = 'Super Smash Bros. Melee'
	highestn = 0
	for gamename in tree.getiterator(tag='GameName'):
		if re.match('\w', gamename.text) is not None:
			if gamename.text not in gamenames:
				gamenames[gamename.text] = 1
			else:
				gamenames[gamename.text] += 1
	for gamename in gamenames:
		if gamenames[gamename] > highestn:
			mostcommongame = gamename
	
	#load the list of players' names
	#in the .tio format, players are referenced by a GUID
	if root.find('PlayerList/Players') is not None:
		for player in root.find('PlayerList/Players').getiterator('Player'):
			players[player.findtext('ID')] = player.findtext('Nickname')
			playerReference[player.findtext('Nickname')] = len(playerIndex)
			playerIndex.append(player.findtext('Nickname'))
	if root.find('PlayerList/Teams') is not None:
		for team in root.find('PlayerList/Teams').getiterator('Team'):
			rawplayers = None
			members = []
			nickname = team.findtext('Nickname')
			if re.search('\w', team.findtext('Players')):
				rawplayers = team.findtext('Players')
			else:
				#sometimes, people enter names as the nickname instead of a team name
				if team.findtext('Nickname').count('+') > 0 or team.findtext('Nickname').count('&') > 0:
					#only use the nickname as the player list if it looks like a player list
					rawplayers = team.findtext('Nickname')
			if rawplayers is not None:
				if rawplayers.count('+') == 0 and rawplayers.count('&') > 0:
					rawplayers = rawplayers.replace('&', '+')
				#sort alphabetically so the same player composition will always have the same name
				for member in rawplayers.split('+'):
					members.append(member.strip(' '))
				members.sort(cmp=lambda x, y: cmp(x.lower(), y.lower()))
				savename = ' + '.join(members)
				teamcomps[savename] = members
			else:
				#if they didn't specify the players in the team, just use the nickname
				savename = team.findtext('Nickname')
			players[team.findtext('ID')] = savename
			playerReference[savename] = len(playerIndex)
			playerIndex.append(savename)

	eventindex = 0
	for game in tournament.find('Games').getiterator('Game'):
		#in the .tio format, a "game" is an event, for instance: Melee Singles.
		#output.append('<br />' + game.findtext('Name'))
		gamename = game.findtext('GameName')
		gametype = game.findtext('GameType')
		size = int(game.findtext('Bracket/Size'))
		if re.match('\w', gamename) is None:
			gamename = mostcommongame
		gamedata = conn.execute('SELECT gameid FROM game WHERE name=? AND category=?', (gamename, gametype)).fetchone()
		if gamedata is None:
			cursor = conn.execute('INSERT INTO game (name, category) VALUES (?, ?)', (gamename, gametype))
			gameid = cursor.lastrowid
		else:
			gameid = gamedata['gameid']
		if gameid not in matches:
			games.append(gameid)
			matches[gameid] = []
			matchindex[gameid] = 0
		matchnumber = 0
		try:
			evtdate = calendar.timegm(time.strptime(game.findtext('Date'), '%m/%d/%Y %I:%M:%S %p'))
		except ValueError:
			try:
				evtdate = calendar.timegm(time.strptime(game.findtext('Date'), '%m/%d/%Y %H:%M:%S'))
			except:
				evtdate = now()
		events.append([game.findtext('Name'), gameid, evtdate, eventindex])
		#for entrant in game.find('Entrants').getiterator('PlayerID'):
		#	if (players[entrant.text], gameid) not in playercache:
		#		playerrow = conn.execute('SELECT playerid, regionid, gameid FROM player WHERE nickname=? AND gameid=?', (players[entrant.text], gameid)).fetchone()
		#		if playerrow is None:
		#			#cursor = conn.execute('INSERT INTO player (nickname, gameid) VALUES (?, ?)', (players[entrant.text], gameid))
		#			player = (players[entrant.text], gameid)
		#			playerdata.append(player)
		#			playercache[player] = None
		#		else:
		#			if playerrow['regionid'] != -1:
		#				regions.append(playerrow['regionid'])
		#			playercache[(players[entrant.text], gameid)] = playerrow['playerid']
		event = {}
		event['name'] = game.findtext('Name')
		event['bracket'] = {}
		entrants = []
		event['bracket']['entrants'] = entrants
		progress = []
		event['bracket']['progress'] = progress
		championship = -1
		championshipmatch = False
		secondchamp = False
		savedata['events'].append(event)
		if game.findtext('BracketType') == 'RoundRobin': #round robin/pools
			event['bracket']['type'] = 2
			#fill the entrants and progress lists with lists to store data for each pool
			for unused in xrange(0, size):
				entrants.append([])
				progress.append([])
			for pool in game.findall('Bracket/Pools/Pool'):
				number = int(pool.findtext('Number'))
				aprogress = progress[number]
				#output.append('Pool ' + str(number))
				for player in pool.findall('Players/PlayerID'):
					if player.text not in byes and (players[player.text], gameid) not in playercache:
						playerrow = conn.execute('SELECT playerid, regionid, gameid FROM player WHERE nickname=? AND gameid=?', (players[player.text], gameid)).fetchone()
						if playerrow is None:
							playerd = (players[player.text], gameid)
							playerdata.append(playerd)
							playercache[playerd] = None
						else:
							if playerrow['regionid'] != -1:
								regions.append(playerrow['regionid'])
							playercache[(players[player.text], gameid)] = playerrow['playerid']
					entrants[number].append(playerReference[players[player.text]])
				poolsize = len(entrants[number])
				tri = []
				n = 0
				for i in xrange(0, poolsize):
					n += i
					tri.append(n)
				#fill the pool's progress with unrecorded matches
				for unused in xrange(0, tri[poolsize - 1] + poolsize - 1):
					aprogress.append(0)
				for match in pool.getiterator('Match'):
					p1i = playerReference[players[match.findtext('Player1')]]
					p2i = playerReference[players[match.findtext('Player2')]]
					p1n = -1
					p2n = -1
					if p1i in entrants[number] and p2i in entrants[number]:
						p1n = entrants[number].index(p1i)
						p2n = entrants[number].index(p2i)
						if p1n < p2n:
							index = p1n + tri[p2n - 1]
						else:
							index = p2n + tri[p1n - 1]
					if match.findtext('Player1') not in players:
						players[match.findtext('Player1')] = 'Bye'
						byes.append(match.findtext('Player1'));
					if match.findtext('Player2') not in players:
						players[match.findtext('Player2')] = 'Bye'
						byes.append(match.findtext('Player2'));
					if match.findtext('Player1') not in byes and (players[match.findtext('Player1')], gameid) not in playercache:
						playerrow = conn.execute('SELECT playerid, regionid, gameid FROM player WHERE nickname=? AND gameid=?', (players[match.findtext('Player1')], gameid)).fetchone()
						if playerrow is None:
							player = (players[match.findtext('Player1')], gameid)
							playerdata.append(player)
							playercache[player] = None
						else:
							if playerrow['regionid'] != -1:
								regions.append(playerrow['regionid'])
							playercache[(players[match.findtext('Player1')], gameid)] = playerrow['playerid']
					if match.findtext('Player2') not in byes and (players[match.findtext('Player2')], gameid) not in playercache:
						playerrow = conn.execute('SELECT playerid, regionid, gameid FROM player WHERE nickname=? AND gameid=?', (players[match.findtext('Player2')], gameid)).fetchone()
						if playerrow is None:
							player = (players[match.findtext('Player2')], gameid)
							playerdata.append(player)
							playercache[player] = None
						else:
							if playerrow['regionid'] != -1:
								regions.append(playerrow['regionid'])
							playercache[(players[match.findtext('Player2')], gameid)] = playerrow['playerid']
					wongames = int(match.findtext('Games')) / 2 + 1
					if match.findtext('Winner') == match.findtext('Player1'):
						#player 1 won
						if match.findtext('Player1') not in byes and match.findtext('Player2') not in byes:
							aprogress[index] = (wongames, int(match.findtext('Losses')))
							matches[gameid].append((eventindex, matchindex[gameid], matchnumber, gameid, players[match.findtext('Player1')], players[match.findtext('Player2')], number, wongames, int(match.findtext('Losses'))))
						#output.append(players[match.findtext('Player1')] + ' beat ' + players[match.findtext('Player2')] + ' ' + str(wongames) + '-' + match.findtext('Losses'))
					else:
						#player 2 won
						if match.findtext('Player1') not in byes and match.findtext('Player2') not in byes:
							aprogress[index] = (wongames, int(match.findtext('Losses')))
							#progress.append(int(match.findtext('Losses')))
							matches[gameid].append((eventindex, matchindex[gameid], matchnumber, gameid, players[match.findtext('Player2')], players[match.findtext('Player1')], number, wongames, int(match.findtext('Losses'))))
						#output.append(players[match.findtext('Player2')] + ' beat ' + players[match.findtext('Player1')] + ' ' + str(wongames) + '-' + match.findtext('Losses'))
			matchindex[gameid] += 1
		else: #bracket
			if game.findtext('BracketType') == 'SingleElim':
				event['bracket']['type'] = 0
			elif game.findtext('BracketType') == 'DoubleElim':
				event['bracket']['type'] = 1
			for match in game.getiterator('Match'):
				if match.findtext('Round') is not None:
					round = int(match.findtext('Round'))
				else:
					#.tio doesn't store round numbers for single elimination...
					number = int(match.findtext('Number')) + 1
					hsize = size
					round = 0
					while number > 0:
						hsize /= 2
						number -= hsize
						round += 1
				if match.findtext('Player1') not in players:
					players[match.findtext('Player1')] = 'Bye'
					byes.append(match.findtext('Player1'));
				if match.findtext('Player2') not in players:
					players[match.findtext('Player2')] = 'Bye'
					byes.append(match.findtext('Player2'));
				if round == 1:
					entrants.append(playerReference[players[match.findtext('Player1')]])
					entrants.append(playerReference[players[match.findtext('Player2')]])
					if match.findtext('Player1') not in byes and (players[match.findtext('Player1')], gameid) not in playercache:
						playerrow = conn.execute('SELECT playerid, regionid, gameid FROM player WHERE nickname=? AND gameid=?', (players[match.findtext('Player1')], gameid)).fetchone()
						if playerrow is None:
							player = (players[match.findtext('Player1')], gameid)
							playerdata.append(player)
							playercache[player] = None
						else:
							if playerrow['regionid'] != -1:
								regions.append(playerrow['regionid'])
							playercache[(players[match.findtext('Player1')], gameid)] = playerrow['playerid']
					if match.findtext('Player2') not in byes and (players[match.findtext('Player2')], gameid) not in playercache:
						playerrow = conn.execute('SELECT playerid, regionid, gameid FROM player WHERE nickname=? AND gameid=?', (players[match.findtext('Player2')], gameid)).fetchone()
						if playerrow is None:
							player = (players[match.findtext('Player2')], gameid)
							playerdata.append(player)
							playercache[player] = None
						else:
							if playerrow['regionid'] != -1:
								regions.append(playerrow['regionid'])
							playercache[(players[match.findtext('Player2')], gameid)] = playerrow['playerid']
				wongames = int(match.findtext('Games')) / 2 + 1
				if match.findtext('Winner') in byes:
					if match.findtext('IsChampionship') == 'True':
						championship = -1
					event['bracket']['progress'].append(-1)
				elif match.findtext('Winner') == match.findtext('Player1'):
					#player 1 won
					if match.findtext('IsChampionship') == 'True':
						championship = 0
						if match.findtext('Player1') not in byes and match.findtext('Player2') not in byes:
							championshipmatch = (eventindex, matchindex[gameid], matchnumber, gameid, players[match.findtext('Player1')], players[match.findtext('Player2')], round, wongames, int(match.findtext('Losses')))
					else:
						event['bracket']['progress'].append(0)
						if match.findtext('Player1') not in byes and match.findtext('Player2') not in byes:
							matches[gameid].append((eventindex, matchindex[gameid], matchnumber, gameid, players[match.findtext('Player1')], players[match.findtext('Player2')], round, wongames, int(match.findtext('Losses'))))
							matchindex[gameid] += 1
							matchnumber += 1
					#output.append(players[match.findtext('Player1')] + ' beat ' + players[match.findtext('Player2')] + ' r' + str(round) + ' ' + str(wongames) + '-' + match.findtext('Losses'))
				else:
					#player 2 won
					if match.findtext('IsChampionship') == 'True':
						championship = 1
						if match.findtext('Player1') not in byes and match.findtext('Player2') not in byes:
							championshipmatch = (eventindex, matchindex[gameid], matchnumber, gameid, players[match.findtext('Player2')], players[match.findtext('Player1')], round, wongames, int(match.findtext('Losses')))
					else:
						event['bracket']['progress'].append(1)
						if match.findtext('Player1') not in byes and match.findtext('Player2') not in byes:
							matches[gameid].append((eventindex, matchindex[gameid], matchnumber, gameid, players[match.findtext('Player2')], players[match.findtext('Player1')], round, wongames, int(match.findtext('Losses'))))
							matchindex[gameid] += 1
							matchnumber += 1
					#output.append(players[match.findtext('Player2')] + ' beat ' + players[match.findtext('Player1')] + ' r' + str(round) + ' ' + str(wongames) + '-' + match.findtext('Losses'))
				if match.findtext('IsSecondChampionship') == 'True':
					if match.findtext('Winner') in byes or match.findtext('Player1') in byes or match.findtext('Player2') in byes:
						secondchamp = -1
						progress[len(progress) - 1] = -1
					else:
						if progress[len(progress) - 1] == 0:
							progress[len(progress) - 1] = 1
							secondchamp = 1
						else:
							progress[len(progress) - 1] = 0
							secondchamp = 0
					event['bracket']['progress'].append(event['bracket']['progress'][len(event['bracket']['progress']) - 1])
					event['bracket']['progress'][len(event['bracket']['progress']) - 2] = championship
					if secondchamp != -1 and championshipmatch != False:
						a, b, c, d, e, f, g, h, i = matches[gameid][len(matches[gameid]) - 1]
						matches[gameid][len(matches[gameid]) - 1] = (a, b + 1, c + 1, d, e, f, g, h, i)
						matches[gameid].append(matches[gameid][len(matches[gameid]) - 1])
						a, b, c, d, e, f, g, h, i = championshipmatch
						championshipmatch = (a, matchindex[gameid] - 1, matchnumber - 1, d, e, f, g, h, i)
						matches[gameid][len(matches[gameid]) - 2] = championshipmatch
					elif championshipmatch != False:
						championshipmatch = (championshipmatch[0], matchindex[gameid], matchnumber, championshipmatch[3], championshipmatch[4], championshipmatch[5], championshipmatch[6], championshipmatch[7], championshipmatch[8])
						matches[gameid].append(championshipmatch)
			if championship is False:
				event['bracket']['progress'].append(championship)
				matches[gameid].append(championshipmatch)
		eventindex += 1
	#for game in games:
	#	for match in matches[game]:
	#		output.append(pformat(match))
	#for event in events:
	#	output.append(pformat(event))
	#for player in playerdata:
	#	output.append(pformat(player))
	#done processing, save data to database
	jsondata = json.dumps(savedata, separators=(',', ':'))
	diskfilename = str(now()) + os.path.basename(filename) + '.gz'
	tournamentcursor = conn.execute('INSERT INTO tournament (name, timestamp, timeprocessed, uploaderid, original, jsondata) VALUES (?, ?, now(), ?, ?, ?)', (name, date, userid, diskfilename, jsondata))
	tournamentid = tournamentcursor.lastrowid
	#prepare event data for saving
	saveevents = []
	for event in events:
		event.insert(0, tournamentid) #add the tournament ID to the event data
		cursor = conn.execute('INSERT INTO event (tournamentid, name, gameid, timestamp, orderstamp) VALUES (?, ?, ?, ?, ?)', event)
		event.insert(0, cursor.lastrowid) #add the event ID to the event data
		#saveevents.append(tournamentid, event[0], event[1], event[2], event[3])
	for player in playerdata:
		#any players that weren't already in the database get added here and their IDs are cached
		cursor = conn.execute('INSERT INTO player (nickname, gameid) VALUES (?, ?)', player)
		playercache[player] = cursor.lastrowid
	#conn.executemany('INSERT INTO player (nickname, gameid) VALUES (?, ?)', playerdata)
	savematches = []
	for game in games:
		for match in matches[game]:
			if (match[4], match[3]) in playercache and (match[5], match[3]) in playercache:
				#savematches.append((match[3], tournamentid, events[match[0]][0], match[6], match[1], match[2], playercache[(match[4], match[3])], playercache[(match[5], match[3])], match[7], match[8]))
				savematches.append((match[3], tournamentid, events[match[0]][0], match[6], match[2], playercache[(match[4], match[3])], playercache[(match[5], match[3])], match[7], match[8]))
	#conn.executemany('INSERT INTO match (gameid, tournamentid, eventid, round, tournamentorder, matchorder, winnerid, loserid, wins, losses) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', savematches)
	conn.executemany('INSERT INTO match (gameid, tournamentid, eventid, round, matchorder, winnerid, loserid, wins, losses) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', savematches)
	#save backup file
	uploaded.seek(0)
	backup = gzip.open(tiostore + diskfilename, 'wb')
	backup.write(uploaded.read())
	backup.close()
	return tournamentid
	#return '<br />'.join(output) + '<br />' + jsondata + '<br /><div class="bracket" style="width: 100%; overflow: hidden; cursor: move" data-tournament=\'' + jsondata.replace('\'', '&apos;') + '\'></div>'
