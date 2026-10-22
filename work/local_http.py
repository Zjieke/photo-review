"""HTTP transport for a numeric loopback address, without reverse DNS at startup."""
from http.server import ThreadingHTTPServer
from socketserver import TCPServer


class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        if self.server_address[0] != '127.0.0.1':
            raise ValueError('LocalHTTPServer only accepts the IPv4 loopback address')
        # HTTPServer.server_bind calls socket.getfqdn for a display name. On some
        # macOS networks this blocks for tens of seconds, even for 127.0.0.1.
        # Routing and origin checks use the explicit bind address and actual port.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
