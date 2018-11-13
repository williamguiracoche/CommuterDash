from utils import mta

import time # imports module for Epoch/GMT time conversion
import os # imports package for dotenv
import yaml
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash

collected_times = []

TRAINS_TO_ID = yaml.load(open('trains_to_id.yaml'))

app = Flask(__name__)

def timeUntil(arrival_time):
    current_time = int(time.time())
    time_until_train = int(((arrival_time - current_time) / 60))
    return time_until_train

@app.route('/')
def main():
    return 'This is the main page. You may want to visit /line-select'

@app.route('/line-select')
def selectLine():
    return render_template('line.html', lines=TRAINS_TO_ID)

@app.route('/<line>/station-select', methods = ['GET','POST'])
def selectStation(line):
    global collected_times
    if request.method == 'GET':
        station_names = mta.get_station_names_from_line(line)
        return render_template('stationSelect.html', stations = station_names)

    elif request.method == 'POST':
        direction = request.form['direction']
        station = request.form['station']
        print 'direction',direction
        print 'station',station
        print 'line',line
        collected_times = mta.get_sorted_times_from_station(direction, station, line)
        print 'updated master list', collected_times

        return redirect(url_for('timesDisplay'))

@app.route('/times-display')
def timesDisplay():
    global collected_times

    print '[display]: collected_times master list'
    print collected_times
    # Pop off the earliest  arrival times from the list
    first_arrival_time_data = collected_times[0]
    second_arrival_time_data = collected_times[1]
    third_arrival_time_data = collected_times[2]

    first_line = first_arrival_time_data[0]
    first_time = first_arrival_time_data[1]
    second_line = second_arrival_time_data[0]
    second_time = second_arrival_time_data[1]
    third_line = third_arrival_time_data[0]
    third_time = third_arrival_time_data[1]

    time_until_first = timeUntil(first_time)
    time_until_second = timeUntil(second_time)
    time_until_third = timeUntil(third_time)

    print collected_times

    print first_line
    print time_until_first

    print second_line
    print time_until_second

    print third_line
    print time_until_third

    output = ''
    output += '%s train arriving in %d minutes<br>' % (first_line, time_until_first)
    output += '%s train arriving in %d minutes<br>' % (second_line, time_until_second)
    output += '%s train arriving in %d minutes<br>' % (third_line, time_until_third)

    # This final part of the code checks the time to arrival and prints a few
    # different messages depending on the circumstance

    if time_until_first > 3:
        print "Current time: "+time.strftime("%I:%M %p")
        print "Minutes to next: "+str(time_until_first)
        print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(first_time))
    elif time_until_first <= 0:
        print "Missed it. Minutes to next: "+str(time_until_first)
        print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(second_time))
    else:
        print "You have "+str(time_until_first)+" minutes to get home."
        print "Arrival time: "+time.strftime("%I:%M %p", time.localtime(first_time))

    return output

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
