import time
import os
import spotipy
from spotipy.util import prompt_for_user_token
import slack

from configuration import *
#from sa_config import *


POLL_TIMEOUT = 1

PLAYLIST_URI = "spotify:user:"+USERNAME+":playlist:"+PLAYLIST_ID


POLL_TIMEOUT = 1

slack_client = slack.RTMClient(token=SLACK_API)
slack_webclient = slack.WebClient(token=SLACK_API)

NOT_FOUND_TITLE = "Not found"

RESET_TRACK_ID = "4WenC8xnhFyvARaqeItwqN" # A default track when resetting the playlist

sp_token = None
sp = None

glob_last_track = []
glob_search_results = []

def reset_playlist():
	res = sp.user_playlist_replace_tracks(USERNAME, PLAYLIST_ID, [RESET_TRACK_ID])
	try:
		res = sp.pause_playback()
		res = sp.start_playback(context_uri=PLAYLIST_URI)
		return True
	except Exception as e:
		print("Couldn't pause/play , %s" % str(e))
		
	
	
def refresh_spotify_token():
	global sp_token
	global sp
	sp_token = prompt_for_user_token(USERNAME,"playlist-modify-public playlist-modify-private app-remote-control user-read-playback-state user-read-recently-played user-modify-playback-state streaming user-top-read") # Your spotify api key need to have all these privilages!
	sp = spotipy.Spotify(auth=sp_token)

def send_msg(txt, chn):
	slack_webclient.chat_postMessage(
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
	*search [txt]* : Search a song
	*sadd [index]* : Add from search results

"""
	
	send_msg(help_txt, chn)
def get_track_title(track):
	return ', '.join([a['name'] for a in track['artists']]) + " - " + track['name']

def remove_last_song():
	last_track = glob_last_track.pop()
	sp.user_playlist_remove_all_occurrences_of_tracks(USERNAME, PLAYLIST_ID, [last_track['id']])
	

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
	#TODO: mark current song
	tracks = get_playlist_songids()
	return [get_track_title(sp.track(t)) for t in tracks[-count:]]

def skip_song():
	sp.next_track()

def current_song_title():
	current_song = sp.current_playback()
	if not current_song:
		return 'No song is currently playing...'
	
	title = get_track_title(current_song['item'])
	return title


def search_song(q):

	results = sp.search(q=q, type='track', limit=5)
	res = []
	for t in results['tracks']['items']:
		res += [t]
	
	return res
	

def add_song(txt):
	global glob_last_track

	results = sp.search(q=txt, type='track', limit=5)
	
	if len(results['tracks']['items']) < 1:
		return NOT_FOUND_TITLE
		
	
	top_track = results['tracks']['items'][0]
	title = get_track_title(top_track)
	results = sp.user_playlist_add_tracks(USERNAME, PLAYLIST_ID, [top_track['id']])
	glob_last_track += [top_track]

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
			
	if splitted[0] == "search":
		global glob_search_results
		glob_search_results = search_song(" ".join(splitted[1:]))
		index = 0
		for t in glob_search_results:
			index += 1
			send_msg(str(index)+" - "+get_track_title(t), chn)
	
	# Add from search
	if splitted[0] == "sadd" and int(splitted[1]) in range(1,6) and glob_search_results:
		global glob_last_track
		track = glob_search_results[int(splitted[1])-1]
		result = sp.user_playlist_add_tracks(USERNAME, PLAYLIST_ID, [track['id']])
		glob_last_track += [track]

		print("ADD\n====")
		print(result)
		send_msg("Adding " + get_track_title(track), chn)
		
			
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
		if reset_playlist():
			send_msg("Playlist was reset", chn)
		

	elif splitted[0] == "help":
		print_help(chn)


@slack.RTMClient.run_on(event='message')
def onMsg(**payload):
	
	if not ('data' in payload and 'text' in payload['data']):
		return
		
	# TODO: filter self messages 
	
	command = payload['data']['text']
	channel = payload['data']['channel']
	
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
				send_msg("Command failed with %s" % e, channel)



	

def main():

	refresh_spotify_token()
	
	if not sp:
		print("Can't init spotify")

	print("Starting slack client")
	slack_client.start()
	


main()
