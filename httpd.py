#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
from optparse import OptionParser

import async_handlers
import async_simplehttp


class HTTPRequestHandler(async_simplehttp.BaseHTTPRequestHandler):

    def handle_get(self):
        pass

    def handle_head(self):
        pass


class TCPServer(async_handlers.BaseStreamHandler):

    def __init__(self, name, host, port, handlerclass, map=None):
        super(TCPServer, self).__init__(map=map)
        self.name = name
        self.handlerclass = handlerclass
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            print '{}: Incoming connection from {}'.format(self.name, repr(addr))
            handler = self.handlerclass(sock, map=workers)


if __name__ == '__main__':
    op = OptionParser()
    op.add_option("-p", "--port", action="store", type=int, default=8080)
    op.add_option("-H", "--host", action="store", default='localhost')
    op.add_option("-w", "--workers", action="store", type=int, default=5)
    op.add_option("-r", "--root", action="store", default='root')
    (opts, args) = op.parse_args()
    workers = {}
    server = TCPServer('worker1', opts.host, opts.port, async_simplehttp.BaseHTTPRequestHandler, map=workers)
    try:
        async_handlers.loop(map=workers)
    except KeyboardInterrupt:
        pass
    finally:
        for _, server in workers.items():
            server.close()