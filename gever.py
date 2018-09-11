import time
import os
import spotipy
from spotipy.util import prompt_for_user_token
from slackclient import SlackClient


# Obtain here https://api.slack.com/
SLACK_API = "YOUR_SLACK_API" # Looks like 'xoxb-303732729214-DXNVlObzNU4s9tv01eoOefVj'


# Obtain here: https://developer.spotify.com/documentation/general/guides/app-settings/#register-your-app
SPOTIFY_CLIENT_ID = 'YOUR_SPOTIFY_CLIENT_ID' #Looks like '1735b67d768e48a2ac0df711a601a05f'
SPOTIFY_CLIENT_SECRET = 'SPOTIFY_CLIENT_SECRET' # Same format as above

PLAYLIST_ID = "PLAYLIST_ID" # Looks like '0GP9NFEElh7pqbQoEx5z', Make sure your spotify api key has the right privilages
USERNAME = "OJ" # Just enter your username...

POLL_TIMEOUT = 1

PLAYLIST_URI = "spotify:user:"+USERNAME+":playlist:"+PLAYLIST_ID


POLL_TIMEOUT = 1

slack_client = SlackClient(SLACK_API)
NOT_FOUND_TITLE = "Not found"

RESET_TRACK_ID = "4WenC8xnhFyvARaqeItwqN" # A default track when resetting the playlist

sp_token = None
sp = None

glob_last_track = None

def reset_playlist():
	res = sp.user_playlist_replace_tracks(USERNAME, PLAYLIST_ID, [RESET_TRACK_ID])
	res = sp.pause_playback()
	res = sp.start_playback(context_uri=PLAYLIST_URI)
	
def refresh_spotify_token():
	global sp_token
	global sp
	sp_token = prompt_for_user_token(USERNAME,"playlist-modify-public user-modify-playback-state user-read-playback-state user-read-recently-played user-modify-playback-state") # Your spotify api key need to have all these privilages!
	sp = spotipy.Spotify(auth=sp_token)

def send_msg(txt, chn):
	slack_client.api_call(
		"chat.postMessage",
		channel=chn,
		text=txt)

def print_help(chn):
	help_txt = """
	Hello my name is Gever and my purpose in this cyberspace is to help you manage a collaborative playlist!
	These are the commands I support:

	*add [txt]* : Look for a song and adds it to the playlist
	*help* : Print what you're seeing now...
	*reset* : Reset the managed playlist in case the playback has turned into radio or anything else (Just do this if the playback has run into the void of recommendations) [Basically plays human music]
	*skip* : Skip currently playing track
	*undo* : Remove last added track
	*recommend* : Add 5 random songs based on the style of the last 5 songs in the playlist
	*tail* : Shows the bottom of the playlist
	*current* : Shows the currently playing track
	*recent* : Shows the most recently played songs

"""
	
	send_msg(help_txt, chn)
def get_track_title(track):
	return ', '.join([a['name'] for a in track['artists']]) + " - " + track['name']

def remove_last_song():
	sp.user_playlist_remove_all_occurrences_of_tracks(USERNAME, PLAYLIST_ID, [glob_last_track['id']])

def get_playlist_songids():
	playlist = sp.user_playlist(USERNAME, PLAYLIST_ID, fields="tracks")['tracks']
	tracks = playlist['items']
	while playlist['next']:
		playlist = sp.next(playlist)
		tracks += playlist['items']

	return [t['track']['id'] for t in tracks]

def add_recommended(count):
	tracks = sp.recommendations(seed_tracks=get_playlist_songids()[-count:], limit=count)['tracks']
	results = sp.user_playlist_add_tracks(USERNAME, PLAYLIST_ID, [t['id'] for t in tracks])
	return [get_track_title(t) for t in tracks]


def get_recent_songs():
	last_tracks = sp.current_user_recently_played(limit=5)['items'][::-1]
	desc = '*' + '\n*'.join([get_track_title(track['track']) for track in last_tracks])
	desc += '\n--> *%s' % current_song_title()
	return desc

def get_playlist_tail(count):
	tracks = get_playlist_songids()
	return [get_track_title(sp.track(t)) for t in tracks[-count:]]

def skip_song():
	sp.next_track()

def current_song_title():
	current_song = sp.currently_playing()['item']
	title = get_track_title(current_song)
	return title


def add_song(txt):
	global glob_last_track

	results = sp.search(q=txt, limit=5)
	if len(results['tracks']['items']) < 1:
		return NOT_FOUND_TITLE
	top_track = results['tracks']['items'][0]
	title = get_track_title(top_track)
	results = sp.user_playlist_add_tracks(USERNAME, PLAYLIST_ID, [top_track['id']])
	glob_last_track = top_track

	print("ADD\n====")
	print(results)

	return title

def parse_bot_command(slack_events):
	for event in slack_events:
		if event["type"] == "message" and not "subtype" in event:
			message = event["text"]
			return message, event["channel"]
	return None, None


def handle_command(cmd, chn):
	splitted = cmd.split(" ")

	if splitted[0] == "add":
		title = add_song(" ".join(splitted[1:]))
		if title == NOT_FOUND_TITLE:
			send_msg("Can't find song...", chn)
		else:
			send_msg("Adding " + title, chn)

	elif splitted[0] == "current":
		send_msg("Current song is %s" % current_song_title(), chn)

	elif splitted[0] == "recent":
		send_msg("=====\nLast songs:\n=====\n%s" % get_recent_songs(), chn)

	elif splitted[0] == "tail":
		send_msg("=====\nPlaylist's tail:\n=====\n%s" % '*' + '\n*'.join(get_playlist_tail(10)), chn)

	elif splitted[0] == "recommend":
		titles = add_recommended(5)
		send_msg("Adding 5 recommended songs:\n", chn)
		send_msg("*" + "\n*".join(titles), chn)

	elif splitted[0] == "undo":
		remove_last_song()
		send_msg("Last added track removed...", chn)

	elif splitted[0] == "skip":
		send_msg("Skipping current track...", chn)
		skip_song()

	elif splitted[0] == "reset":
		reset_playlist()

	elif splitted[0] == "help":
		print_help(chn)


def main():
	if not slack_client.rtm_connect():
		print("Can't connect slack client")

	refresh_spotify_token()
	if not sp:
		print("Can't init spotify")

	print("Running!")
	while True:
		time.sleep(POLL_TIMEOUT)
		command, channel = parse_bot_command(slack_client.rtm_read())
		if command:
			try:
				print("Handling %s" % command)
				handle_command(command, channel)
			except spotipy.SpotifyException:
				send_msg("Error, maybe token expired, retrying...", channel)
				refresh_spotify_token()
				# Retry
				try:
					handle_command(command, channel)
				except Exception as e:
					send_msg("Command failed with %s" % e)



main()
