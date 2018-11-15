import yaml
import dotenv
import os # imports package for dotenv
from google.transit import gtfs_realtime_pb2
import urllib2
import csv
import requests
import operator
from protobuf_to_dict import protobuf_to_dict

dotenv.load_dotenv('utils/api_key.env') # loads .env from root directory

# The root directory requires a .env file with API_KEY assigned/defined within
# and dotenv installed from pypi. Get API key from http://datamine.mta.info/user
api_key = os.environ['API_KEY']
TRAINS_TO_ID = yaml.load(open('trains_to_id.yaml'))
stations_url = 'http://web.mta.info/developers/data/nyct/subway/Stations.csv'
# Because the data feed includes multiple arrival times for a given station
# a global list needs to be created to collect the various times
collected_times = []

def get_stations_csv():
    # CSV file reader
    stations_response = urllib2.urlopen(stations_url)
    stations_csv = csv.reader(stations_response)
    # Skips the first line in the csv file because it's the header.
    next(stations_csv)
    return stations_csv

def get_line_array_from_lines(lines):
    line_array = lines.split()
    return line_array

def get_station_names_from_line(line):
    stations_csv = get_stations_csv()
    station_names = [row[5] for row in stations_csv if line in get_line_array_from_lines(row[7])]
    return station_names

def get_station_name_from_gtfs_id(gtfs_id):
    stations_csv = get_stations_csv()
    station_name = ''
    for row in stations_csv:
        if gtfs_id in row[2]: station_name = row[5]
        return station_names
    return 'Station name not found from GTFS Stop ID'

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
