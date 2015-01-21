#!/usr/bin/python
#
# Author: @sungho

from signal import SIGTERM

import os
import sys
import time
import atexit
import logging
import signal


PATH_DEVICE_NULL = '/dev/null'


def process_running(pid):
  """Check pid are existed or not."""
  try:
    os.kill(int(pid), 0)
  except OSError:
    return False
  return True


class Daemon:
  """A generic daemon class.

  Usage: subclass the Daemon class and override the run() method
  """
  def __init__(self, pid_file_path, worker=1, stdout=None,
               stderr=None):
    self.pid_file_path = pid_file_path
    self.worker = int(worker)

    self.stdin = PATH_DEVICE_NULL
    self.stdout = stdout or PATH_DEVICE_NULL
    self.stderr = stderr or PATH_DEVICE_NULL

  def daemonize(self):
    """Do the UNIX double-fork magic, see Stevens' "Advanced
    Programming in the UNIX Environment" for details (ISBN 0201563177)
    http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
    """
    try:
      pid = os.fork()
      if pid > 0:
        sys.exit(0)
    except OSError, e:
      logging.error('fork #1 failed: %d (%s)' % (e.errno, e.strerror))
      sys.exit(1)

    # decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # do second fork
    try:
      pid = os.fork()
      if pid > 0:
        sys.exit(0)
    except OSError, e:
      logging.error('fork #2 failed: %d (%s)' % (e.errno, e.strerror))
      sys.exit(1)

  def write_pid_file(self):
    # write pid file
    atexit.register(self.exit_hook)
    with file(self.pid_file_path, 'w+') as pid_file:
      pid_file.write(str(os.getpid()))

  def redirect_file(self):
    """Redirect standard file descriptors. """
    os.close(sys.stdin.fileno())
    sys.stdout.flush()
    sys.stderr.flush()

  def exit_hook(self):
    """"""
    if os.path.exists(self.pid_file_path):
      os.remove(self.pid_file_path)
    logging.info('pid {pid} are terminated'.format(pid=os.getpid()))

  def start(self):
    """Start the daemon. """
    # Check for a pidfile to see if the daemon already runs
    try:
      with file(self.pid_file_path, 'r') as pid_file:
        pid = int(pid_file.read().strip())
    except IOError:
      pid = None

    if pid is not None:
      if not process_running(pid):
        os.remove(self.pid_file_path)
      else:
        message = 'pid file {path} already exist. Daemon already running?'
        logging.warning(message.format(path=self.pid_file_path))
        sys.exit(1)

    logging.info('worker process count: %s', self.worker)

    # Start the daemonize
    self.daemonize()

    # make worker process
    childs = []
    for _ in range(self.worker):
      pid = os.fork()
      if pid == 0:
        self.redirect_file()
        self.register_tear_down()
        self.run()
        return
      childs.append(pid)

    self.write_pid_file()

    # TODO(sungho): change from blocking to process monitoring or command listen
    # I recommand to reference a uwsgi master process implementation
    for pid in childs:
      os.waitpid(pid, 0)

  def stop(self):
    """Stop the daemon. """
    # Get the pid from the pid file
    try:
      with file(self.pid_file_path, 'r') as pid_file:
        pid = int(pid_file.read().strip())
    except IOError:
      pid = None

    if pid is None:
      logging.error('process id file {path} does not exist. '
                    'Daemon not running?'.format(path=self.pid_file_path))
      return

    # Try killing the daemon process
    try:
      while True:
        gid = os.getpgid(pid)
        os.killpg(gid, SIGTERM)
        time.sleep(0.1)
    except OSError as error:
      if str(error).find("No such process") > 0:
        if os.path.exists(self.pid_file_path):
          os.remove(self.pid_file_path)
      else:
        logging.error(str(error))
        sys.exit(1)

  def restart(self):
    """Restart the daemon. """
    self.stop()
    self.start()

  def run(self):
    """ You should override this method when you subclass Daemon.

    It will be called after the process has been
    daemonized by start() or restart().
    """
    raise NotImplementedError('run is not implemented')

  def register_tear_down(self):
    """"""
    signal.signal(signal.SIGTERM, self.hooking_tear_down)

  def hooking_tear_down(self, signum, frame):
    """"""
    if signum == signal.SIGTERM:
      try:
        self.tear_down()
      finally:
        sys.exit(0)

  def tear_down(self):
    """"""
