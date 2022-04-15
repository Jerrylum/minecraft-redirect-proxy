import unittest
from redirect_proxy import connect_addr_to_upstream_addr as test_method

domain = "server.domain"

class TestAddrConversion(unittest.TestCase):

    def do_test_error(self, errmsg, func):
        with self.assertRaises(ValueError) as context:
            func()
        self.assertTrue(errmsg in str(context.exception))

    def test_endswith_server_domain(self):
        errmsg = "connect_addr must end"
        self.do_test_error(errmsg, lambda: test_method("", domain))
        self.do_test_error(errmsg, lambda: test_method(".domain", domain))
        self.do_test_error(errmsg, lambda: test_method(".domain.", domain))
        self.do_test_error(errmsg, lambda: test_method("server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method(".server.domain.", domain))

    def test_addr_format(self):
        errmsg = "connect_addr must be in the form"
        self.do_test_error(errmsg, lambda: test_method(".server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("c.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("com.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method(".com.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("localhost.server.domain", domain))

    def test_no_localhost(self):
        errmsg = "connect_addr must not be localhost"
        self.do_test_error(errmsg, lambda: test_method("localhost.25565.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("hello.localhost.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("hello.localhost.25565.server.domain", domain))

    def test_ip_format(self):
        errmsg = "ip address is invalid"
        self.do_test_error(errmsg, lambda: test_method("1.2.3.4.5.6.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("1.2.3.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("100.200.300.400.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("100.200.300.400.500.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("100.200.300.400.50000.server.domain", domain))

    def test_ip_is_public(self):
        errmsg = "host must be a public IP address"
        self.do_test_error(errmsg, lambda: test_method("127.0.0.0.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("127.0.0.1.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("127.0.1.1.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("10.0.0.0.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("10.0.0.1.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("10.0.1.1.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("192.168.0.0.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("192.168.0.1.server.domain", domain))
        self.do_test_error(errmsg, lambda: test_method("192.168.1.1.server.domain", domain))

    def test_port_is_in_range(self):
        errmsg = "port must be between 0 and 65535"
        self.do_test_error(errmsg, lambda: test_method("host.com.65536.server.domain", domain))

    def test_conversion_okay(self):
        self.assertEqual(test_method("host.com.server.domain", domain), ("host.com", 25565))
        self.assertEqual(test_method("my.host.com.server.domain", domain), ("my.host.com", 25565))
        self.assertEqual(test_method("my.host.com.25565.server.domain", domain), ("my.host.com", 25565))
        self.assertEqual(test_method("my.host.com.3000.server.domain", domain), ("my.host.com", 3000))
        self.assertEqual(test_method("12.34.56.78.server.domain", domain), ("12.34.56.78", 25565))
        self.assertEqual(test_method("12.34.56.78.25565.server.domain", domain), ("12.34.56.78", 25565))
        self.assertEqual(test_method("12.34.56.78.3000.server.domain", domain), ("12.34.56.78", 3000))
        pass

if __name__ == "__main__":
    unittest.main()