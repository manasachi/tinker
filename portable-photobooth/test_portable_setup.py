import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from portable_setup import (
    DIRECT_PROFILE, command, configure_queue, connect_direct, main, print_one_test,
    direct_printer_uri, validate_uri, verify_direct,
)


URI = "ipp://CP1500f66dc2.local:631/ipp/print"
ATTRIBUTES = (
    "printer-make-and-model (textWithoutLanguage) = Canon SELPHY CP1500\n"
    "printer-is-accepting-jobs (boolean) = true\n"
    "printer-state (enum) = idle\n"
)


class PortableSetupTests(unittest.TestCase):
    def test_explicit_uris_accept_local_hostname_or_direct_address(self):
        self.assertEqual(validate_uri(URI), "cp1500f66dc2.local")
        self.assertEqual(validate_uri("ipp://192.168.0.1:631/ipp/print"), "192.168.0.1")
        for uri in (
            "http://printer.local/", "ipp://127.0.0.1/ipp/print",
            "ipp://user:password@printer.local/ipp/print", "ipp://printer.local/?x=y",
        ):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                validate_uri(uri)

    def test_direct_address_comes_from_the_current_dhcp_lease_not_mdns_or_home_ip(self):
        for server in ("192.168.0.1", "192.168.4.1"):
            with self.subTest(server=server), patch(
                "portable_setup.command", side_effect=[
                    DIRECT_PROFILE, f"ip_address = 192.168.0.2 | dhcp_server_identifier = {server} | routers = {server}",
                ],
            ) as run:
                self.assertEqual(direct_printer_uri("wlan0"), f"ipp://{server}:631/ipp/print")
                self.assertNotIn("getent", str(run.call_args_list))

    def test_missing_direct_dhcp_address_is_reported(self):
        with patch("portable_setup.command", side_effect=[DIRECT_PROFILE, "ip_address = 192.168.0.2"]):
            with self.assertRaisesRegex(RuntimeError, "DHCP server address"):
                direct_printer_uri("wlan0")

    def test_connect_saves_auto_reconnect_without_putting_password_in_arguments(self):
        with patch("portable_setup.command", return_value=""), \
                patch("portable_setup.subprocess.run") as run, \
                patch("sys.stdout", new_callable=io.StringIO):
            connect_direct("SELPHY-direct", "wlan0")
        run.assert_called_once_with(
            ["nmcli", "--ask", "--wait", "60", "connection", "up", DIRECT_PROFILE,
             "ifname", "wlan0"], check=True, timeout=90,
        )

    def test_connect_preserves_other_saved_networks_and_rejects_wrong_saved_ssid(self):
        with patch("portable_setup.command", side_effect=[DIRECT_PROFILE, "Other printer"]) as run:
            with self.assertRaisesRegex(ValueError, "saved direct profile"):
                connect_direct("SELPHY-direct", "wlan0")
        self.assertEqual(run.call_count, 2)

    def test_connect_sets_reconnect_priority_and_does_not_replace_default_route(self):
        with patch("portable_setup.command", return_value="") as run, \
                patch("portable_setup.subprocess.run"), patch("sys.stdout", new_callable=io.StringIO):
            connect_direct("SELPHY-direct", "wlan0")
        modification = run.call_args.args[0]
        self.assertIn("100", modification)
        self.assertEqual(modification[modification.index("ipv4.never-default") + 1], "yes")
        self.assertNotIn("delete", str(run.call_args_list))

    def test_verify_requires_saved_direct_profile(self):
        with patch("portable_setup.command", return_value="Home Wi-Fi") as run:
            with self.assertRaisesRegex(RuntimeError, "not a verified router-free test"):
                verify_direct(URI, "wlan0")
        self.assertEqual(run.call_count, 1)

    def test_verify_rejects_other_interface_or_router_hop(self):
        for route in ('[{"dev":"eth0"}]', '[{"dev":"wlan0","gateway":"192.168.1.1"}]', "[]"):
            with self.subTest(route=route), patch(
                "portable_setup.command",
                side_effect=[DIRECT_PROFILE, "192.168.0.1 STREAM printer", route],
            ):
                with self.assertRaisesRegex(RuntimeError, "route to the printer"):
                    verify_direct(URI, "wlan0")

    def test_verify_checks_printer_identity_and_readiness(self):
        replies = (
            ATTRIBUTES.replace("CP1500", "Other"),
            ATTRIBUTES.replace("= true", "= false"),
            ATTRIBUTES.replace("= idle", "= stopped"),
        )
        for attributes in replies:
            with self.subTest(attributes=attributes), patch(
                "portable_setup.command",
                side_effect=[DIRECT_PROFILE, "192.168.0.1 STREAM printer",
                             '[{"dev":"wlan0"}]', attributes],
            ), self.assertRaises(RuntimeError):
                verify_direct(URI, "wlan0")

    def test_verify_succeeds_on_direct_local_link(self):
        with patch("portable_setup.command", side_effect=[
            DIRECT_PROFILE, "192.168.0.1 STREAM printer", '[{"dev":"wlan0"}]', ATTRIBUTES,
        ]):
            self.assertIn("without a routing gateway", verify_direct(URI, "wlan0"))

    def test_verify_direct_ip_does_not_depend_on_mdns(self):
        with patch("portable_setup.command", side_effect=[
            DIRECT_PROFILE, '[{"dev":"wlan0"}]', ATTRIBUTES,
        ]) as run:
            self.assertIn("without a routing gateway", verify_direct(
                "ipp://192.168.0.1:631/ipp/print", "wlan0",
            ))
        self.assertNotIn("getent", str(run.call_args_list))

    def test_check_does_not_modify_network_or_submit_print(self):
        with patch.object(sys, "argv", ["portable_setup.py", "check"]), \
                patch("portable_setup.direct_printer_uri", return_value=URI), \
                patch("portable_setup.verify_direct", return_value="Direct link"), \
                patch("portable_setup.connect_direct") as connect, \
                patch("portable_setup.configure_queue") as configure, \
                patch("portable_setup.print_one_test") as print_test, \
                patch("sys.stdout", new_callable=io.StringIO):
            main()
        connect.assert_not_called()
        configure.assert_not_called()
        print_test.assert_not_called()

    def test_test_print_verifies_again_and_refuses_duplicate_job(self):
        with patch("portable_setup.verify_direct") as verify, \
                patch("portable_setup.command", return_value="SELPHY_CP1500-3"), \
                patch("print_test.prepare_test_sheet") as prepare:
            with self.assertRaisesRegex(RuntimeError, "pending job"):
                print_one_test("SELPHY_CP1500", URI, "wlan0", Path("unused"))
        verify.assert_called_once_with(URI, "wlan0")
        prepare.assert_not_called()

    def test_explicit_test_prints_one_sheet_without_text(self):
        with patch("portable_setup.verify_direct"), patch(
            "portable_setup.command", side_effect=["", "request id is SELPHY_CP1500-4"],
        ) as run, patch("portable_setup.configure_queue") as configure, patch(
            "print_test.prepare_test_sheet", return_value=Path("test.png"),
        ) as prepare:
            self.assertIn("request id", print_one_test(
                "SELPHY_CP1500", URI, "wlan0", Path("output"),
            ))
        prepare.assert_called_once_with(Path("output"))
        configure.assert_called_once_with("SELPHY_CP1500", URI)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[arguments.index("-n") + 1], "1")
        self.assertEqual(arguments[-1], "test.png")

    def test_configure_queue_is_driverless(self):
        with patch("portable_setup.command") as run:
            configure_queue("SELPHY_CP1500", URI)
        self.assertEqual(run.call_args.args[0][-2:], ["-m", "everywhere"])

    def test_backend_failures_are_explicit_and_never_automatically_retried(self):
        for failure in (
            OSError("nmcli missing"),
            subprocess.CalledProcessError(1, ["nmcli"], stderr="Not authorized"),
            subprocess.TimeoutExpired(["nmcli"], 20),
        ):
            with self.subTest(failure=failure), patch(
                "portable_setup.subprocess.run", side_effect=failure,
            ) as run:
                with self.assertRaises(RuntimeError):
                    command(["nmcli"])
                self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
