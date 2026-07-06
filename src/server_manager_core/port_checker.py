import socket


class PortChecker:
    """
    Practical check:
      - TCP connect to localhost:port to detect if something is listening.
    Note:
      - This does NOT prove WAN reachability.
      - Vintage Story may use both TCP and UDP on 42420; UDP "listening" is not as
        straightforward to test generically from a local-only tool.
    """
    @staticmethod
    def is_tcp_listening(host: str, port: int, timeout: float = 0.12) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def is_port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.12) -> bool:
        return PortChecker.is_tcp_listening(host, int(port), timeout=timeout)
