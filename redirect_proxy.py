import typing
from xmlrpc.client import ProtocolError

from quarry.net.protocol import Protocol, protocol_modes_inv
from quarry.net.server import ServerProtocol, ServerFactory
from quarry.net.client import ClientFactory
from twisted.names import client, dns
from twisted.internet import reactor, defer

from enum import Enum


def connect_addr_to_upstream_addr(connect_addr: str, server_domain: str) -> typing.Tuple[str, int]:

    if not connect_addr.endswith("." + server_domain):
        raise ValueError(
            "connect_addr must end with .{}".format(server_domain))

    temp = connect_addr[:-len(server_domain) - 1]
    ext_idx = temp.rfind(".")

    if ext_idx < 1:
        raise ValueError("connect_addr must be in the form of <host>.[port].<server_domain>")

    # TODO handle raw IP input
    # handle localhost

    lookup_host = temp
    lookup_port = 25565
    ext = temp[ext_idx + 1:]

    if ext.isdigit():
        lookup_host = temp[:ext_idx]
        lookup_port = int(ext)

    if 0 < lookup_port > 65535:
        raise ValueError("port must be between 0 and 65535")

    return lookup_host, lookup_port


class ProxyMode(Enum):
    pass_through_dedicated = 'pass-through-dedicated'
    pass_through_by_domain = 'pass-through-by-domain'
    hidden = 'hidden'

    def __str__(self):
        return self.value


class LowLevelUpstreamFactory(ClientFactory):
    protocol = None
    allow_local_connection = True


class LowLevelUpstreamProtocol(Protocol):
    recv_direction = "downstream"
    send_direction = "upstream"
    factory: LowLevelUpstreamFactory = None

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


class MotdSyncFactory(LowLevelUpstreamFactory):
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


class PassThroughFactory(LowLevelUpstreamFactory):
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


class HiddenFactory(LowLevelUpstreamFactory):
    protocol = HiddenUpstreamProtocol


class MyDownstream(ServerProtocol):
    pass_through_stream = None
    hidden_connect_stream = None
    login_start_buff = None
    upstream_host: str = None
    upstream_port: int = None
    upstream_dns_deffered: defer.Deferred = None

    def dns_result_set_connect_host(self, result):
        try:
            rr = result[0][0]
            if rr.type == dns.SRV:
                self.upstream_host = str(rr.payload.target)
                self.upstream_port = rr.payload.port

        except:
            # XXX: should improve how we handle errback
            pass

        print('resolved', self.upstream_host, self.upstream_port)
        self.upstream_dns_deffered = None

    def motd_upstream_connect(self, _=None):
        motd = MotdSyncFactory()
        motd.mother_server = self
        motd.connect(self.upstream_host,
                     self.upstream_port)

    def hidden_upstream_connect(self):
        hidden = HiddenFactory()
        hidden.mother_server = self
        hidden.connect(self.factory.args.hidden_connect_host,
                       self.factory.args.hidden_connect_port)

    def pass_through_connect(self, _=None):
        pro = PassThroughFactory()
        pro.mother_server = self
        pro.connect(self.upstream_host, self.upstream_port)

    def packet_handshake(self, buff):
        buff.save()

        self.upstream_host = self.factory.args.pass_through_host
        self.upstream_port = self.factory.args.pass_through_port

        buff.unpack_varint()
        connect_host = buff.unpack_string()
        server_domain = self.factory.args.domain

        buff.restore()
        super().packet_handshake(buff)

        if self.factory.args.mode != ProxyMode.hidden:
            if self.factory.args.mode == ProxyMode.pass_through_by_domain:
                try:
                    self.upstream_host, self.upstream_port = connect_addr_to_upstream_addr(connect_host, server_domain)
                except:
                    self.close()
                    return

            if self.upstream_port == 25565:
                self.upstream_dns_deffered = client \
                    .lookupService('_minecraft._tcp.' + self.upstream_host, [10]) \
                    .addCallback(self.dns_result_set_connect_host) \
                    .addErrback(self.dns_result_set_connect_host)

    def packet_login_start(self, buff):
        if self.login_expecting != 0:
            raise ProtocolError("Out-of-order login")

        if self.factory.args.mode == ProxyMode.hidden:
            self.hidden_upstream_connect()
        else:
            if self.upstream_dns_deffered != None:
                self.upstream_dns_deffered.addCallback(self.pass_through_connect)
            else:
                self.pass_through_connect()

        self.login_start_buff = buff.read()

    def packet_login_encryption_response(self, buff):
        # must be from hidden client
        self.hidden_connect_stream.send_packet("login_encryption_response", buff.read())

    def packet_status_request(self, buff):
        if self.factory.args.sync:
            if self.upstream_dns_deffered != None:
                self.upstream_dns_deffered.addCallback(self.motd_upstream_connect)
            else:
                self.motd_upstream_connect()
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
    args = None
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
