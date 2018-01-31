#!/usr/bin/env python
# -*- coding: utf-8 -*-

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


def to_compile_request(method):
    def generator(self):
        result = True
        while result:
            result = method(self)
            yield result

    def wrapper(self):
        if not hasattr(self, 'gen'):
            self.gen = generator(self)

        self.compile_request()

    return wrapper


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class BaseHTTPRequestHandler(async_handlers.StreamHandler):

    default_request_version = "HTTP/0.9"
    protocol_version = "HTTP/1.1"
    sys_version = "Python/" + sys.version.split()[0]
    server_version = "SimpleHTTP/" + __version__
    responses = {
        200: ('OK', 'Request fulfilled, document follows'),
        400: ('Bad Request',
              'Bad request syntax or unsupported method'),
        403: ('Forbidden',
              'Request forbidden -- authorization will not help'),
        404: ('Not Found', 'Nothing matches the given URI'),
        405: ('Method Not Allowed',
              'Specified method is invalid for this resource.'),
    }

    def __init__(self, sock=None, map=None):
        super(BaseHTTPRequestHandler, self).__init__(sock, map)
        self.rawrequest = ''
        self.content_type = ''
        self.content = ''
        self.content_length = 0

    def send_headers(self):
        self.send_header('Server', self.version_string())
        self.send_header('Date', self.date_time_string())
        if self.content and self.command != 'HEAD':
            self.send_header("Content-Type", self.content_type)
            self.send_header('Content-Length', self.content_length)

    def send_response(self, code):
        self.send_status_code(code)
        self.send_headers()
        self.end_headers()


    def send_error(self, code, message=None):
        """Send and log an error reply.

        Arguments are the error code, and a detailed message.
        The detailed message defaults to the short entry matching the
        response code.

        This sends an error response (so it must be called before any
        output has been generated), logs the error, and finally sends
        a piece of HTML explaining the error to the user.

        """

        try:
            short, long = self.responses[code]
        except KeyError:
            short, long = '???', '???'
        if message is None:
            message = short
        explain = long
        self.log_error("response code: {:d} {}", code, message)
        self.content = DEFAULT_ERROR_MESSAGE.format(
            code=code, message=escape(message), explain=explain
        )
        self.content_type = DEFAULT_ERROR_CONTENT_TYPE
        self.content_length = len(self.content)
        self.send_status_code(code)
        self.send_headers()
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD' and code >= 200 and code not in (204, 304):
            self.write(self.content)

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

    def log_error(self, format, *args):
        logging.error("{} - {}\n".format(
            self.addr[0],
            format.format(*args))
        )

    def compile_request(self):
        part = self.gen.next()
        if part:
            self.rawrequest += part
            self.handle_request()
        else:
            # client was disconnected
            # close generator
            self.gen.close()

    @to_compile_request
    def handle_read(self):
        return self.recv(1024)

    def handle_request(self):
        if not self.validate_start_line():
            return
        name = 'handle_' + self.command.lower()
        if not hasattr(self, name):
            self.send_error(405, "Unsupported method {0!r}".format(self.command))
            return
        method = getattr(self, name)
        method()

    def validate_start_line(self):
        self.command = None  # set in case of error on the first line
        self.request_version = version = self.default_request_version
        self.startline = self.rawrequest.split('\n')[0]
        self.startline = self.startline.rstrip('\r')
        words = self.startline.split(None, 2)
        if len(words) == 3:
            command, path, version = words
            if version[:5] != 'HTTP/':
                self.send_error(400, "Bad request version {0!r}".format(version))
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
                self.send_error(400, "Bad request version {0!r}".format(version))
                return False
            if version_number >= (2, 0):
                self.send_error(505, "Invalid HTTP Version {}".format(base_version_number))
                return False
        elif len(words) == 2:
            command, path = words
            if command != 'GET':
                self.send_error(400, "Bad HTTP/0.9 request type {0!r}".format(command))
                return False
        elif not words:
            return False
        else:
            self.send_error(400, "Bad request syntax {0!r}".format(self.rawrequest))
            return False
        self.command, self.path, self.request_version = command, path, version

        return True
