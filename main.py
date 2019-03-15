from utils import mta

import time # imports module for Epoch/GMT time conversion
import os # imports package for dotenv
import oyaml as yaml
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from flask import session as login_session
import random, string
from protobuf_to_dict import protobuf_to_dict

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
from oauth2client.clientsecrets import InvalidClientSecretsError
import httplib2
import json
from flask import make_response
import requests
import dotenv

from sqlalchemy import create_engine, asc, exists, and_
from sqlalchemy.orm import sessionmaker
from database_setup import Base, User, SavedStation

app = Flask(__name__)
try:
    app.secret_key = os.environ['SECRET_KEY']
except KeyError:
    app.secret_key = '_5#y2L"F4Q8zn+xec]/'

lookup_gtfs=''
TRAINS_TO_ID = yaml.load(open('trains_to_id.yaml'))
try:
    CLIENT_ID = json.loads(os.environ['CLIENT_SECRETS'])['web']['client_id']
except KeyError:
    CLIENT_ID = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Commuter Dash"

# Connect to Database and create database session
# dotenv.load_dotenv('utils/database_url.env') # loads .env from root directory
DATABASE_URL = os.environ['DATABASE_URL']
engine = create_engine(DATABASE_URL)
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

def timeUntil(arrival_time):
    current_time = int(time.time())
    time_until_train = int(((arrival_time - current_time) / 60))
    return time_until_train

# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)

@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data
    print "access token received %s " % access_token


    app_id = json.loads(open('fb_client_secrets.json', 'r').read())[
        'web']['app_id']
    app_secret = json.loads(
        open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (
        app_id, app_secret, access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]


    # Use token to get user info from API
    userinfo_url = "https://graph.facebook.com/v2.8/me"

    token = result.split(',')[0].split(':')[1].replace('"', '')

    url = 'https://graph.facebook.com/v2.8/me?access_token=%s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    # print "url sent for API access:%s"% url
    # print "API JSON result: %s" % result
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout
    login_session['access_token'] = token

    # Get user picture
    url = 'https://graph.facebook.com/v2.8/me/picture?access_token=%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    # see if user exists
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']

    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '

    flash("Now logged in as %s" % login_session['username'])
    return output


@app.route('/fbdisconnect')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (facebook_id,access_token)
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]
    login_session.clear()
    flash('Successfully disconnected')
    return redirect(url_for('main'))

# User Helper Functions
def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id

def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user

def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None

@app.route('/')
def main():
    logged_in = False
    if 'username' in login_session:
        logged_in = True
        user_id = login_session['user_id']

        saved_gtfs_ids = []
        user = session.query(User).filter_by(id=user_id).one()
        stations = session.query(SavedStation).filter_by(user_id=user_id)
        for station in stations: saved_gtfs_ids.append(station.gtfs_id)
        return render_template('dashboard.html', logged_in = logged_in, user=user, gtfs_ids=saved_gtfs_ids, get_name =mta.get_station_name_from_gtfs_id, get_times =mta.get_times_from_gtfs)
    else:
        return render_template('publicDashboard.html')

@app.route('/line-select')
def selectLine():
    return render_template('line.html', lines=TRAINS_TO_ID)

@app.route('/<line>/station-select', methods = ['GET','POST'])
def selectStation(line):
    global lookup_gtfs
    if request.method == 'GET':
        gtfs_and_names = mta.get_gtfs_and_station_name_from_line(line)
        return render_template('stationSelect.html', gtfs_and_names= gtfs_and_names, line=line)

    elif request.method == 'POST':
        gtfs_id = request.form['gtfs_id']
        station_name = mta.get_station_name_from_gtfs_id(gtfs_id)
        # print station_name

        if 'username' in login_session:
            username = login_session['username']
            user_id = login_session['user_id']
            # print user_id

            if session.query(exists().where(and_(
                SavedStation.gtfs_id == gtfs_id,
                SavedStation.user_id == user_id))
            ).scalar():
                flash('%s is already in favorites' % station_name)
            else:
                newStation = SavedStation(gtfs_id = gtfs_id, user_id=login_session['user_id'])
                session.add(newStation)
                flash('Hey %s, we have added %s station to your favorites!' % (username, station_name))
                session.commit()
            return redirect(url_for('main'))

        lookup_gtfs = gtfs_id
        return redirect(url_for('timesDisplay'))

@app.route ('/delete/<gtfs_id>', methods = ['GET','POST'])
def deleteStation(gtfs_id):
    if request.method == 'POST':
        if 'username' in login_session:
            user_id = login_session['user_id']
            itemToDelete = session.query(SavedStation).filter_by(user_id=user_id, gtfs_id=gtfs_id).one()
            session.delete(itemToDelete)
            session.commit()
            flash('Station removed')
            return redirect(url_for('main'))
        else:
            flash("You cannot delete a station if you are not logged in")
            redirect(url_for('gconnect'))
    else:
        station_name = mta.get_station_name_from_gtfs_id(gtfs_id)
        return render_template('deleteConfirmation.html', gtfs_id = gtfs_id, get_name =mta.get_station_name_from_gtfs_id)

@app.route('/times-display')
def timesDisplay():
    global lookup_gtfs
    logged_in = False
    times_dict = mta.times_dict_from_gtfs_array([lookup_gtfs])
    return render_template('dashboard.html', logged_in = logged_in, gtfs_ids=[lookup_gtfs], get_name =mta.get_station_name_from_gtfs_id, get_times =mta.get_times_from_gtfs)

if __name__ == '__main__':
    app.debug = True
    app.run()
