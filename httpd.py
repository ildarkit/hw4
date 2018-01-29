#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import logging
from multiprocessing import Process
from optparse import OptionParser

import async_handlers
import async_simplehttp


class HTTPRequestHandler(async_simplehttp.BaseHTTPRequestHandler):

    def handle_get(self):
        pass

    def handle_head(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()


class TCPServer(async_handlers.BaseStreamHandler):

    def __init__(self, addr, handlerclass, map=None, root=''):
        super(TCPServer, self).__init__(map=map)
        self.root = root
        self.handlerclass = handlerclass
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(addr)
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            logging.info('Incoming connection from {0!r}'.format(addr))
            _ = self.handlerclass(sock)


HTTPServer = TCPServer


def serving_loop(server):
    try:
        async_handlers.loop()
    except KeyboardInterrupt:
        server.close()
        logging.info('Close server {}'.format(server))


if __name__ == '__main__':
    op = OptionParser()
    op.add_option("-p", "--port", action="store", type=int, default=8080)
    op.add_option("-H", "--host", action="store", default='localhost')
    op.add_option("-w", "--workers", action="store", type=int, default=5)
    op.add_option("-r", "--root", action="store", default='root')
    op.add_option("-l", "--log", action="store", default=None)
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log, level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')
    server = HTTPServer((opts.host, opts.port), async_simplehttp.BaseHTTPRequestHandler)
    logging.info("Starting {} workers at {}".format(opts.workers, opts.port))
    for _ in range(opts.workers):
        p = Process(target=serving_loop, args=(server,))
        p.start()
        p.join()