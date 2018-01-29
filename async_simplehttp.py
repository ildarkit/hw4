#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import time
import logging

import async_handlers

__version__ = "0.1"

DEFAULT_ERROR_MESSAGE = """
<head>
<title>Error response</title>
</head>
<body>
<h1>Error response</h1>
<p>Error code {code:d}.
<p>Message: {message}.
<p>Error code explanation: {code:d} = {explain}.
</body>
"""

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
    protocol_version = "HTTP/1.0"
    sys_version = "Python/" + sys.version.split()[0]
    server_version = "BaseHTTP/" + __version__
    responses = {
        200: ('OK', 'Request fulfilled, document follows'),
        404: ('Not Found', 'Nothing matches the given URI'),
        405: ('Method Not Allowed',
              'Specified method is invalid for this resource.'),
    }

    def __init__(self, sock=None, map=None):
        super(BaseHTTPRequestHandler, self).__init__(sock, map)
        self.rawrequest = ''

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
        # using _quote_html to prevent Cross Site Scripting attacks (see bug #1100201)
        content = DEFAULT_ERROR_MESSAGE.format(
            code=code, message=escape(message), explain=explain
        )
        self.send_response(code)
        self.send_header("Content-Type", DEFAULT_ERROR_CONTENT_TYPE)
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD' and code >= 200 and code not in (204, 304):
            self.write(content)

    def send_response(self, code):
        if code in self.responses:
            message = self.responses[code][0]
        else:
            message = ''
        if self.request_version != 'HTTP/0.9':
            self.write("{} {:d} {}\r\n".format(
                self.protocol_version, code, message)
            )
            # print (self.protocol_version, code, message)
        self.send_header('Server', self.version_string())
        self.send_header('Date', self.date_time_string())

    def send_header(self, keyword, value):
        """Send a MIME header."""
        if self.request_version != 'HTTP/0.9':
            self.write("{}: {}\r\n".format(keyword, value))

        if keyword.lower() == 'connection':
            if value.lower() == 'close':
                self.close_connection = 1
            elif value.lower() == 'keep-alive':
                self.close_connection = 0

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

    def log_request(self, code='-', size='-'):
        """Log an accepted request.

        This is called by send_response().

        """

        self.log_message('"{}" {} {}',
                         self.rawrequest, str(code), str(size))

    def log_error(self, format, *args):
        """Log an error.

        This is called when a request cannot be fulfilled.  By
        default it passes the message on to log_message().

        Arguments are the same as for log_message().

        XXX This should go to the separate error log.

        """

        self.log_message(format, *args)

    def log_message(self, format, *args):
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
            # close the generator
            self.gen.close()

    @to_compile_request
    def handle_read(self):
        return self.recv(1024)

    def handle_request(self):
        if not self.parse_request():
            return
        name = 'handle_' + self.command.lower()
        if not hasattr(self, name):
            self.send_error(405, "Unsupported method {0!r}".format(self.command))
            return
        method = getattr(self, name)
        method()

    def parse_request(self):
        """Parse a request (internal).
        The request should be stored in self.raw_requestline; the results
        are in self.command, self.path, self.request_version and
        self.headers.
        Return True for success, False for failure; on failure, an
        error is sent back.
        """
        self.command = None  # set in case of error on the first line
        self.request_version = version = self.default_request_version
        self.close_connection = 1
        self.rawrequest = self.rawrequest.rstrip('\r\n')
        words = self.rawrequest.split()
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
            if version_number >= (1, 1) and self.protocol_version >= "HTTP/1.1":
                self.close_connection = 0
            if version_number >= (2, 0):
                self.send_error(505, "Invalid HTTP Version {}".format(base_version_number))
                return False
        elif len(words) == 2:
            command, path = words
            self.close_connection = 1
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


