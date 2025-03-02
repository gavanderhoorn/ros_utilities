# Copyright (c) 2023 Boston Dynamics AI Institute Inc.  All rights reserved.
import argparse

from std_srvs.srv import Trigger

import bdai_ros2_wrappers.process as process


def test_process_wrapping() -> None:
    """Asserts that the process bound node is made available."""

    @process.main(name="test_process")
    def main() -> int:
        def dummy_server_callback(_: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
            response.success = True
            return response

        assert main.node is not None
        main.node.create_service(Trigger, "/dummy/trigger", dummy_server_callback)

        client = main.node.create_client(Trigger, "/dummy/trigger")
        assert client.wait_for_service(timeout_sec=10)

        response = client.call(Trigger.Request())
        assert response.success
        return 0

    assert main() == 0


def test_command_wrapping() -> None:
    """Asserts that the process bound node is made available."""

    def cli() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser("test_command")
        parser.add_argument("-n", "--namespace", default="/")
        parser.set_defaults(node_args=lambda args: dict(namespace=args.namespace))
        return parser

    @process.main(cli())
    def main(args: argparse.Namespace) -> int:
        assert main.node.get_name() == "test_command"
        assert main.node.get_namespace() == "/foo"
        return 0

    assert main(["test_command", "-n", "/foo"]) == 0
