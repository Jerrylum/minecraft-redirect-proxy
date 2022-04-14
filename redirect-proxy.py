from xmlrpc.client import ProtocolError

from quarry.net.protocol import Protocol, protocol_modes_inv
from quarry.net.server import ServerProtocol, ServerFactory
from quarry.net.client import ClientFactory
from twisted.internet import reactor, task, defer


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

        self.send_packet(
            "login_start", self.factory.mother_server.login_start_buff)

        self.logger.debug("Connection made")


class PassThroughUpstreamProtocol(LowLevelUpstreamProtocol):
    def connection_made(self):
        self.factory.mother_server.pass_through_stream = self

        super().connection_made()

    def data_received(self, data):
        self.factory.mother_server.transport.write(data)

        self.connection_timer.restart()


class PassThroughFactory(ClientFactory):
    protocol = PassThroughUpstreamProtocol


class SideUpstreamProtocol(LowLevelUpstreamProtocol):
    request_sent = False

    def connection_made(self):
        self.factory.mother_server.side_client_stream = self

        super().connection_made()

    def packet_login_encryption_request(self, buff):
        self.factory.mother_server.send_packet(
            "login_encryption_request", buff.read())
        self.request_sent = True

    def data_received(self, data):
        if not self.request_sent:
            super().data_received(data)

        self.connection_timer.restart()
        # ignore


class SideFactory(ClientFactory):
    protocol = SideUpstreamProtocol


class MyDownstream(ServerProtocol):
    pass_through_stream = None
    side_client_stream = None
    login_start_buff = None

    def side_upstream_connect(self):
        side = SideFactory()
        side.mother_server = self
        side.connect(self.factory.side_client_host, self.factory.side_client_port)

    def pass_through_connect(self):
        pro = PassThroughFactory()
        pro.mother_server = self
        pro.connect(self.factory.connect_host, self.factory.connect_port)

    def packet_login_start(self, buff):
        if self.login_expecting != 0:
            raise ProtocolError("Out-of-order login")

        # side client mode
        # self.side_upstream_connect()

        # pass through mode
        self.pass_through_connect()

        self.login_start_buff = buff.read()

    def packet_login_encryption_response(self, buff):
        # must be from side client
        self.side_client_stream.send_packet(
            "login_encryption_response", buff.read())

        # research needed
        # task.deferLater(reactor, 3, self.pass_through_connect)

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
    side_client_host = None
    side_client_port = None
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
                        default="mh-prd.minehut.com", help="address to connect to")
    parser.add_argument("-q", "--pass-through-port", default=25565,
                        type=int, help="port to connect to")
    parser.add_argument("-c", "--side-client-host",
                        default="127.0.0.1", help="another address to connect to")
    parser.add_argument("-r", "--side-client-port", default=25565,
                        type=int, help="another port to connect to")
    args = parser.parse_args(argv)

    # Create factory
    factory = MyDownstreamFactory()
    factory.connect_host = args.pass_through_host
    factory.connect_port = args.pass_through_port
    factory.side_client_host = args.side_client_host
    factory.side_client_port = args.side_client_port

    # Listen
    factory.listen(args.listen_host1, args.listen_port1)
    reactor.run()


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
