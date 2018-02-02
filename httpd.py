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
                 '.txt': 'text/plain',
                 '.jpeg': 'image/jpeg',
                 '.jpg': 'image/jpeg',
                 '.png': 'image/png',
                 '.gif': 'image/gif',
                 '.swf': 'application/x-shockwave-flash'}
OK = 200
NOT_FOUND = 404
INDEX_FILE = 'index.html'


class HTTPRequestHandler(async_simplehttp.BaseHTTPRequestHandler):

    def __init__(self, sock=None, map=None, root_dir=''):
        super(HTTPRequestHandler, self).__init__(sock, map)
        self.root_dir = root_dir
        self.resource_found = False

    def handle_get(self):
        self.handle_head()

    def handle_head(self):
        code = self.get_content()
        self.send_response(code)

    def get_content(self):
        code = OK
        full_path = os.path.join(self.root_dir, self.path)
        full_path = self.url_decode(full_path)
        if os.path.isdir(full_path):
            full_path = os.path.join(full_path, INDEX_FILE)
        if os.path.isfile(full_path):
            self.content = full_path
            self.content_type = CONTENT_TYPES[os.path.splitext(full_path)[1].lower()]
            self.resource_found = True
        else:
            code = NOT_FOUND
        if self.command == 'HEAD':
            self.content_length = len(self.rawrequest.rstrip())
            # для того, чтобы пропустить чтение-запись файла
            self.resource_found = False
        elif self.resource_found:
            self.content_length = os.path.getsize(full_path)
            if self.content_length > 64 * 1024:
                self.chunked = True
            # создание генератора
            self.file_reader = self.read_file()
        return code

    def read_file(self):
        with open(self.content, 'rb') as content_file:
            part = True
            while part:
                part = content_file.read(64 * 1024)
                yield part

    def handle_write(self):
        if self.resource_found:
            buffering = True
            looping = True
            while looping:
                part = self.file_reader.next()
                if self.chunked:
                    chunk_len = hex(len(part))
                    chunk_len = chunk_len.lstrip('0x')
                    self.write(chunk_len + '\r\n')
                    looping = False
                if not part:
                    buffering = False
                    looping = False
                    self.file_reader.close()
                    self.closing = True
                self.write(part, buffered=buffering)
        else:
            self.write('', buffered=False)
            self.closing = True
        if self.closing:
            self.handle_close()


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
            # logging.info('Incoming connection from {0!r}'.format(addr))
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
    op.add_option("-r", "--root", action="store", default=r'D:\otus_python\http-test-suite')
    op.add_option("-l", "--log", action="store", default=None)
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log, level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')
    server = HTTPServer((opts.host, opts.port), HTTPRequestHandler, root_dir=opts.root)
    logging.info("Starting {} workers at {}".format(opts.workers, opts.port))
    #for _ in range(opts.workers):
        #p = Process(target=serving_loop, args=(server,))
        #p.start()
        #p.join()
    serving_loop(server)
