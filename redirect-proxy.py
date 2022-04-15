from xmlrpc.client import ProtocolError

from quarry.net.protocol import Protocol, protocol_modes_inv
from quarry.net.server import ServerProtocol, ServerFactory
from quarry.net.client import ClientFactory
from twisted.internet import reactor

from enum import Enum


class ProxyMode(Enum):
    pass_through_dedicated = 'pass-through-dedicated'
    pass_through_by_domain = 'pass-through-by-domain'
    hidden = 'hidden'

    def __str__(self):
        return self.value


class LowLevelUpstreamProtocol(Protocol):
    recv_direction = "downstream"
    send_direction = "upstream"

    def connection_made(self):
        """Called when the connection is established"""

        self.protocol_version = self.factory.mother_server.protocol_version

        # Send handshake
        addr = self.transport.connector.getDestination()
        self.send_packet(
            "handshake",
            self.buff_type.pack_varint(self.protocol_version) +
            self.buff_type.pack_string(addr.host) +
            self.buff_type.pack('H', addr.port) +
            self.buff_type.pack_varint(
                protocol_modes_inv[self.factory.protocol_mode_next]))

        # Switch buff type
        self.buff_type = self.factory.get_buff_type(self.protocol_version)

        self.protocol_mode = self.factory.protocol_mode_next

        self.logger.debug("Connection made")


class MotdSyncProtocol(LowLevelUpstreamProtocol):
    def connection_made(self):
        super().connection_made()

        self.send_packet("status_request", b'')

    def packet_status_response(self, buff):
        self.factory.mother_server.send_packet('status_response', buff.read())


class MotdSyncFactory(ClientFactory):
    protocol = MotdSyncProtocol
    protocol_mode_next = "status"


class PassThroughUpstreamProtocol(LowLevelUpstreamProtocol):
    def connection_made(self):
        self.factory.mother_server.pass_through_stream = self

        super().connection_made()

        self.send_packet(
            "login_start", self.factory.mother_server.login_start_buff)

    def connection_lost(self, reason):
        self.factory.mother_server.close()

        super().connection_lost(reason)

    def data_received(self, data):
        self.factory.mother_server.transport.write(data)

        self.connection_timer.restart()


class PassThroughFactory(ClientFactory):
    protocol = PassThroughUpstreamProtocol


class HiddenUpstreamProtocol(LowLevelUpstreamProtocol):
    request_sent = False

    def connection_made(self):
        self.factory.mother_server.hidden_connect_stream = self

        super().connection_made()

        self.send_packet(
            "login_start", self.factory.mother_server.login_start_buff)

    def packet_login_encryption_request(self, buff):
        self.factory.mother_server.send_packet(
            "login_encryption_request", buff.read())
        self.request_sent = True

    def data_received(self, data):
        if not self.request_sent:
            super().data_received(data)

        self.connection_timer.restart()
        # ignore


class HiddenFactory(ClientFactory):
    protocol = HiddenUpstreamProtocol


class MyDownstream(ServerProtocol):
    pass_through_stream = None
    hidden_connect_stream = None
    login_start_buff = None

    def hidden_upstream_connect(self):
        hidden = HiddenFactory()
        hidden.mother_server = self
        hidden.connect(self.factory.hidden_connect_host,
                       self.factory.hidden_connect_port)

    def pass_through_connect(self):
        pro = PassThroughFactory()
        pro.mother_server = self
        pro.connect(self.factory.connect_host, self.factory.connect_port)

    def packet_login_start(self, buff):
        if self.login_expecting != 0:
            raise ProtocolError("Out-of-order login")

        if self.factory.mode == ProxyMode.hidden:
            self.hidden_upstream_connect()
        else:
            self.pass_through_connect()

        self.login_start_buff = buff.read()

    def packet_login_encryption_response(self, buff):
        # must be from hidden client
        self.hidden_connect_stream.send_packet(
            "login_encryption_response", buff.read())

    def packet_status_request(self, buff):
        if self.factory.sync:
            ms = MotdSyncFactory()
            ms.mother_server = self
            ms.connect(self.factory.connect_host, self.factory.connect_port)
        else:
            super().packet_status_request(buff)

    def connection_lost(self, reason):
        if self.pass_through_stream is not None:
            self.pass_through_stream.close()

        super().connection_lost(reason)

    def data_received(self, data):
        if self.pass_through_stream is not None:
            self.pass_through_stream.transport.write(data)

            self.connection_timer.restart()
            return

        super().data_received(data)


class MyDownstreamFactory(ServerFactory):
    protocol = MyDownstream
    connect_host = None
    connect_port = None
    hidden_connect_host = None
    hidden_connect_port = None
    mode = ProxyMode.pass_through
    sync = True
    motd = "A Minecraft Server"


def main(argv):
    # Parse options
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--listen-host1", default="",
                        help="address to listen on")
    parser.add_argument("-p", "--listen-port1", default=25566,
                        type=int, help="port to listen on")
    parser.add_argument("-b", "--pass-through-host",
                        default="minehut.com", help="address to connect to in dedicated mode")
    parser.add_argument("-q", "--pass-through-port", default=25565,
                        type=int, help="port to connect to in dedicated mode")
    parser.add_argument("-c", "--hidden-connect-host",
                        default="127.0.0.1", help="another address to connect to in hidden mode")
    parser.add_argument("-r", "--hidden-connect-port", default=25565,
                        type=int, help="another port to connect to in hidden mode")
    parser.add_argument("-d", "--domain", default="",
                        help="the domain the proxy is running on")
    parser.add_argument("-m", "--mode", default=ProxyMode.pass_through_dedicated,
                        type=ProxyMode, choices=list(ProxyMode), help="proxy mode")
    parser.add_argument(
        '--sync', help="sync motd with pass through host (default)", action='store_true')
    parser.add_argument('--no-sync', action='store_false')
    parser.set_defaults(sync=True)
    args = parser.parse_args(argv)

    if args.mode == ProxyMode.pass_through_by_domain and args.domain == "":
        parser.error("--domain is required for pass-through-by-domain mode")
        return

    # Create factory
    factory = MyDownstreamFactory()
    factory.args = args

    # Listen
    factory.listen(args.listen_host1, args.listen_port1)
    reactor.run()


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
