# -*- coding:utf-8 -*-

from __future__ import absolute_import

import time
import re
import requests
import hashlib
from os import path
from base64 import b64encode

try:
    range = xrange
except NameError:
    pass

from . import log, config, util, downloader
from .obj import Song


LOG = log.get_logger("zxLogger")

#163 music api url
url_163="http://music.163.com"
url_mp3="http://m1.music.126.net/%s/%s.mp3"
url_album="http://music.163.com/api/album/%s/"
url_song="http://music.163.com/api/song/detail/?id=%s&ids=[%s]"
url_playlist="http://music.163.com/api/playlist/detail?id=%s"
url_artist_top_song = "http://music.163.com/api/artist/%s"

#agent string for http request header
AGENT= 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.95 Safari/537.36'

#headers
HEADERS = {'User-Agent':AGENT}
HEADERS['Referer'] = url_163
HEADERS['Cookie'] = 'appver=1.7.3'

class NeteaseSong(Song):
    """
    163 Song class, if song_json was given, 
    Song.post_set() needs to be called for post-setting 
    abs_path, filename, etc.
    url example: http://music.163.com/song?id=209235
    """

    def __init__(self,m163,url=None,song_json=None):
        self.song_type=2
        self.m163 = m163
        self.group_dir = None

        if url:
            self.url = url
            self.song_id = re.search(r'(?<=/song\?id=)\d+', url).group(0)

            j = self.m163.read_link(url_song % (self.song_id,self.song_id)).json()['songs'][0]
            self.init_by_json(j)
            #set filename, abs_path etc.
            self.post_set()

        elif song_json:
            self.init_by_json(song_json)


    def init_by_json(self,js):
        #name
        self.song_name = util.decode_html(js['name'])

        # artist_name
        self.artist_name = js['artists'][0]['name']
        # album id, name
        self.album_name = util.decode_html(js['album']['name'])
        self.album_id = js['album']['id']

        # download link
        dfsId = ''
        if self.m163.is_hq:
            dfsId = js['hMusic']['dfsId']
        else:
            dfsId = js['mMusic']['dfsId']
        self.dl_link = url_mp3 % (self.m163.encrypt_dfsId(dfsId), dfsId)

        #used only for album/collection etc. create a dir to group all songs
        #if it is needed, it should be set by the caller
        self.group_dir = None

class NeteaseAlbum(object):
    """The netease album object"""

    def __init__(self, m163, url):
        """url example: http://music.163.com/album?id=2646379"""

        self.m163=m163
        self.url = url 
        self.album_id = re.search(r'(?<=/album\?id=)\d+', self.url).group(0)
        LOG.debug(u'[易]开始初始化专辑[%s]'% self.album_id)
        self.year = None
        self.track=None
        self.songs = [] # list of Song
        self.init_album()

    def init_album(self):
        #album json
        js = self.m163.read_link(url_album % self.album_id).json()['album']
        #name
        self.album_name = util.decode_html(js['name'])
        #album logo
        self.logo = js['picUrl']
        # artist_name
        self.artist_name = js['artists'][0]['name']
        #handle songs
        for jsong in js['songs']:
            song = NeteaseSong(self.m163, song_json=jsong)
            song.group_dir = self.artist_name + u'_' + self.album_name
            song.post_set()
            self.songs.append(song)

        d = path.dirname(self.songs[-1].abs_path)
        #creating the dir
        LOG.debug(u'创建专辑目录[%s]' % d)
        util.create_dir(d)

        #download album logo images
        LOG.debug(u'下载专辑[%s]封面'% self.album_name)
        downloader.download_by_url(self.logo, path.join(d,'cover.' +self.logo.split('.')[-1]))

class NeteasePlayList(object):
    """The netease playlist object"""
    def __init__(self, m163, url):
        self.url = url
        self.m163 = m163
        #user id in url
        self.playlist_id = re.search(r'(?<=/playlist\?id=)\d+', self.url).group(0)
        self.songs = []
        self.init_playlist()

    def init_playlist(self):
        j = self.m163.read_link(url_playlist % (self.playlist_id) ).json()['result']
        self.playlist_name = j['name']
        for jsong in j['tracks']:
            song = NeteaseSong(self.m163, song_json=jsong)
            #rewrite filename, make it different
            song.group_dir = self.playlist_name
            song.post_set()
            self.songs.append(song)
        if len(self.songs):
            #creating the dir
            util.create_dir(path.dirname(self.songs[-1].abs_path))

class NeteaseTopSong(object):
    """download top songs of given artist"""
    def __init__(self, m163, url):
        self.url = url
        self.m163 = m163
        #artist id
        self.artist_id = re.search(r'(?<=/artist\?id=)\d+', self.url).group(0)
        self.artist_name = ""
        self.songs = []
        self.init_topsong()

    def init_topsong(self):
        j = self.m163.read_link(url_artist_top_song % (self.artist_id)).json()
        self.artist_name = j['artist']['name']
        for jsong in j['hotSongs']:
            song = NeteaseSong(self.m163, song_json=jsong)
            song.group_dir = self.artist_name + '_TopSongs'
            song.post_set()
            self.songs.append(song)
            #check config for top X
            if len(self.songs) >= config.DOWNLOAD_TOP_SONG:
                break

        if len(self.songs):
            #creating the dir
            util.create_dir(path.dirname(self.songs[-1].abs_path))

class Netease(object):

    def __init__(self, is_hq=False):
        self.is_hq = is_hq


    def read_link(self, link):
        return requests.get(link, headers=HEADERS)

    def encrypt_dfsId(self,dfsId):
        byte1 = [ord(x) for x in '3go8&$8*3*3h0k(2)2']
        byte2 = bytearray(str(dfsId), 'utf-8')
        byte1_len = len(byte1)
        for i in range(len(byte2)):
            byte2[i] ^= byte1[i%byte1_len]
        m = hashlib.md5()
        m.update(byte2)
        result = b64encode(m.digest()).decode('utf-8')
        result = result.replace('/', '_')
        result = result.replace('+', '-')
        return result
