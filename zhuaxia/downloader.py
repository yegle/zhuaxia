# -*- coding:utf-8 -*-

from __future__ import absolute_import

from os import path
import sys
import requests
import datetime,time
from mutagen.id3 import ID3,TRCK,TIT2,TALB,TPE1,APIC,TDRC,COMM,TPOS,USLT
from threading import Thread

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

from . import config, log, util
from .threadpool import ThreadPool

LOG = log.get_logger('zxLogger')

#total number of jobs
total=0
#the number of finished jobs
done=0
#progress dictionary, for progress display
progress = {}
#finsished job to be shown in progress
done2show=[]


#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ 
# output progress 
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ 
def print_progress():
    #the factor of width used for progress bar
    percent_bar_factor = 0.4
    width = util.get_terminal_size()[1] -5
    bar_count = (int(width*percent_bar_factor)-2//10) # number of percent bar
    #line = log.hl(u' %s\n'% ('-'*90), 'cyan')
    line = log.hl(u' %s\n'% ('+'*width), 'cyan')
    sep = log.hl(u' %s\n'% ('='*width), 'cyan')
    sys.stdout.write(u'\x1b[2J\x1b[H') #clear screen
    sys.stdout.write(line)
    header = u' 保存目录:[%s] | 线程池:[%d]\n'% (config.DOWNLOAD_DIR, config.THREAD_POOL_SIZE)
    #header = util.ljust(header, width)
    sys.stdout.write(log.hl(u' %s'%header,'warning'))
    sys.stdout.write(line)

    fmt_progress = '%s [%s] %.1f%%\n'


    all_p = [] #all progress bars, filled by following for loop
    sum_percent = 0 # total percent for running job
    total_percent = 0

    for filename, percent in progress.items():
        sum_percent += percent
        bar = util.ljust('=' * int(percent * bar_count), bar_count)
        per100 = percent * 100 
        single_p =  fmt_progress % \
                (util.rjust(filename,(width - bar_count -10)), bar, per100) # the -10 is for the xx.x% and [ and ]
        all_p.append(log.hl(single_p,'green'))
    
    #calculate total progress percent
    total_percent = float(sum_percent+done)/total
    
    #global progress
    g_text = u'总进度[%d/%d]:'% (done, total)
    g_bar = util.ljust('#' * int(total_percent* bar_count), bar_count)
    g_progress =  fmt_progress % \
                (util.rjust(g_text,(width - bar_count -10)), g_bar, 100*total_percent) # the -10 is for the xx.x% and [ and ]

    #output all total progress bars
    sys.stdout.write(log.hl(u'%s'%g_progress, 'red'))
    sys.stdout.write(sep)

    #output all downloads' progress bars
    sys.stdout.write(''.join(all_p))

    if len(done2show):
        sys.stdout.write(line)
        sys.stdout.write(log.hl(u'  最近%d个完成任务:\n'% config.SHOW_DONE_NUMBER,'warning'))
        sys.stdout.write(line)
        #display finished jobs
        for d in done2show:
            sys.stdout.write(log.hl(u' √ %s\n'% d,'cyan'))

    sys.stdout.flush()

def download_by_url(url,filepath,show_progress=False):
    """ 
    basic downloading function, download url and save to 
    file path
    """
    if ( not filepath ) or (not url):
        LOG.err( 'Url or filepath is not valid, resouce cannot be downloaded.')
        return

    fname = path.basename(filepath)
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        total_length = int(r.headers.get('content-length'))
        done_length = 0
        with open(filepath,'wb') as f:
            for chunk in r.iter_content(1024):
                done_length += len(chunk)
                f.write(chunk)
                if show_progress:
                    percent = float(done_length) / float(total_length)
                    progress[fname] = percent
    return 0

def download(song):
    global done, progress

    #if file not in progress, add
    if song.filename not in progress:
        progress[song.filename] = 0.0

    if ( not song.filename ) or (not song.dl_link):
        LOG.err( 'Song [id:%s] cannot be downloaded' % song.song_id)
        return
    mp3_file = song.abs_path

    download_by_url(song.dl_link, mp3_file, show_progress=True)

    write_mp3_meta(song)
    done += 1
    fill_done2show(song.filename)
    #remove from progress
    del progress[song.filename]

def fill_done2show(filename):
    global done2show
    if len(done2show) == config.SHOW_DONE_NUMBER:
        done2show.pop()
    done2show.insert(0, filename)

def start_download(songs):
    global total, progress
    total = len(songs)
    pool = ThreadPool(config.THREAD_POOL_SIZE)

    downloader = Downloader(songs, pool)
    downloader.start()

    while done < total:
        time.sleep(1)
        print_progress()


class Downloader(Thread):
    def __init__(self, songs, pool):
        Thread.__init__(self)
        self.songs = songs
        self.pool = pool

    def run(self):
        global progress
        for song in self.songs:
            self.pool.add_task(download, song)
        self.pool.wait_completion()

#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ 
# write mp3 meta data to downloaded mp3 files
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ 
def write_mp3_meta(song):
    id3 = ID3()
    id3.add(TIT2(encoding=3, text=song.song_name))
    id3.add(TALB(encoding=3, text=song.album_name))
    id3.add(TPE1(encoding=3, text=song.artist_name))
    id3.save(song.abs_path)
