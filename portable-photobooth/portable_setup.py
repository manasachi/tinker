"""Connect the Pi to SELPHY Direct Connection and verify router-free printing."""

import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


DIRECT_PROFILE = "photobooth-selphy-direct"
PRINTER_ATTRIBUTES = "/usr/share/cups/ipptool/get-printer-attributes.test"


def command(arguments: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(
            arguments, check=True, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"{arguments[0]} failed: {(error.stderr or error.stdout or str(error)).strip()}"
        ) from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Could not run {arguments[0]}: {error}") from error
    return result.stdout.strip()


def validate_uri(uri: str) -> str:
    parsed = urlsplit(uri)
    if (
        parsed.scheme not in ("ipp", "ipps") or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment
    ):
        raise ValueError("Use an ipp:// or ipps:// printer URI without credentials.")
    if not parsed.hostname.endswith(".local"):
        address = ipaddress.IPv4Address(parsed.hostname)
        if address.is_loopback or address.is_multicast or address.is_unspecified:
            raise ValueError("Use the printer's local address, not a loopback or multicast address.")
    return parsed.hostname


def require_direct_profile(interface: str) -> None:
    active = command(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", interface])
    if active != DIRECT_PROFILE:
        raise RuntimeError(
            f"{interface} is using {active!r}, not {DIRECT_PROFILE!r}. "
            "This is not a verified router-free test. No print was sent."
        )


def direct_printer_uri(interface: str) -> str:
    require_direct_profile(interface)
    options = command(["nmcli", "-g", "DHCP4.OPTION", "device", "show", interface])
    server = re.search(
        r"\bdhcp_server_identifier\s*=\s*(\d{1,3}(?:\.\d{1,3}){3})\b", options,
    )
    if server is None:
        raise RuntimeError(
            "The printer's direct network did not provide a DHCP server address. "
            "Check Direct Connection and the Pi's Wi-Fi status."
        )
    address = ipaddress.IPv4Address(server.group(1))
    return f"ipp://{address}:631/ipp/print"


def connect_direct(ssid: str, interface: str) -> None:
    if not ssid.strip():
        raise ValueError("Enter the SSID shown on the SELPHY Direct Connection screen.")
    profiles = command(["nmcli", "-g", "NAME", "connection", "show"]).splitlines()
    if DIRECT_PROFILE in profiles:
        saved_ssid = command([
            "nmcli", "-g", "802-11-wireless.ssid", "connection", "show", DIRECT_PROFILE,
        ])
        if saved_ssid != ssid:
            raise ValueError(
                f"The saved direct profile belongs to {saved_ssid!r}, not {ssid!r}. "
                "Do not replace it without checking the printer's network settings."
            )
    else:
        command([
            "nmcli", "connection", "add", "type", "wifi", "ifname", interface,
            "con-name", DIRECT_PROFILE, "ssid", ssid,
            "wifi-sec.key-mgmt", "wpa-psk",
        ])
    command([
        "nmcli", "connection", "modify", DIRECT_PROFILE,
        "connection.interface-name", interface,
        "connection.autoconnect", "yes", "connection.autoconnect-priority", "100",
        "ipv4.method", "auto", "ipv4.never-default", "yes", "ipv6.method", "disabled",
    ])
    print(
        "Switching the Pi to the printer's Wi-Fi. An SSH connection through your "
        "old Wi-Fi will disconnect. Enter the printer's password at the local "
        "nmcli prompt; it is not passed as a command-line argument.",
        flush=True,
    )
    try:
        subprocess.run(
            ["nmcli", "--ask", "--wait", "60", "connection", "up", DIRECT_PROFILE,
             "ifname", interface],
            check=True, timeout=90,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            "Could not activate SELPHY Direct Connection. Check the printer's "
            "SSID/password and keep its Direct Connection screen active. "
            f"NetworkManager reported: {error}"
        ) from error


def verify_direct(uri: str, interface: str) -> str:
    hostname = validate_uri(uri)
    require_direct_profile(interface)
    if hostname.endswith(".local"):
        addresses = command(["getent", "ahostsv4", hostname], timeout=10)
        if not addresses:
            raise RuntimeError(f"The printer hostname {hostname} did not resolve.")
        address = str(ipaddress.IPv4Address(addresses.split()[0]))
    else:
        address = str(ipaddress.IPv4Address(hostname))
    routes = json.loads(command(["ip", "-j", "-4", "route", "get", address]))
    if not routes or routes[0].get("dev") != interface or routes[0].get("gateway"):
        raise RuntimeError(
            "The route to the printer is not directly on the selected Wi-Fi link. "
            "Refusing to claim a router-free connection."
        )
    attributes = command(["ipptool", "-tv", uri, PRINTER_ATTRIBUTES], timeout=20)
    model = re.search(r"printer-make-and-model \([^)]*\) = (.+)", attributes)
    if model is None or "CP1500" not in model.group(1).upper().replace(" ", ""):
        raise RuntimeError("The IPP endpoint did not identify itself as a SELPHY CP1500.")
    if not re.search(r"printer-is-accepting-jobs \([^)]*\) = true", attributes):
        raise RuntimeError("The SELPHY is not accepting print jobs.")
    state = re.search(r"printer-state \(enum\) = (\w+)", attributes)
    if state is None or state.group(1) not in ("idle", "processing"):
        raise RuntimeError("The SELPHY is not ready. Check its screen for errors.")
    return f"{model.group(1)} at {address} via {interface}, without a routing gateway"


def configure_queue(queue: str, uri: str) -> None:
    command([
        "/usr/sbin/lpadmin", "-p", queue, "-E", "-v", uri, "-m", "everywhere",
    ], timeout=60)


def print_one_test(queue: str, uri: str, interface: str, output: Path) -> str:
    from print_test import prepare_test_sheet

    verify_direct(uri, interface)
    if command(["lpstat", "-W", "not-completed", "-o", queue]):
        raise RuntimeError("The queue already has a pending job. No additional print was sent.")
    configure_queue(queue, uri)
    path = prepare_test_sheet(output)
    return command([
        "lp", "-d", queue, "-n", "1",
        "-t", "Photobooth - router-free monochrome test - no footer",
        "-o", "PageSize=Postcard.Borderless", "-o", "print-scaling=fit",
        "-o", "orientation-requested=3", "-o", "sides=one-sided",
        "-o", "ColorModel=Gray", "-o", "print-color-mode=monochrome", str(path),
    ], timeout=30)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("connect", "check"))
    parser.add_argument("--ssid", help="SSID shown by the SELPHY in Direct Connection mode.")
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--queue", default="SELPHY_CP1500_Direct")
    parser.add_argument(
        "--printer-uri",
        help="Override the IPP URI; defaults to the printer's DHCP server on its own network.",
    )
    parser.add_argument(
        "--print-test", action="store_true",
        help="After verification, explicitly submit ONE circle sheet without footer text.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path.home() / "Pictures" / "photobooth-printer-tests",
    )
    args = parser.parse_args()
    if args.action == "connect" and not args.ssid:
        parser.error("connect requires --ssid from the printer's Direct Connection screen.")
    try:
        if args.printer_uri:
            validate_uri(args.printer_uri)
        if args.action == "connect":
            connect_direct(args.ssid, args.interface)
        uri = args.printer_uri or direct_printer_uri(args.interface)
        print("Verified: " + verify_direct(uri, args.interface), flush=True)
        if args.action == "connect":
            configure_queue(args.queue, uri)
            print("Saved direct-network profile and driverless printer queue.", flush=True)
        if args.print_test:
            print(print_one_test(args.queue, uri, args.interface, args.output), flush=True)
            print(
                "One job submitted, not yet confirmed printed. Check with: "
                f"lpstat -p {args.queue} -l",
            )
        else:
            print("No print job was sent.")
    except (RuntimeError, ValueError) as error:
        parser.exit(1, f"Portable printer setup failed: {error}\n")


if __name__ == "__main__":
    main()
