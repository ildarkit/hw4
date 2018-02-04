#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import socket
import logging
import multiprocessing
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
FORBIDDEN = 403
INDEX_FILE = 'index.html'


class HTTPRequestHandler(async_simplehttp.BaseHTTPRequestHandler):

    def __init__(self, sock=None, map=None, root_dir=''):
        super(HTTPRequestHandler, self).__init__(sock, map)
        self.root_dir = root_dir
        self.resource_found = False
        self.chunk_size = 1024 * 1024

    def handle_get(self):
        self.handle_head()

    def handle_head(self):
        code = self.get_content()
        self.send_response(code)

    def get_content(self):
        code = OK
        try_index_file = False
        full_path = self.root_dir + self.url_decode(self.path.split('?', 1)[0])
        full_path = os.path.normpath(full_path)
        if os.path.isdir(full_path):
            full_path = os.path.join(full_path, INDEX_FILE)
            try_index_file = True
        if os.path.isfile(full_path):
            self.content = full_path
            self.content_type = CONTENT_TYPES[os.path.splitext(full_path)[1].lower()]
            self.resource_found = True
        elif try_index_file:
            code = FORBIDDEN
        else:
            code = NOT_FOUND
        if self.command == 'HEAD':
            self.content_length = len(self.rawrequest.rstrip())
            # для того, чтобы пропустить чтение-запись файла
            self.resource_found = False
        elif self.resource_found:
            self.content_length = os.path.getsize(full_path)
            # большой файл отправляем не сразу весь целиком, а chunk-ми
            if self.content_length > self.chunk_size:
                self.chunked = True
            # возвращаем генератор
            self.file_reader = self.read_file()
        return code

    def read_file(self):
        with open(self.content, 'rb') as content_file:
            part = True
            while part:
                part = content_file.read(self.chunk_size)
                yield part

    def handle_write(self):
        if self.resource_found:
            if self.chunked:
                # большой файл отдаем chunk-ми
                # в буфере всегда остается какая-то часть от
                # предыдущей итерации, чтобы оставаться writeable
                buffering = False
            else:
                # все прочитанное из файла складываем в буфер и выходим из обработчика
                # при следующем возникновении события на запись, отправляем
                buffering = True
            looping = True

            while looping:
                part = self.file_reader.next()
                _bytes = len(part)
                if _bytes < self.chunk_size:
                    # из файла ничего не прочитали
                    # или же все, что меньше chunk_size
                    # отправляем последний chunk и надо закрываться
                    buffering = False
                    looping = False
                    self.file_reader.close()
                    self.closing = True

                if self.chunked:
                    # записываем длину блока
                    chunk_len = hex(_bytes)
                    chunk_len = chunk_len.lstrip('0x')
                    self.write(chunk_len + '\r\n')
                    looping = False
                    part += '\r\n'

                self.write(part, buffered=buffering,
                           send_size=self.chunk_size)
        else:
            self.closing = True
            self.write('', buffered=False,
                       send_size=self.chunk_size)
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
            worker_name = multiprocessing.current_process().name
            logging.info('{}: Incoming connection from {}'.format(worker_name, addr))
            _ = self.handlerclass(sock, root_dir=self.root_dir)


HTTPServer = TCPServer


if __name__ == '__main__':
    workers = []
    op = OptionParser()
    op.add_option("-p", "--port", action="store", type=int, default=8080)
    op.add_option("-H", "--host", action="store", default='localhost')
    op.add_option("-w", "--workers", action="store", type=int, default=5)
    op.add_option("-r", "--root", action="store", default='/home/ildark/otus_python/http-test-suite')
    op.add_option("-l", "--log", action="store", default=None)
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log, level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')

    server = HTTPServer((opts.host, opts.port), HTTPRequestHandler, root_dir=opts.root)
    logging.info("Starting {} workers at {}".format(opts.workers, opts.port))
    multiprocessing.log_to_stderr(logging.INFO)
    for i in range(opts.workers):
        p = multiprocessing.Process(target=async_handlers.loop,
                                    name='worker' + str(i))
        workers.append(p)

    for worker in workers:
        worker.start()

    for worker in workers:
        worker.join()
    server.close()

