import sys


class Output:
    @staticmethod
    def print_line(message):
        sys.stderr.write(f"{message}\n")

    @staticmethod
    def print_without_linebreak(message):
        sys.stderr.write(message)

    def print_route(self, route):
        route_str = " -> ".join(str(h.chan_id) for h in route.hops)
        self.print_line(route_str)
