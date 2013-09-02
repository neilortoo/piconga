# -*- coding: utf-8 -*-
"""
tornado_server.participant
~~~~~~~~~~~~~~~~~~~~~~~~~~

Defines the representation of a single participant in a conga.
"""
# Define some states for the Participant connection.
OPENING = 0
UP = 1
CLOSING = 2


class Participant(object):
    """
    Participant wraps a single incoming IOStream. It knows about the next
    participant in the Conga chain, and correctly writes to it.
    """
    def __init__(self, source, db):
        #: The tornado IOStream socket wrapper pointing to the end user.
        self.source_stream = source

        #: The Participant object representing the next link in the conga.
        self.destination = None

        #: A reference to the database object.
        self.db = db

        #: An indiciation of the state of this connection.
        self.state = OPENING

        #: The ID of this particular conga participant.
        self.participant_id = None

    def add_destination(self, destination):
        """
        Add a new conga participant as the target for any incoming conga
        messages.
        """
        self.destination = destination

    def write(self, data):
        """
        Write data on the downstream connection. If no such connection exists,
        drop this stuff on the floor.
        """
        try:
            self.source_stream.write(data)
        except AttributeError:
            pass

    def wait_for_headers(self):
        """
        Read from the incoming stream until we receive the delimiter that tells
        us that the headers have ended.
        """
        self.source_stream.read_until(b'\r\n\r\n', self._parse_headers)

    def _parse_headers(self, header_data):
        """
        Turns the headers into a dictionary. Checks the content-length and
        reads that many bytes as the body. Most importantly, handles the
        request URI.
        """
        headers = {}

        decoded_data = header_data.decode('utf-8')
        lines = decoded_data.split('\r\n')
        request_uri = lines[0]

        try:
            header_lines = lines[1:]
        except IndexError:
            header_lines = []

        for line in header_lines:
            if line:
                key, val = line.split(':', 1)
                headers[key] = val

        # Get the content-length, and then read however many bytes we need to
        # get the body.
        length = int(headers.get('Content-Length', '0'))

        if (request_uri == 'HELLO') and (self.state == OPENING):
            cb = self._hello(header_data)
        elif (request_uri == 'BYE') and (self.state == UP):
            pass
        elif (request_uri == 'MSG') and (self.state == UP):
            # This is a simple message, so we just want to repeat it.
            cb = self._repeat_data(header_data)
        else:
            raise RuntimeError("Unexpected verb.")

        self.source_stream.read_bytes(length, cb)
        self.wait_for_headers()

    def _hello(self, header_data):
        """
        Builds a closure for use as a registration callback. This closure is
        actually really minor, but we do it anyway to keep the interface.
        """
        def callback(data):
            self.state = UP

        return callback

    def _repeat_data(self, header_data):
        """
        Builds a closure for use as a data sending callback. We use a closure
        here to ensure that we are able to wait for the message body before
        sending the headers, just in case the message is ill-formed. That way
        we don't confuse clients by sending headers with no following body.
        """
        def callback(data):
            self.destination.write(header_data + data)

        return callback
