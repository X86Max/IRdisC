import unittest

from irdisc import parse_irc_line


class ParseIrcLineTests(unittest.TestCase):
    def test_privmsg(self):
        command, params, trailing = parse_irc_line(
            ":cisc!user@example PRIVMSG #debian-offtopic :hello there"
        )
        self.assertEqual(command, "PRIVMSG")
        self.assertEqual(params, ["#debian-offtopic"])
        self.assertEqual(trailing, "hello there")

    def test_ping(self):
        self.assertEqual(parse_irc_line("PING :server.example"), ("PING", [], "server.example"))


if __name__ == "__main__":
    unittest.main()
