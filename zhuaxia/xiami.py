# -*- coding:utf-8 -*-

from __future__ import absolute_import

import time
import re
import requests
import urllib
from os import path

from . import log, config, util, downloader
from .obj import Song

LOG = log.get_logger("zxLogger")

#xiami android/iphone api urls
url_xiami="http://www.xiami.com"
url_hq="http://www.xiami.com/song/gethqsong/sid/%s"
url_vip="http://www.xiami.com/vip/update-tone"
url_login="https://login.xiami.com/member/login"
url_song = "http://www.xiami.com/app/android/song?id=%s"
url_album = "http://www.xiami.com/app/android/album?id=%s"
url_fav = "http://www.xiami.com/app/android/lib-songs?uid=%s&page=%s"
url_collection = "http://www.xiami.com/app/android/collect?id=%s"
url_artist_top_song = "http://www.xiami.com/app/android/artist-topsongs?id=%s"
#url_artist_albums = "http://www.xiami.com/app/android/artist-albums?id=%s&page=%s"

#agent string for http request header
AGENT= 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.95 Safari/537.36'

class XiamiSong(Song):
    """
    xiami Song class, if song_json was given, 
    Song.post_set() needs to be called for post-setting 
    abs_path, filename, etc.
    """

    def __init__(self,xiami_obj,url=None,song_json=None):
        self.song_type=1
        self.xm = xiami_obj
        self.group_dir = None
        if url:
            self.url = url
            self.init_by_url(url)
            #set filename, abs_path etc.
            self.post_set()
        elif song_json:
            self.init_by_json(song_json)
        
        #if is_hq, get the hq location to overwrite the dl_link
        if self.xm.is_hq:
            try:
                self.dl_link = self.xm.get_hq_link(self.song_id)
            except:
                #if user was not VIP, don't change the dl_link
                pass


    def init_by_json(self, song_json ):
        """ the group dir and abs_path should be set by the caller"""

        self.song_id = song_json['song_id']
        self.album_id = song_json['album_id']
        self.song_name = util.decode_html(song_json['name'])
        self.dl_link = song_json['location']
        # lyrics link
        self.lyrics_link = song_json['lyric']
        # artist_name
        self.artist_name = song_json['artist_name']
        # album id, name
        self.album_name = song_json['title']

        #self.filename = (self.song_name + u'.mp3').replace('/','_')

    def init_by_url(self,url):
        self.song_id = re.search(r'(?<=/song/)\d+', url).group(0)
        j = self.xm.read_link(url_song % self.song_id).json()
        #name
        #self.song_name = j['song']['song_name'].replace('&#039;',"'")
        self.song_name = util.decode_html(j['song']['song_name'])
        # download link
        self.dl_link = j['song']['song_location']
        # lyrics link
        self.lyrics_link = j['song']['song_lrc']
        # artist_name
        self.artist_name = j['song']['artist_name']
        # album id, name
        self.album_name = util.decode_html(j['song']['album_name'])
        self.album_id = j['song']['album_id']

        #used only for album/collection etc. create a dir to group all songs
        self.group_dir = None


class Album(object):
    """The xiami album object"""
    def __init__(self, xm_obj, url):

        self.xm = xm_obj
        self.url = url 
        self.album_id = re.search(r'(?<=/album/)\d+', self.url).group(0)
        LOG.debug(u'开始初始化专辑[%s]'% self.album_id)
        self.year = None
        self.track=None
        self.songs = [] # list of Song
        self.init_album()

    def init_album(self):
        j = self.xm.read_link(url_album % self.album_id).json()['album']
        #name
        self.album_name = util.decode_html(j['title'])
        #album logo
        self.logo = j['album_logo']
        # artist_name
        self.artist_name = j['artist_name']

        #description
        self.album_desc = j['description']

        #handle songs
        for jsong in j['songs']:
            song = XiamiSong(self.xm, song_json=jsong)
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

        LOG.debug(u'保存专辑[%s]介绍'% self.album_name)
        if self.album_desc:
            self.album_desc = re.sub(r'&lt;\s*[bB][rR]\s*/&gt;','\n',self.album_desc)
            self.album_desc = re.sub(r'&lt;.*?&gt;','',self.album_desc)
            self.album_desc = util.decode_html(self.album_desc)
            import codecs
            with codecs.open(path.join(d,'album_description.txt'), 'w', 'utf-8') as f:
                f.write(self.album_desc)


class Favorite(object):
    """ xiami Favorite songs by user"""
    def __init__(self,xm_obj, url):
        self.url = url
        self.xm = xm_obj
        #user id in url
        self.uid = re.search(r'(?<=/lib-song/u/)\d+', self.url).group(0)
        self.songs = []
        self.init_fav()

    def init_fav(self):
        page = 1
        while True:
            j = self.xm.read_link(url_fav % (self.uid, str(page)) ).json()
            if j['songs'] :
                for jsong in j['songs']:
                    song = XiamiSong(self.xm, song_json=jsong)
                    #rewrite filename, make it different
                    song.group_dir = 'favorite_%s' % self.uid
                    song.post_set()
                    self.songs.append(song)
                page += 1
            else:
                break
        if len(self.songs):
            #creating the dir
            util.create_dir(path.dirname(self.songs[-1].abs_path))
            
class Collection(object):
    """ xiami song - collections made by user"""
    def __init__(self,xm_obj, url):
        self.url = url
        self.xm = xm_obj
        #user id in url
        self.collection_id = re.search(r'(?<=/showcollect/id/)\d+', self.url).group(0)
        self.songs = []
        self.init_collection()

    def init_collection(self):
        j = self.xm.read_link(url_collection % (self.collection_id) ).json()['collect']
        self.collection_name = j['name']
        for jsong in j['songs']:
            song = Song(self.xm, song_json=jsong)
            #rewrite filename, make it different
            song.group_dir = self.collection_name
            song.post_set()
            self.songs.append(song)
        if len(self.songs):
            #creating the dir
            util.create_dir(path.dirname(self.songs[-1].abs_path))

class TopSong(object):
    """download top songs of given artist"""
    def __init__(self, xm_obj, url):
        self.url = url
        self.xm = xm_obj
        #artist id
        self.artist_id = re.search(r'(?<=/artist/)\d+', self.url).group(0)
        self.artist_name = ""
        self.songs = []
        self.init_topsong()

    def init_topsong(self):
        j = self.xm.read_link(url_artist_top_song % (self.artist_id)).json()
        for jsong in j['songs']:
            song = XiamiSong(self.xm, song_json=jsong)
            song.group_dir = self.artist_name + '_TopSongs'
            song.post_set()
            self.songs.append(song)
            #check config for top X
            if len(self.songs) >= config.DOWNLOAD_TOP_SONG:
                break

        if len(self.songs):
            #set the artist name
            self.artist_name = self.songs[-1].artist_name
            #creating the dir
            util.create_dir(path.dirname(self.songs[-1].abs_path))

checkin_headers = {
    'User-Agent': AGENT,
    'Content-Length': '0',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
    'Host': 'www.xiami.com',
    'Origin': url_xiami,
    'Referer': url_xiami,
    'Content-Length': '0',
}


class Xiami(object):

    def __init__(self, email, password, is_hq=False):
        self.token = None
        self.uid = ''
        self.user_name = ''
        self.email = email
        self.password = password
        self.skip_login = False
        self.session = None
        self.is_hq = is_hq
        #if either email or password is empty skip login
        if not email or not password or not is_hq:
            self.skip_login = True
            
        self.member_auth = ''
        #do login
        if self.skip_login:
            LOG.warning(u'[虾] 不登录虾米进行下载, 虾米资源质量为128kbps.')
            is_hq = False
        else:
            if self.login():
                LOG.info( u'[Login] 用户: %s (id:%s) 登录成功.' % (self.user_name.decode('utf-8'),self.uid) )
            else:
                is_hq = False

    def login(self):
        LOG.info( u'[虾] 登录虾米...')
        _form = {
            'email': self.email,
            'password': self.password,
            'submit': '登 录',
        }
        headers = {'User-Agent': AGENT}
        headers['Referer'] = url_login
        # do http post login
        try:
            sess = requests.Session()
            sess.headers['User-Agent'] = AGENT
            sess.verify = False
            sess.mount('https://', requests.adapters.HTTPAdapter())
            self.session = sess
            res = sess.post(url_login, data=_form)
            self.memeber_auth = sess.cookies['member_auth']
            self.uid, self.user_name = urllib.unquote(sess.cookies['user']).split('"')[0:2]
            self.token = sess.cookies['_xiamitoken']
            return True
        except:
            LOG.warning(u'[虾] 登录失败, 略过登录, 虾米资源质量为 128kbps.')
            self.is_hq = False
            return False

    def read_link(self, link):
        headers = {'User-Agent':AGENT}
        headers['Referer'] = 'http://img.xiami.com/static/swf/seiya/player.swf?v=%s'%str(time.time()).replace('.','')

        if self.skip_login:
            return requests.get(link, headers=headers)
        else:
            return self.session.get(link,headers=headers)


    def get_hq_link(self, song_id):
        mess = self.read_link(url_hq%song_id).json()['location']
        return self.decode_xiami_link(mess)

    def decode_xiami_link(self,mess):
        """decode xm song link"""
        rows = int(mess[0])
        url = mess[1:]
        len_url = len(url)
        cols = len_url / rows
        re_col = len_url % rows # how many rows need to extend 1 col for the remainder

        l = []
        for row in xrange(rows):
            ln = cols + 1 if row < re_col else cols
            l.append(url[:ln])
            url = url[ln:]

        durl = ''
        for i in xrange(len_url):
            durl += l[i%rows][i/rows]

        return urllib.unquote(durl).replace('^', '0')

