#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import sys
import time
import logging

import async_handlers

__version__ = "0.1"

DEFAULT_ERROR_MESSAGE = """<html>
<head>
<title>Error response</title>
</head>
<body>
<h1>Error response</h1>
<p>Error code {code:d}.</p>
<p>Message: {message}.</p>
<p>Error code explanation: {code:d} = {explain}.</p>
</body>
</html>"""

DEFAULT_ERROR_CONTENT_TYPE = "text/html"


class BaseHTTPRequestHandler(async_handlers.StreamHandler):

    default_request_version = "HTTP/0.9"
    protocol_version = "HTTP/1.1"
    sys_version = "Python/" + sys.version.split()[0]
    server_version = "SimpleHTTP/" + __version__
    responses = {
        200: ('OK', 'Request fulfilled, document follows'),
        400: ('Bad Request',
              'Bad request syntax or unsupported method'),
        404: ('Not Found', 'Nothing matches the given URI'),
        403: ('Forbidden',
              'Request forbidden -- authorization will not help'),
        405: ('Method Not Allowed',
              'Specified method is invalid for this resource.'),
        500: ('Internal Server Error', 'Server got itself in trouble'),
        505: ('HTTP Version Not Supported', 'Cannot fulfill request.')
    }

    def __init__(self, sock=None, map=None):
        super(BaseHTTPRequestHandler, self).__init__(sock, map)
        self.rawrequest = ''
        self.content_type = ''
        self.content = ''
        self.content_length = 0
        self.chunked = False
        self.chunk_size = 2048
        self.resource = False

    def send_headers(self, code):
        self.send_header('Server', self.version_string())
        self.send_header('Date', self.date_time_string())
        if self.chunked:
            self.send_header("Transfer-Encoding", 'chunked')
        if code != 200:
            self.send_error(code)
        if self.content_type:
            self.send_header("Content-Type", self.content_type)
            self.send_header('Content-Length', self.content_length)

    def send_response(self, code):
        self.send_status_code(code)
        self.send_headers(code)
        self.end_headers()
        if code != 200:
            self.send_error_body()

    def send_error_body(self):
        if self.command != 'HEAD':
            self.write(self.content, buffered=False,
                       send_size=self.chunk_size)

    def send_error(self, code, log=logging.error):
        try:
            short, long = self.responses[code]
        except KeyError:
            short, long = '???', '???'
        self.log_error("- Status code: {:d} {}", code, short, log=log)
        if self.command != 'HEAD':
            self.content = DEFAULT_ERROR_MESSAGE.format(
                code=code, message=short, explain=long
            )
            self.content_type = DEFAULT_ERROR_CONTENT_TYPE
            self.content_length = len(self.content)

    def send_status_code(self, code):
        if code in self.responses:
            message = self.responses[code][0]
        else:
            message = ''
        if self.request_version != 'HTTP/0.9':
            self.write("{} {:d} {}\r\n".format(
                self.protocol_version, code, message)
            )

    def send_header(self, keyword, value):
        """Send a MIME header."""
        if self.request_version != 'HTTP/0.9':
            self.write("{}: {}\r\n".format(keyword, value))

    def end_headers(self):
        """Send the blank line ending the MIME headers."""
        if self.request_version != 'HTTP/0.9':
            self.write("\r\n")

    def version_string(self):
        """Return the server software version string."""
        return ' '.join((self.server_version, self.sys_version))

    def date_time_string(self, timestamp=None):
        """Return the current date and time formatted for a message header."""
        if timestamp is None:
            timestamp = time.time()
        year, month, day, hh, mm, ss, wd = time.gmtime(timestamp)[:-2]
        s = "{}, {:02d} {:3s} {:4d} {:02d}:{:02d}:{:02d} GMT".format(
                self.weekdayname[wd],
                day, self.monthname[month], year,
                hh, mm, ss)
        return s

    weekdayname = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    monthname = [None,
                 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    def log_error(self, format, *args, **kwargs):
        kwargs['log']("{} - {} {} {}\n".format(
            self.addr[0],
            self.command,
            self.path,
            format.format(*args))
        )

    @staticmethod
    def url_decode(url):
        def decoder(match):
            code = match.group()
            if code:
                return chr(int(code[1:], 16))
        return re.sub('%[0-9a-f]{2}', decoder, url, flags=re.IGNORECASE)

    def handle_read(self):
        """Обработчик события чтения"""
        self.rawrequest = self.read()
        if self.rawrequest:
            self.handle_request()
        else:
            self.handle_close()

    def handle_request(self):
        """Парсинг и вызов обработчика запроса"""
        if not self.validate_start_line():
            return
        name = 'handle_' + self.command.lower()
        if not hasattr(self, name):
            self.send_response(405)
            return
        method = getattr(self, name)
        method()

    def handle_write(self):
        """Обработчик события записи"""
        if self.resource:
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
                part = self.read_resourse()
                _bytes = len(part)
                if _bytes < self.chunk_size:
                    # из файла ничего не прочитали
                    # или же все, что меньше chunk_size
                    # отправляем последний chunk и надо закрываться
                    buffering = False
                    looping = False
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

    def read_resourse(self):
        """Чтение из файла"""
        raise NotImplementedError

    def handle_error(self):
        self.send_response(500)
        super(BaseHTTPRequestHandler, self).handle_error()

    def handle_expt(self):
       self.handle_error()

    def validate_start_line(self):
        self.command = None  # set in case of error on the first line
        self.request_version = version = self.default_request_version
        self.startline = self.rawrequest.split('\n')[0]
        self.startline = self.startline.rstrip('\r')
        words = self.startline.split(None, 2)
        if len(words) == 3:
            command, path, version = words
            if version[:5] != 'HTTP/':
                self.send_response(400)
                return False
            try:
                base_version_number = version.split('/', 1)[1]
                version_number = base_version_number.split(".")
                # RFC 2145 section 3.1 says there can be only one "." and
                #   - major and minor numbers MUST be treated as
                #      separate integers;
                #   - HTTP/2.4 is a lower version than HTTP/2.13, which in
                #      turn is lower than HTTP/12.3;
                #   - Leading zeros MUST be ignored by recipients.
                if len(version_number) != 2:
                    raise ValueError
                version_number = int(version_number[0]), int(version_number[1])
            except (ValueError, IndexError):
                self.send_response(400)
                return False
            if version_number >= (2, 0):
                self.send_error(505)
                return False
        elif len(words) == 2:
            command, path = words
            if command != 'GET':
                self.send_response(400)
                return False
        elif not words:
            return False
        else:
            self.send_response(400)
            return False
        self.command, self.path, self.request_version = command, path, version

        return True
