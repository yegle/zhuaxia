# -*- coding:utf-8 -*-

from __future__ import absolute_import

from threading import Thread
import traceback

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

from . import log

LOG = log.get_logger('zxLogger')
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ 
# ThreadPool implementation
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ 
class ThreadPool(object):
    def __init__(self, size):
        self.size = size
        self.tasks = Queue(size)
        for i in range(size):
            Worker(self.tasks)

    def add_task(self, func, *args, **kargs):
        self.tasks.put((func,args,kargs))

    def wait_completion(self):
        self.tasks.join()

class Worker(Thread):
    def __init__(self, taskQueue):
        Thread.__init__(self)
        self.tasks = taskQueue
        self.daemon = True
        self.start()

    def run(self):
        while True:
            func ,args, kargs = self.tasks.get()
            try:
                func(*args, **kargs)
            except: #Exception, e: 
                #LOG.error(str(e))
                LOG.error(traceback.format_exc())

            finally:
                self.tasks.task_done()
