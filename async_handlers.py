#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import socket
import select
import logging
import multiprocessing
from errno import (EWOULDBLOCK, ECONNRESET, EINVAL, ENOTCONN,
                   ESHUTDOWN, EINTR, EBADF, ECONNABORTED, EPIPE, EAGAIN, errorcode)

DISCONNECTED = frozenset((ECONNRESET, ENOTCONN, ESHUTDOWN, ECONNABORTED, EPIPE, EBADF))


def _strerror(err):
    try:
        return os.strerror(err)
    except ValueError:
        return errorcode[err] if err in errorcode else "Unknown error {}".format(err)


socket_map = {}


class ExitNow(Exception):
    pass


_reraised_exceptions = (ExitNow, KeyboardInterrupt, SystemExit)


def readwrite(obj, flags):
    try:
        if flags & select.POLLIN:
            obj.handle_read_event()
        if flags & select.POLLOUT:
            obj.handle_write_event()
        if flags & select.POLLPRI:
            obj.handle_expt_event()
        if flags & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
            obj.handle_close()
    except socket.error as e:
        if e.args[0] not in DISCONNECTED:
            obj.handle_error()
        else:
            obj.handle_close()
    except _reraised_exceptions:
        raise
    except:
        obj.handle_error()


def read(obj):
    try:
        obj.handle_read_event()
    except _reraised_exceptions:
        raise
    except:
        obj.handle_error()


def write(obj):
    try:
        obj.handle_write_event()
    except _reraised_exceptions:
        raise
    except:
        obj.handle_error()


def stopping(obj):
    obj.handle_stop_event()


def closing(obj):
    obj.handle_close_event()


def _exception(obj):
    try:
        obj.handle_expt_event()
    except _reraised_exceptions:
        raise
    except:
        obj.handle_error()


def epoll_poller(timeout=0.0, map=None):
    """A poller which uses epoll(), supported on Linux 2.5.44 and newer."""
    _stopping = False
    r = []
    if map is None:
        map = socket_map
    pollster = select.epoll()
    if map:
        for fd, obj in map.items():
            flags = 0
            if obj.readable():
                flags |= select.POLLIN | select.POLLPRI
            if obj.writable():
                flags |= select.POLLOUT
            if flags:
                # Only check for exceptions if object was either readable
                # or writable.
                flags |= select.POLLERR | select.POLLHUP | select.POLLNVAL
                pollster.register(fd, flags)
        try:
            r = pollster.poll(timeout)
        except select.error, err:
            if err.args[0] != EINTR:
                raise
        except KeyboardInterrupt:
            _stopping = True

        if _stopping:
            for fd in map:
                stopping(map[fd])

        for fd, flags in r:
            obj = map.get(fd)
            if obj is None:
                continue
            readwrite(obj, flags)

        if r == [] and len(map) == 1:
            obj = map.values()[0]
            closing(obj)


def select_poller(timeout=0.0, map=None):
    """A poller which uses select(), available on most platforms."""
    _stopping = False
    if map is None:
        map = socket_map
    if map:
        r = []; w = []; e = []
        for fd, obj in list(map.items()):
            is_r = obj.readable()
            is_w = obj.writable()
            if is_r:
                r.append(fd)
            # accepting sockets should not be writable
            if is_w and not obj.accepting:
                w.append(fd)
            if is_r or is_w:
                e.append(fd)
        if [] == r == w == e:
            time.sleep(timeout)
            return

        try:
            r, w, e = select.select(r, w, e, timeout)
        except (OSError, select.error) as e:
            if e.args[0] != EINTR:
                raise
        except KeyboardInterrupt:
            _stopping = True

        if _stopping:
            for fd in map:
                stopping(map[fd])

        for fd in r:
            obj = map.get(fd)
            if obj is None:
                continue
            read(obj)

        for fd in w:
            obj = map.get(fd)
            if obj is None:
                continue
            write(obj)

        for fd in e:
            obj = map.get(fd)
            if obj is None:
                continue
            _exception(obj)

        if r == w == e == [] and len(map) == 1:
            obj = map.values()[0]
            closing(obj)


def loop(timeout=30.0, map=None, count=None):
    if map is None:
        map = socket_map

    if hasattr(select, 'epoll'):
        poller = epoll_poller
    else:
        poller = select_poller

    if count is None:
        while map:
            poller(timeout, map)

    else:
        while map and count > 0:
            poller(timeout, map)
            count = count - 1


class BaseStreamHandler(object):

    connected = False
    accepting = False
    connecting = False
    closing = False
    refusing = False
    addr = None

    def __init__(self, sock=None, map=None):
        self.send_buffer = ''
        self.recv_buffer = ''
        self.buf_bytes = 0
        if map is None:
            self._map = socket_map
        else:
            self._map = map

        self._fileno = None

        if sock:
            sock.setblocking(0)
            self.set_socket(sock, map)
            self.connected = True
            try:
                self.addr = sock.getpeername()
            except socket.error, err:
                if err.args[0] in (ENOTCONN, EINVAL):
                    self.connected = False
                else:
                    self.del_channel(map)
                    raise
        else:
            self.socket = None

    def __repr__(self):
        status = [self.__class__.__name__]
        if self.accepting and self.addr:
            status.append('listening')
        elif self.connected:
            status.append('connected')
        if self.addr is not None:
            try:
                status.append('{}:{:d}'.format(*self.addr))
            except TypeError:
                status.append(repr(self.addr))
        return '<{} at {:#x}>'.format(' '.join(status), id(self))

    __str__ = __repr__

    def add_channel(self, map=None):
        if map is None:
            map = self._map
        map[self._fileno] = self

    def del_channel(self, map=None):
        fd = self._fileno
        if map is None:
            map = self._map
        if fd in map:
            del map[fd]
        self._fileno = None

    def create_socket(self, family, type):
        self.family_and_type = family, type
        sock = socket.socket(family, type)
        sock.setblocking(0)
        self.set_socket(sock)

    def set_socket(self, sock, map=None):
        self.socket = sock
        self._fileno = sock.fileno()
        self.add_channel(map)

    def set_reuse_addr(self):
        try:
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR,
                self.socket.getsockopt(socket.SOL_SOCKET,
                                       socket.SO_REUSEADDR) | 1
                )
        except socket.error:
            pass

    def readable(self):
        return not self.refusing

    def writable(self):
        return (not self.connected) or len(self.send_buffer)

    def listen(self, num):
        self.accepting = True
        if os.name == 'nt' and num > 5:
            num = 5
        return self.socket.listen(num)

    def bind(self, addr):
        self.addr = addr
        return self.socket.bind(addr)

    def accept(self):
        try:
            conn, addr = self.socket.accept()
        except TypeError:
            return None
        except socket.error as err:
            if err.args[0] in (EWOULDBLOCK, ECONNABORTED, EAGAIN):
                return None
            else:
                raise
        else:
            return conn, addr

    def acceptable(self):
        return self.accepting

    def send(self, data):
        result = 0
        try:
            result = self.socket.send(data)
        except socket.error as err:
            if err.args[0] in DISCONNECTED:
                # сокет отсоединился - закрываем его
                self.handle_close()
            elif err.args[0] == EWOULDBLOCK:
                # отправить в неблокирующий сокет
                # не удалось, нужно закрывать его
                pass
            else:
                raise
        return result

    def recv(self, buffer_size):
        try:
            return self.socket.recv(buffer_size)
        except socket.error as err:
            if err.args[0] in DISCONNECTED:
                # сокет отсоединился - закрываем его
                self.handle_close()
                return ''
            elif err.args[0] == EWOULDBLOCK:
                # из неблокирующего сокета прочитать не удалось
                # возвращаем пустое значение - признак того, что все получено
                return ''
            else:
                raise

    def sendall(self, data):
        while data:
            self.buf_bytes = self.send(data)
            if self.buf_bytes:
                data = data[self.buf_bytes:]
            else:
                data = ''
        if self.closing:
            self.send('')

    def write(self, part='', buffered=True, send_size=2048):
        if part:
            self.send_buffer += part
        if not buffered:
            # в случае когда нужно отправлять chunk-ми,
            # очищаем не весь буфер для того,
            # чтобы оставаться writeable
            if self.send_buffer:
                data = self.send_buffer[:send_size]
                self.send_buffer = self.send_buffer[send_size:]
                self.sendall(data)

    def read(self):
        while True:
            part = self.recv(1024)
            if part:
                self.recv_buffer += part
            else:
                break
        return self.recv_buffer

    def close(self):
        self.connected = False
        self.accepting = False
        self.connecting = False
        self.del_channel()
        try:
            self.socket.close()
        except socket.error as err:
            if err.args[0] not in (ENOTCONN, EBADF):
                raise

    def set_refusing(self):
        # сервер останавливается, поэтому
        # входящие соединения не принимаем
        logging.info('Stopping {}'.format(
            multiprocessing.current_process().name)
        )
        self.accepting = False
        self.refusing = True

    def isrefusing(self):
        return self.refusing

    def handle_read_event(self):
        if not self.connected and self.connecting:
            self.handle_connect_event()
        if self.accepting:
            self.handle_accept()
        elif not self.refusing:
            self.handle_read()

    def handle_write_event(self):
        if self.accepting:
            # Accepting sockets shouldn't get a write event.
            # We will pretend it didn't happen.
            return

        if not self.connected:
            if self.connecting:
                self.handle_connect_event()
        self.handle_write()

    def handle_connect_event(self):
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            raise socket.error(err, _strerror(err))
        self.handle_connect()
        self.connected = True
        self.connecting = False

    def handle_expt_event(self):
        # handle_expt_event() is called if there might be an error on the
        # socket, or if there is OOB data
        # check for the error condition first
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            # we can get here when select.select() says that there is an
            # exceptional condition on the socket
            # since there is an error, we'll go ahead and close the socket
            # like we would in a subclassed handle_read() that received no
            # data
            self.handle_close()
        else:
            self.handle_expt()

    def handle_stop_event(self):
        if self.acceptable():
            # случилось KeyboardInterrupt, поэтому
            # останавливаем серверный сокет
            self.set_refusing()

    def handle_close_event(self):
        if self.isrefusing():
            self.handle_close()
            logging.info('{} is stopped'.format(
                multiprocessing.current_process().name)
            )

    def handle_error(self):
        self.handle_close()

    def handle_expt(self):
        raise NotImplementedError

    def handle_read(self):
        raise NotImplementedError

    def handle_write(self):
        raise NotImplementedError

    def handle_connect(self):
        raise NotImplementedError

    def handle_accept(self):
        raise NotImplementedError

    def handle_close(self):
        self.close()
