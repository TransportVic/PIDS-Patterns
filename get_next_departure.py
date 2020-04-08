from ptv_api import ptv_api
from dateutil.tz import gettz
import datetime
import time
import sys
import json
from generate_stopping_pattern import generate_stopping_pattern

config = json.load(open('config.json', 'r'))

key = config['key']
dev_id = config['dev_id']

stations = json.load(open('stations.json', 'r'))

aus_mel = gettz('Australia/Melbourne')
utc = gettz('Australia/Melbourne')

def date(iso):
    return datetime.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=aus_mel)

def format_time(time):
    iso_time = str(time)

    hour = time.hour
    minute = time.minute
    hour_offset = int(iso_time[-5:-3])
    hour += hour_offset
    hour %= 12
    return '{}:{}'.format(str(hour), str(minute))

def time_diff(iso):
    millis_now = int(round(time.time()))
    other_time = date(iso)
    hour_offset = int(str(other_time)[-5:-3])
    time_millis = other_time.timestamp() + hour_offset * 60 * 60

    millisecond_diff = (time_millis - millis_now)

    return int(millisecond_diff // 60)

def get_stopping_pattern(run_id, is_up):
    url = '/v3/pattern/run/{}/route_type/0?expand=stop'.format(run_id)
    pattern_payload = ptv_api(url, dev_id, key)
    departures = pattern_payload['departures']
    stops = pattern_payload['stops']

    departures.sort(key=lambda departure: date(departure['scheduled_departure_utc']))
    stopping_pattern = list(map(lambda departure: stops[str(departure['stop_id'])]['stop_name'], departures))

    if 'Jolimont-MCG' in stopping_pattern:
        stopping_pattern[stopping_pattern.index('Jolimont-MCG')] = 'Jolimont'

    if is_up:
        if 'Flinders Street' in stopping_pattern:
            fssIndex = stopping_pattern.index('Flinders Street')
            stopping_pattern = stopping_pattern[0:fssIndex + 1]

    return stopping_pattern

def transform(departure):
    if departure['route_id'] == 13:
        if departure['stop_id'] == 1073:
            departure['platform_number'] = '1'
        else:
            departure['platform_number'] = '3'

    if 'RRB-RUN' in departure['flags']:
        departure['platform_number'] = 'RRB'

    return departure

def get_next_departure_for_platform(station_name, platform):
    stopGTFSID = stations[station_name]
    url = '/v3/departures/route_type/0/stop/{}?gtfs=true&max_results=5&expand=run&expand=route'.format(stopGTFSID)
    departures_payload = ptv_api(url, dev_id, key)
    departures = departures_payload['departures']
    runs = departures_payload['runs']
    routes = departures_payload['routes']

    departures = list(map(transform, departures))

    platform_departures = list(filter(lambda departure: departure['platform_number'] == platform, departures))
    rrb_departures = list(filter(lambda departure: departure['platform_number'] == 'RRB', departures))

    platform_departures.sort(key=lambda departure: date(departure['scheduled_departure_utc']))

    if len(platform_departures):
        next_departure = platform_departures[0]
        run_data = runs[str(next_departure['run_id'])]
        train_descriptor = run_data['vehicle_descriptor']['id']
        route_name = routes[str(next_departure['route_id'])]['route_name']

        is_up = next_departure['direction_id'] == 1
        if next_departure['route_id'] == '13':
            is_up = next_departure['direction_id'] == 5

        stopping_pattern = get_stopping_pattern(next_departure['run_id'], is_up)

        stopping_pattern_info = generate_stopping_pattern(route_name, stopping_pattern, is_up, station_name)
        stopping_text = stopping_pattern_info['stopping_pattern']
        stopping_type = stopping_pattern_info['stopping_type']

        scheduled_departure_utc = next_departure['scheduled_departure_utc']
        estimated_departure_utc = next_departure['estimated_departure_utc']

        destination = stopping_pattern[-1]

        if is_up and 'Flagstaff' in stopping_pattern:
            destination = 'City Loop'

        return {
            "td": train_descriptor,
            "scheduled_departure_utc": scheduled_departure_utc,
            "estimated_departure_utc": estimated_departure_utc,
            "destination": destination,
            "stopping_pattern": stopping_text,
            "stopping_type": stopping_type
        }

        # time_to_departure = None
        # if estimated_departure_utc:
        #     time_to_departure = time_diff(estimated_departure_utc)
        #     if time_to_departure <= 0:
        #         time_to_departure = 'NOW'
        #     else:
        #         time_to_departure = str(time_to_departure) + ' min'
        #
        # print('Next train:', train_descriptor)
        # print(format_time(date(scheduled_departure_utc)), destination)
        # if estimated_departure_utc:
        #     print('Departing', time_to_departure)
        # print(stopping_text)
    elif len(rrb_departures):
        raise Exception('No trains operating buses have been arranged')
    else:
        raise Exception('No trains depart platform {}'.format(platform))

print(get_next_departure_for_platform(sys.argv[1], sys.argv[2]))
