#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import socket
import logging
from multiprocessing import Process
from optparse import OptionParser

import async_handlers
import async_simplehttp

CONTENT_TYPES = {'.html': 'text/html',
                 '.css': 'text/css',
                 '.js': 'text/javascript',
                 '.jpeg': 'image/jpeg',
                 '.jpg': 'image/jpeg',
                 '.png': 'image/png',
                 '.gif': 'image/gif',
                 '.swg': 'application/x-shockwave-flash'}
OK = 200
BAD_REQUEST = 400
FORBIDDEN = 403
NOT_FOUND = 404
INVALID_REQUEST = 422
INTERNAL_ERROR = 500

INDEX_FILE = 'index.html'


class HTTPRequestHandler(async_simplehttp.BaseHTTPRequestHandler):

    def __init__(self, sock=None, map=None, root_dir=''):
        super(HTTPRequestHandler, self).__init__(sock, map)
        self.root_dir = root_dir

    def handle_get(self):
        response, code = '', OK
        full_path = os.path.join(self.root_dir, self.path)
        if os.path.exists(full_path):
            if os.path.isfile(full_path):
                self.content_type = CONTENT_TYPES[os.path.splitext(full_path)[1]]
                self.content_length = os.path.getsize(full_path)
                with open(full_path, 'rb') as f:
                    f.read(512)
            elif os.path.isdir(full_path):
                index_file = os.path.join(full_path, INDEX_FILE)
                if os.path.exists(index_file):
                    self.content_type = CONTENT_TYPES[os.path.splitext(full_path)[1]]
                    self.content_length = os.path.getsize(full_path)
                    with open(index_file, 'rb') as f:
                        f.read(512)
                else:
                    code = NOT_FOUND
        else:
            code = NOT_FOUND

        self.send_response(code)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", self.content_length)
        self.end_headers()
        self.write()

    def handle_head(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

    def read_file(self, path):
        with open(path, 'rb') as f:
            part = True
            while part:
                part = f.read(512)
                yield part


class TCPServer(async_handlers.BaseStreamHandler):

    def __init__(self, addr, handlerclass, map=None, root_dir=''):
        super(TCPServer, self).__init__(map=map)
        self.root_dir = root_dir
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
            _ = self.handlerclass(sock, root_dir=self.root_dir)


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
    #for _ in range(opts.workers):
        #p = Process(target=serving_loop, args=(server,))
        #p.start()
        #p.join()
    serving_loop(server)
