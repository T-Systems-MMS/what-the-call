#!/usr/bin/env python3
# coding: utf-8
"""
This script shows the last notifications from multiple icinga instances
"""

import requests
from requests.auth import HTTPBasicAuth
import json
import typing
from sys import exit, stdin
import time
import select
from datetime import datetime
from getpass import getpass, getuser
import configargparse
from re import compile
from colorama import Fore, Style, ansi

def regex_parse(arg_value):
    """
    checks if the argument is a regex and compiles it - required for input validation
    """
    try:
        contact_filter = compile(arg_value)
    except:
        raise configargparse.ArgumentTypeError("invalid regex")
    return contact_filter

def generate_url(
        instance: str,
        host: str,
        service: typing.Optional[str]=None):
    """
    generates the URL to the check in the webinterface
    """
    if service is None:
        url = f"{instance}/dashboard#!/monitoring/host/show?host={host}"
    else:
        url = f"{instance}/dashboard#!/monitoring/service/show?host={host}&service={service}"
    return url

def get_instance_notifications(instance: str):
    """
    load the notifications of the supplied icinga instance
    """
    response = requests.request(
        "GET",
        f"{instance}/monitoring/list/notifications?notification_timestamp>={args.lookback}",
        headers=headers,
        auth=icinga_auth
    )
    try:
        output = json.loads(response.text)
    except json.decoder.JSONDecodeError:
        print(f"error decoding json from {instance}. Login error?")
        exit(1)
    # add links to output
    for row in output:
        url = generate_url(
            instance=instance,
            host = row.get("host_name"),
            service = row.get("service_description")
            )
        row.update({"url": url })
    return output

def sort_by_ts(elem):
    """helper function to return the timestamp from the element dict for sorting"""
    return elem.get("notification_timestamp")

def data_of_instances(instances):
    """fetches data from multiple icinga instances"""
    returns = []
    for instance in instances:
        icinga_output = get_instance_notifications(
            instance=instance
        )
        returns.extend(icinga_output)
    returns.sort(key=sort_by_ts, reverse=True)
    return returns

def show_time(ts):
    """icinga returns timestamps as unix timestamp - this produces "readable" time for the output"""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def state_string(state):
    """maps the state number (1-3) to colored text output"""
    states = {
        '0': f'{Fore.GREEN}OK{Fore.RESET}',
        '1': f'{Fore.YELLOW}WARN{Fore.RESET}',
        '2': f'{Fore.RED}CRIT{Fore.RESET}',
        '3': f'{Fore.CYAN}UNKN{Fore.RESET}'
    }
    return states.get(state, state)

def text_output(notifications, limit: int):
    """generates text output from fetched notifications"""
    counter = 0
    separator = " | "
    for r in notifications:
        timestamp = show_time(int(r.get("notification_timestamp")))
        hostname = r.get("host_name")
        service = r.get("service_display_name")
        url = r.get("url")
        state = state_string(r.get("notification_state"))

        if r.get("notification_contact_name") != None:
            if args.filter.match(r.get("notification_contact_name")):
                if counter < limit:
                    output = separator.join([
                            f"{counter+1:02d}",
                            timestamp,
                            state,
                            hostname,
                            service
                        ])
                    print(output)
                    if not args.disable_urls:
                        print(f'   `-{Fore.GREEN}{Style.BRIGHT}{url}{Style.RESET_ALL}')
                    counter += 1
                else:
                    break

def show_data():
    """fetches and outputs icinga notifications"""
    notifs = data_of_instances(args.instance)

    text_output(
        notifications=notifs,
        limit=args.limit
    )

def wait_for_key(
        prompt: str,
        timeout: int,
    ):
    """waits for a timeout or a keypress"""
    print(prompt, end='', flush=True)
    timeStart = time.time()

    while True:
        if(timeout > -1 and (time.time() - timeStart) >= timeout):
            break
        if (select.select([stdin], [], [], 0) == ([stdin], [], [])):
            stdin.read(1)
            break
        time.sleep(0.1)

if __name__ == "__main__":

    p = configargparse.ArgParser(
    default_config_files=['~/.config/wtc.yml'],
    config_file_parser_class=configargparse.YAMLConfigFileParser,
    formatter_class=configargparse.ArgumentDefaultsHelpFormatter,
    )

    p.add(
        "--instance",
        "-i",
        type=str,
        help="one or more icinga instances to monitor",
        action="append",
        required=True,
    )
    p.add(
        "--lookback",
        "-l",
        type=str,
        help="how long to look back for notifications",
        default="-1 days",
    )
    p.add(
        "--limit",
        type=int,
        help="number of the last entries to display",
        default=10,
    )
    p.add(
        "--filter",
        type=regex_parse,
        help="regex filter for notification contact name",
        default=".*",
    )
    p.add(
        "--user",
        "-u",
        type=str,
        help="Login User for Icinga",
        default=getuser(),
    )
    p.add(
        "--password",
        "-p",
        type=str,
        help="Login Password for Icinga",
        default=None,
    )
    p.add(
        "--disable-urls",
        action="store_true",
        default=False,
    )
    p.add(
        "--watch",
        "-w",
        action="store_true",
        help="run the output in infinite loop, refreshing automatically",
        default=False,
    )
    p.add(
        "--watch-interval",
        help="interval for updates in watch mode in seconds",
        type=int,
        default=120,
    )

    args = p.parse_args()

    # ask for password if it isn't set from the commandline
    if args.password is None:
        password = getpass(f'enter password for {args.user}:')
    else:
        password = args.password

    icinga_auth = HTTPBasicAuth(args.user, password)

    headers = {
        "Accept": "application/json"
    }

    if args.watch:
        while True:
            try:
                print(ansi.clear_screen())
                show_data()
                wait_for_key(
                    prompt=f"Waiting for {args.watch_interval}s, press enter to refresh now",
                    timeout=args.watch_interval,
                    )
            except KeyboardInterrupt:
                exit(0)
    else:
        show_data()
