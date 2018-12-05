import yaml
import dotenv
import os # imports package for dotenv
import time # imports module for Epoch/GMT time conversion
from google.transit import gtfs_realtime_pb2
import urllib2
from urllib2 import HTTPError
import csv
import requests
import operator
from protobuf_to_dict import protobuf_to_dict

#dotenv.load_dotenv('utils/api_key.env') # loads .env from root directory

# The root directory requires a .env file with API_KEY assigned/defined within
# and dotenv installed from pypi. Get API key from http://datamine.mta.info/user
try:
    api_key = os.environ['API_KEY']
except KeyError:
    dotenv.load_dotenv('utils/api_key.env')
    api_key = os.environ['API_KEY']
try:
    DATABASE_URL = os.environ['DATABASE_URL']
except KeyError:
    dotenv.load_dotenv('utils/database_url.env')
    DATABASE_URL = os.environ['DATABASE_URL']
TRAINS_TO_ID = yaml.load(open('trains_to_id.yaml'))

site= 'http://web.mta.info/developers/data/nyct/subway/Stations.csv'
hdr = {'User-Agent': 'Mozilla/5.0'}
stations_url = urllib2.Request(site,headers=hdr)

# Because the data feed includes multiple arrival times for a given station
# a global list needs to be created to collect the various times
collected_times = []

def get_stations_csv():
    # CSV file reader
    try:
        stations_response = urllib2.urlopen(stations_url)
    except urllib2.HTTPError:
        stations_response = open('utils/stations.csv')
    stations_csv = csv.reader(stations_response)
    # Skips the first line in the csv file because it's the header.
    next(stations_csv)
    return stations_csv

def timeUntil(arrival_time):
    current_time = int(time.time())
    time_until_train = int(((arrival_time - current_time) / 60))
    return time_until_train

def get_line_array_from_lines(lines):
    line_array = lines.split()
    return line_array

# Delete this if you replace it with get_station_name_and_gtfs_from_line()
def get_station_names_from_line(line):
    stations_csv = get_stations_csv()
    station_names = [row[5] for row in stations_csv if line in get_line_array_from_lines(row[7])]
    return station_names

def get_gtfs_and_station_name_from_line(line):
    stations_csv = get_stations_csv()
    station_info = []
    for row in stations_csv:
        if line in get_line_array_from_lines(row[7]):
            gtfs_id = row[2]
            station_name = row[5]
            station_info.append((gtfs_id, station_name))
    return station_info

def get_station_name_from_gtfs_id(gtfs_id):
    stations_csv = get_stations_csv()
    station_name = ''
    for row in stations_csv:
        if gtfs_id in row[2]:
            station_name = row[5]
            break
    return station_name

def get_line_ids_from_gtfs(gtfs_id):
    stations_csv = get_stations_csv()
    line_ids = []
    for row in stations_csv:
        if gtfs_id == row[2]:
            lines = get_line_array_from_lines(row[7])
    for line in lines:
        line_id = TRAINS_TO_ID[line]
        if line_id not in line_ids:
            line_ids.append(line_id)
    return line_ids

def get_sorted_times_from_station(direction, station, line):
    stations_csv = get_stations_csv()
    gtfs_id = ''

    for row in stations_csv:
        if line in (row[7]) and station == row[5]:
            gtfs_id = row[2]

    if direction == 'uptown':
        stop_id = gtfs_id + 'N'
    else:
        stop_id = gtfs_id + 'S'

    print 'Line:'+line
    print 'Station: '+station
    print 'gtfs_id is: '+gtfs_id
    print 'stop_id: '+stop_id

    train_id = TRAINS_TO_ID[line]
    # Requests subway status data feed from City of New York MTA API
    response = requests.get('http://datamine.mta.info/mta_esi.php?key={}&feed_id={}'.format(api_key,train_id))
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    #print feed #Uncomment to actually look at the feed you're accessing

    # The MTA data feed uses the General Transit Feed Specification (GTFS) which
    # is based upon Google's "protocol buffer" data format. While possible to
    # manipulate this data natively in python, it is far easier to use the
    # "pip install --upgrade gtfs-realtime-bindings" library which can be found on pypi

    subway_feed = protobuf_to_dict(feed) # subway_feed is a dictionary
    realtime_data = subway_feed['entity'] # train_data is a list

    # Run the above function for the station ID for Broadway-Lafayette
    collected_times = station_time_lookup(realtime_data, stop_id)

    # Sort the collected times list in chronological order (the times from the data
    # feed are in Epoch time format)
    collected_times.sort(key=operator.itemgetter(1))
    return collected_times

# This function takes a converted MTA data feed and a specific station ID and
# loops through various nested dictionaries and lists to (1) filter out active
# trains, (2) search for the given station ID, and (3) append the arrival time
# of any instance of the station ID to the collected_times list
def station_time_lookup(train_data, stop):
    collected_times = []
    for trains in train_data: # trains are dictionaries
        if trains.get('trip_update', False) != False:
            unique_train_schedule = trains['trip_update'] # train_schedule is a dictionary with trip and stop_time_update
            trip_info = unique_train_schedule['trip'] #trip_info is a list of the train info that going through the stops
            route_id = trip_info['route_id']
            unique_arrival_times = unique_train_schedule['stop_time_update'] # arrival_times is a list of arrivals
            for scheduled_arrivals in unique_arrival_times: #arrivals are dictionaries with time data and stop_ids
                if scheduled_arrivals.get('stop_id', False) == stop:
                    time_data = scheduled_arrivals['arrival']
                    unique_time = time_data['time']
                    if unique_time != None:
                        route_time = (route_id, unique_time)
                        collected_times.append(route_time)
                        print 'route time added:', route_time

    return collected_times

def get_times_from_gtfs(gtfs_id):
    uptown_times = []
    downtown_times = []
    line_ids = get_line_ids_from_gtfs(gtfs_id)

    # Sometimes, a station has multiple train lines going through it.
    # (For example, Forest Hills - 71 Av has routes E,F,M and R)
    # This loop goes through each line to get uptown and downtown times
    # for all stations.
    for line_id in line_ids:
        # Requests subway status data feed from City of New York MTA API
        response = requests.get('http://datamine.mta.info/mta_esi.php?key={}&feed_id={}'.format(api_key,line_id))
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        subway_feed = protobuf_to_dict(feed) # subway_feed is a dictionary
        try:
            realtime_data = subway_feed['entity'] # train_data is a list
        except KeyError:
            realtime_data = []

        # Run the above function for the station ID for Broadway-Lafayette
        times = station_up_down_lookup(realtime_data, gtfs_id)
        uptown_times.extend(times[0])
        downtown_times.extend(times[1])


    # Sort the collected times list in chronological order (the times from the data
    # feed are in Epoch time format)
    uptown_times.sort(key=operator.itemgetter(1))
    downtown_times.sort(key=operator.itemgetter(1))

    # Limit the times stored to 3 per direction
    uptown_times = uptown_times[:4]
    downtown_times = downtown_times[:4]
    return uptown_times, downtown_times

# This function takes a converted MTA data feed and a specific station ID and
# loops through various nested dictionaries and lists to (1) filter out active
# trains, (2) search for the given station ID, and (3) append the arrival time
# of any instance of the station ID to the collected_times list
def station_up_down_lookup(train_data, gtfs_id):
    print gtfs_id
    uptown_times = []
    downtown_times = []
    uptown_stop = gtfs_id + 'N'
    downtown_stop = gtfs_id + 'S'

    for trains in train_data: # trains are dictionaries
        if trains.get('trip_update', False) != False:
            unique_train_schedule = trains['trip_update'] # train_schedule is a dictionary with trip and stop_time_update
            trip_info = unique_train_schedule['trip'] #trip_info is a list of the train info that going through the stops
            route_id = trip_info['route_id']
            unique_arrival_times = unique_train_schedule['stop_time_update'] # arrival_times is a list of arrivals
            for scheduled_arrivals in unique_arrival_times: #arrivals are dictionaries with time data and stop_ids
                if scheduled_arrivals.get('stop_id', False) == uptown_stop:
                    try:
                        time_data = scheduled_arrivals['arrival']
                        unique_time = timeUntil(time_data['time'])
                        if unique_time != None and unique_time>0:
                            route_time = (route_id, unique_time)
                            uptown_times.append(route_time)
                    except KeyError:
                        pass
                if scheduled_arrivals.get('stop_id', False) == downtown_stop:
                    try:
                        time_data = scheduled_arrivals['arrival']
                        unique_time = timeUntil(time_data['time'])
                        if unique_time != None and unique_time>0:
                            route_time = (route_id, unique_time)
                            downtown_times.append(route_time)
                    except KeyError:
                        pass
    return uptown_times, downtown_times

def times_dict_from_gtfs_array(gtfs_ids):
    gtfs_dict = {}
    for gtfs_id in gtfs_ids:
        gtfs_dict[gtfs_id] = get_times_from_gtfs(gtfs_id)
    return gtfs_dict
