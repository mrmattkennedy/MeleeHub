import os
import json
import pytz
import asyncio
import datetime
import configparser
import multiprocessing
import requests
from threading import RLock

from waitress import serve

from flask import Flask, render_template, redirect, url_for, jsonify, flash, request, session
from requests.models import HTTPError
from flask_discord import DiscordOAuth2Session
import discord as discordpy


import pyrebase
import firebase_admin
from firebase_admin import credentials, auth
from firebase_admin._auth_utils import EmailAlreadyExistsError

file_home = os.path.dirname(os.path.realpath(__file__))
import sys
sys.path.insert(0, file_home)
from firebase_worker import Firebase_Worker
from gcs_worker import GCS_Worker


#Create application using urandomeo
app = Flask(__name__)
app.secret_key = os.urandom(24)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"

#Read config file into parser
conf_reader = configparser.ConfigParser()
conf_reader.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'configs', 'config.cfg'))

app.config["DISCORD_CLIENT_ID"] = conf_reader.get('discord', 'client_id')       # Discord client ID.
app.config["DISCORD_CLIENT_SECRET"] = conf_reader.get('discord', 'secret')      # Discord client secret.
app.config["DISCORD_REDIRECT_URI"] = "https://meleehub.gg/discordCallback"      # URL to your callback endpoint.
# app.config["DISCORD_REDIRECT_URI"] = "http://localhost:8080/discordCallback"    # URL to your callback endpoint.
app.config["DISCORD_BOT_TOKEN"] =  conf_reader.get('discord', 'bot_token')      # Required to access BOT resources.
discord = DiscordOAuth2Session(app)
client = discordpy.Client()

#Webhook for discord support
app.config['DISCORD_SUPPORT_WEBHOOK'] = conf_reader.get('discord', 'support_webhook')
app.config['DISCORD_HIGHLIGHTS_WEBHOOK'] = conf_reader.get('discord', 'highlights_webhook')

#Indeces for firebase user data
app.config['USER_TIER_IDX'] = 1
app.config['IS_TO_IDX'] = 2
app.config['DISCORD_ID_IDX'] = 3
app.config['DISCORD_USER_IDX'] = 4
app.config['TOURNAMENT_START_IDX'] = 5



#Create firebase credentials
API_KEY = conf_reader.get('firebase', 'api_key')
AUTH_DOMAIN = conf_reader.get('firebase', 'auth_domain')
DATABASE_URL = conf_reader.get('firebase', 'database_url')
STORAGE_BUCKET = conf_reader.get('firebase', 'storage_bucket')

#Create firebase instance
config = {
    "apiKey": API_KEY,
    "authDomain": AUTH_DOMAIN,
    "databaseURL": DATABASE_URL,
    "storageBucket": STORAGE_BUCKET
}

#Initialize db_worker for firebase database handling
firebase_db = pyrebase.initialize_app(config)
db_worker = Firebase_Worker()

#Firebase authentication
cred = credentials.Certificate(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'configs', 'firebase_adminsdk.json'))
firebase = firebase_admin.initialize_app(cred)

#GCS worker
gcs_worker = GCS_Worker(db_worker)

#Lock for viewing messages
lock = RLock()

########################################
# Check if a request is within daily limits
# No tier is limited to 10 weekly 
# uploads/downloads
########################################
def check_daily_limits(numFiles):
    #Set tier limits
    t0_limit = 10
    t1_limit = 50
    t2_limit = 1000
    t3_limit = 1000

    #Change to $5 tier can do it a large amount, then t2+t3 can do more

    now = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
    refreshCutoffDay = datetime.timedelta(hours=24)
    refreshCutoffWeek = datetime.timedelta(weeks=1)

    #Get user tier
    if not 'userTier' in session: session['userTier'] = 0            
    userTier = session['userTier']

    #If not already done, get user logs for last day and for all time, or if logs have passed 24 hours
    if not 'dailyDownloads' in session or ('refreshAtTimeDay' in session and now - session['refreshAtTimeDay'] > refreshCutoffDay) or ('refreshAtTimeWeek' in session and now - session['refreshAtTimeWeek'] > refreshCutoffWeek) or ('recheckLog' in session and session['recheckLog']):
        #Get info
        if 'uid' in session: downloads, uploads, weeklyDownloads, weeklyUploads, totalDownloads, totalUploads, oldestDailyTimestamp, oldestWeeklyTimestamp = getFirebaseActivityLastDay(uid=session['uid'])
        else: downloads, uploads, weeklyDownloads, weeklyUploads, totalDownloads, totalUploads, oldestDailyTimestamp, oldestWeeklyTimestamp = getFirebaseActivityLastDay(remote_addr=session['remote_addr'])

        #Save in session so this only happens once per session
        session['dailyDownloads'] = downloads
        session['dailyUploads'] = uploads
        session['weeklyDownloads'] = weeklyDownloads
        session['weeklyUploads'] = weeklyUploads
        session['totalDownloads'] = totalDownloads
        session['totalUploads'] = totalUploads
        session['refreshAtTimeDay'] = oldestDailyTimestamp
        session['refreshAtTimeWeek'] = oldestWeeklyTimestamp

        session.permanent = True
        session['recheckLog'] = False

    #Authenticate user
    if userTier == 0:
        if session['weeklyUploads'] + session['weeklyUploads'] + numFiles <= t0_limit:
            return True
        else:
            return False

    elif userTier == 1:
        if session['weeklyUploads'] + session['weeklyUploads'] + numFiles <= t1_limit:
            return True
        else:
            return False

    elif userTier == 2:
        if session['weeklyUploads'] + session['weeklyUploads'] + numFiles <= t2_limit:
            return True
        else:
            return False

    elif userTier == 3:
        if session['weeklyUploads'] + session['weeklyUploads'] + numFiles <= t3_limit:
            return True
        else:
            return True

    elif userTier == 4:
        return True

########################################
# Checks if a user is within tier limits 
# for an upload/download action
########################################
@app.route('/canDoAction', methods=["POST"])
def canDoAction(numFiles=None):
    updateUserSessionData()
    if not numFiles:
        try:
            if numFiles == None: numFiles = int(request.form.get('numFiles'))
        except:
            return jsonify({'result': False})

    canDoAction = check_daily_limits(numFiles)
    return jsonify({'result': canDoAction})
    

########################################
# Home page for the website
# Sets session data each time a user visits
# in order to track source IP for request limitations
# Also get the tournaments the user has access to for uploading
########################################
@app.route('/')
def home():
    updateUserSessionData()

    #check if email/uid in session, update if so
    if 'email' in session: email = session['email']
    else: email = None
    if 'uid' in session: uid = session['uid']
    else: uid = None
    if 'discordID' in session: discordID = session['discordID']
    else: discordID = 0
    if 'discordUsername' in session: discordUsername = session['discordUsername']
    else: discordUsername = 0
    if 'userTier' in session: userTier = session['userTier']
    else: userTier = None

    #Get source IP and add to session
    if not 'HTTP_X_REAL_IP' in request.environ: session['remote_addr'] = '127.0.0.1'
    else: session['remote_addr'] = request.environ.get('HTTP_X_REAL_IP')

    #Read if there are any alerts and display if so
    try:
        with lock:
            with open('alerts.txt', 'r') as f:
                alerts = [l.strip() for l in f.readlines()]
    except:
        alerts = []
    
    for alert in alerts:
        flash(alert)

    #Get tournaments user has access to
    userData = db_worker.db.child('Users').child(uid).get().val()
    tournaments = {}
    if userData:
        try:
            for t in userData.split(',')[app.config['TOURNAMENT_START_IDX']:]:
                tournaments[t] = db_worker.firebase_data.tournaments[t]
        except Exception as e:
            print(e)
        
    #Check if user is TO
    if 'isTO' in session and session['isTO'] == 1: isTO = True
    else: isTO = False 

    #Render template
    json_tourneys = json.dumps(tournaments)
    return render_template('index.html', tournaments=tournaments, json_tourneys=json_tourneys, isTo=isTO, userTier=userTier, email=email, discordID=discordID, discordUsername=discordUsername)

'''
Upload
'''
########################################
# Creates a signed URL for uploading
# The purpose is to upload to GCS directly, 
# instead of uploading to the server then to GCS.
########################################
@app.route("/signedUploadURL", methods=["POST"])
def getNewSignedURL():
    #Get args from ajax
    tournament = request.form.get('tourney').strip()
    subTournament = request.form.get('subTourney').strip()
    video = request.form.get('video')
    notes = request.form.get('notes')
    
    if session['userTier'] == 0 and video == '1': video == '0' #server side check

    #If tourney/subtourney is none, specify that
    if not tournament: tournament = 'None'
    if not subTournament: subTournament = 'None'
    ext = request.form.get('ext')

    #Create signed URL
    presigned_upload_url = gcs_worker.generate_upload_signed_url_v4(method='put', tournament=tournament, subTournament=subTournament, ext=ext, video=video, notes=notes)

    #Send in to ajax
    return jsonify({'presigned_url': presigned_upload_url})


########################################
# Adds a new sub tournament to firebase
########################################
@app.route("/newSubTourney", methods=["POST"])
def createNewSubtournament():
    try:
        #Get args from ajax
        tournament = request.form.get('tourney').strip()
        newSubTournament = request.form.get('newSubTourney').strip()
        
        #Update firebase
        current_data = db_worker.db.child('tournaments').child(tournament).get().val()
        current_data += f'|{newSubTournament}'
        data = {tournament: current_data}
        db_worker.db.child('tournaments').update(data)


        #Send in to ajax
        return jsonify({'result': 1})
    except:
        return jsonify({'result': -1})


'''
Viewing
'''
########################################
# Saves filters for viewing replays
########################################
def check_and_store_differences(playerFilters, characterFilters, stageFilter, selected_tourney, selected_subTourney, download_slp_files, download_video_files):
    #First, create blank items where needed
    if not playerFilters: playerFilters = [None] * 4
    if not characterFilters: characterFilters = [None] * 4
    if not stageFilter or stageFilter.lower() == 'none': stageFilter = None
    if not selected_tourney: selected_tourney = None
    if not selected_subTourney: selected_subTourney = None
    if not download_slp_files: download_slp_files = 0
    if not download_video_files: download_video_files = 0
    

    #Last, set new session data
    for i in range(4):
        try:
            session[f'p{i}filter'] = playerFilters[i]
        except:
            session[f'p{i}filter'] = None

        try:
            session[f'char{i}filter'] = characterFilters[i]
        except:
            session[f'char{i}filter'] = None

    session['stageFilter'] = stageFilter
    session['tourney'] = selected_tourney
    session['subTourney'] = selected_subTourney
    session['downloadSLPFiles'] = download_slp_files
    session['downloadVideoFiles'] = download_video_files

########################################
# Page for viewing replays
# Gets the stored filters if there are any
# Gets the replays to display
# Renders the page
########################################
@app.route('/replays')
async def searchReplays():
    #Update user session data
    updateUserSessionData()
    if not 'HTTP_X_REAL_IP' in request.environ: session['remote_addr'] = '127.0.0.1'
    else: session['remote_addr'] = request.environ.get('HTTP_X_REAL_IP')

    #Get any filters if there are any
    try:
        playerFilters = [request.args.get('playerOneFilter'), request.args.get('playerTwoFilter'), request.args.get('playerThreeFilter'), request.args.get('playerFourFilter')]
        playerFilters = [None if p == '' else p for p in playerFilters ]
        playerFilters = [p.lower() for p in playerFilters if p]
    except:
        playerFilters = []

    try:
        characterFilters = [request.args.get('char1'), request.args.get('char2'), request.args.get('char3'), request.args.get('char4')]
        characterFilters = [None if c == '' or c.lower() == 'all' else c for c in characterFilters ]
        characterFilters = [c for c in characterFilters if c]
    except:
        characterFilters = []
    
    try:
        stageFilter = request.args.get('stageInput')
        if stageFilter == 'Stage Filter' or stageFilter == 'ALL': stageFilter = None
    except:
        stageFilter = None

    try:
        selected_tourney = request.args.get('tourneyInput')
        selected_subTourney = request.args.get('subTourneyInput')
        if selected_tourney == 'All' or '': selected_tourney = None
        if selected_subTourney == 'All' or '': selected_subTourney = None
    except:
        selected_tourney = None
        selected_subTourney = None

    try:
        download_slp_files = int(request.args.get('downloadSLPFiles'))
    except:
        download_slp_files = 1

    try:
        download_video_files = int(request.args.get('downloadVideoFiles'))
    except:
        download_video_files = 0

    #Get tournament data
    tourneys = db_worker.firebase_data.tournaments
    main_tourneys = list(tourneys.keys())
    num_tourneys=len(tourneys)
    

    #Get the data, and prepare it for the table to view
    check_and_store_differences(playerFilters, characterFilters, stageFilter, selected_tourney, selected_subTourney, download_slp_files, download_video_files)
    if all(p is None for p in playerFilters) and all(c is None for c in characterFilters) and not stageFilter and not selected_tourney and not selected_subTourney:
        replayData = db_worker.firebase_data.generic_data
        clipsSize = min(db_worker.firebase_data.generic_page_size, len(db_worker.firebase_data.clips_data))
        clipData = db_worker.firebase_data.clips_data[-clipsSize:]
    else:
        replayData, clipData = db_worker.firebase_data.get_replays(playerFilters, 
                                                        characterFilters, 
                                                        stageFilter, 
                                                        selected_tourney,
                                                        selected_subTourney)

    #Convert clip data to easy-to-read dict for javascript
    jsonClipData = {}
    for idx, v in enumerate(clipData):
        jsonClipData[idx] = v
    jsonClipData = json.dumps(jsonClipData)

    #Get character and stage data to send in
    charData = db_worker.firebase_data.get_character_data()
    stageData = db_worker.firebase_data.get_stage_data()

    #Reassign these to send back for button text
    playerFilters = []
    characterFilters = []
    for i in range(4):
        if not session.get(f'p{i}filter'):
            playerFilters.append('')
        else:
            playerFilters.append(session.get(f'p{i}filter'))

        if not session.get(f'char{i}filter'):
            characterFilters.append('')
        else:
            characterFilters.append(session.get(f'char{i}filter'))

    stageFilter = session.get('stageFilter') if session.get('stageFilter') else 'ALL'
    selected_tourney = session.get('tourney') if session.get('tourney') else 'All'
    selected_subTourney = session.get('subTourney') if session.get('subTourney') else 'All'
    characterFilters = ['ALL' if c == '' else c for c in characterFilters]

    if 'discordID' in session: discordID = session['discordID']
    else: discordID = 0
    if 'discordUsername' in session: discordUsername = session['discordUsername']
    else: discordUsername = 0

    #Render template
    return render_template('search_replays.html', replay_data = replayData,
                                                    clip_data = jsonClipData,
                                                    num_chars = len(charData),
                                                    char_data = charData,
                                                    num_stages = len(stageData),
                                                    stage_data = stageData,
                                                    character_filters = characterFilters,
                                                    player_filters = playerFilters,
                                                    stage_filter = stageFilter,
                                                    main_tourneys = main_tourneys,
                                                    tournaments = tourneys,
                                                    num_tourneys = num_tourneys,
                                                    prior_tourney = selected_tourney,
                                                    prior_subTourney = selected_subTourney,
                                                    download_slp_files = download_slp_files,
                                                    download_video_files = download_video_files,
                                                    discordID = discordID,
                                                    discordUsername = discordUsername)

'''
Download
'''
########################################
# Post request for downloading items
########################################
@app.route("/downloadItems",methods=["POST"])
# @check_token
def downloadFilterAll():
    #Get form info
    requestedItems = request.form.get('requestedItems')[1:-1].replace('"', '').split(',')
    currentTime = int(request.form.get('currentTime'))
    numVideoFiles = len([f for f in requestedItems if '.mp4' in f])

    #check if within limits to do action
    result = canDoAction(len(requestedItems))
    if not result.json['result']:
        return jsonify({'result': 2})

    #Basic checks to make sure request isn't enormous
    if len(requestedItems) == 0:
        flash("There are no items to download")
        # return redirect(url_for("searchReplays"))
        return jsonify({'result': -2})
    if len(requestedItems) > 500:
        flash("Sorry, there is a maximum download size of 500 files")
        # return redirect(url_for("searchReplays"))
        return jsonify({'result': -3})
    if numVideoFiles > 50:
        flash("Sorry, there is a maximum of 50 video files in a single download")
        # return redirect(url_for("searchReplays"))
        return jsonify({'result': -4})

    if session['userTier'] == 0 and numVideoFiles > 0:
        flash("Sorry, only Patrons can download videos")
        return jsonify({'result': -4})

    #Check if the user wants to wait or wants an email
    sendEmail = request.form.get('email')
    if sendEmail == 'true': 
        email=session['email']
        gcs_worker.emailDownloadQ.put([requestedItems, currentTime, email])
    else: 
        email=None
        gcs_worker.smallDownloadQ.put([requestedItems, currentTime, email])
        gcs_worker.currentProgress[currentTime] = 'Waiting until other downloads finish'

    #Create firebase data and update
    numFiles = len(requestedItems)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dt%H%M%S")
    data = {timestamp: f'{numFiles},0'}
    db_worker.db.child('remoteAddrData').child(session['remote_addr'].replace('.', '_')).update(data)

    #If uid specified, then update there as well
    if 'uid' in session: db_worker.db.child('UIDs').child(session['uid']).update(data)

    #Update session counts
    session['dailyDownloads'] += numFiles
    session['totalDownloads'] += numFiles

    return jsonify({'result': 1})

########################################
# Polling endpoint for user while waiting
# Just sends back basic updates, or when
# upload to GCS is done, sends back that URL
########################################
@app.route("/pollDownload", methods=["POST"])
def pollDownload():
    try:
        currentTime = int(request.form.get('currentTime'))
        progress = gcs_worker.currentProgress[currentTime]

        return jsonify({'progress': progress})
    except:
        return jsonify({'progress': -1})


'''
Discord
'''

########################################
# Runs the user through the Discord
# OAuth screen again
########################################
@app.route('/discordAuth', methods=['POST'])
def discordAuth():
    return {'url': discord.create_session(scope="identify")}

########################################
# Callback used after OAuth to store
# Discord user ID in firebase + session
########################################
@app.route("/discordCallback/")
def discordCallback():
    try:
        #Get discord data
        data = discord.callback()
        discordUser = discord.fetch_user()
        discordUserName = f'{discordUser.name}#{discordUser.discriminator}'
        discordID = discordUser.id

        #Update discord ID if specified
        userData = db_worker.db.child('Users').child(session['uid']).get().val()
        userData = userData.split(',')
        userData[app.config['DISCORD_ID_IDX']] = str(discordID)
        userData[app.config['DISCORD_USER_IDX']] = discordUserName
        userData = ','.join(userData)

        #Set user data in firebase and session
        data = {session['uid']: userData}
        db_worker.db.child('Users').update(data)
        session['discordID'] = discordID
    except :
        pass
    
    redirect_to = data.get("redirect", "/")
    return redirect(redirect_to)

########################################
# Sends a support message to support channel
########################################
@app.route('/discordSupport', methods=['POST'])
def discordSupport():
    message = request.form.get('message')
    data = {'username': 'Website Support', 'avatar_url': "", 'content': message}
    headers = {'Content-type': 'application/json'}
    response = requests.post(app.config['DISCORD_SUPPORT_WEBHOOK'], headers=headers, json=data)

    
    return {"result": response.status_code}

########################################
# Creates a request in the highlights channel
########################################
@app.route('/discordHighlight', methods=['POST'])
def discordHighlight():
    try:
        #Get form data
        startTime = int(request.form.get('start'))
        endTime = int(request.form.get('end'))
        fps = int(request.form.get('fps'))
        resolution = '480p' if request.form.get('resolution') == 'Normal' else '720p'
        discordID = request.form.get('discordID')
        uid = request.form.get('uid')

        #Get slp file info
        slpFile = request.form.get('slpFile')
        tourney = slpFile.split('_')[0]
        subTourney = slpFile.split('_')[1]
        slpFilePath = os.path.join(gcs_worker.processed_folder, tourney, subTourney, f"Processed_{slpFile.split('_')[2]}.zip")
        fileName = f"Processed_{slpFile.split('_')[2]}.zip"

        #Get the user ID, name, and discriminator
        # url = 'https://discord.com/api/users/@me/channels'
        # data = {'recipient_id': str(discordID)}
        # headers = {'authorization' : f'Bot {app.config["DISCORD_BOT_TOKEN"]}'}
        # r = requests.post(url, json=data, headers=headers)
        # r_data = json.loads(r.text)
        # username = r_data['recipients'][0]['username']
        # discriminator = r_data['recipients'][0]['discriminator']
        discordUsername = request.form.get('discordUsername')

        #Set payload items
        payload = {
            "username": "MeleeHub",
            "content": f"!gif {startTime} {endTime} {fps} {resolution} {tourney} {subTourney} {uid} {discordID} {discordUsername}"
        }

        #With open file, send data
        with open(slpFilePath, "rb") as slpFileData:
            multipart = {"file": (fileName, slpFileData, "application/octet-stream")}
            requests.post(url=app.config['DISCORD_HIGHLIGHTS_WEBHOOK'], files=multipart, data=payload)
        
        return {"result": 1}
    except Exception as e:
        print(e)
        return {"result": -1}

    



'''
Authentication
'''

########################################
# Creates a new user with Firebase Auth
# with an email/password
########################################
@app.route('/signup', methods=['POST'])
def signup():
    #Get email and password from form, check they exist
    email = request.form.get('email').lower()
    password = request.form.get('password')
    if not email or not password: return {'result': -1, "message": 'Missing email or password, please fill in both fields and try again'}

    #Check if user wants to link discord
    linkDiscord = True if request.form.get('discord') == 'true' else False

    try:
        #Create a new user
        user = auth.create_user(email=email, password=password)

        #Update firebase
        data = {user.uid: f'{email},-1,0,0,0'}
        db_worker.db.child('Users').update(data)

        #Set current session data and check for patreon information
        setUserSessionData(email, password)
        gcs_worker.patreonQ.put(user.uid)
        
        if linkDiscord: return {'result': 2, 'url': discord.create_session(scope="identify")}
        else: return {'result': 1, 'message': f'Successfully created user {user.uid}'}
    
    #If value error, then didn't meet firebase auth's mysterious and unlisted criteria
    except ValueError as e:
        return {'result': -2, "message": 'Email and/or password does not meet criteria, please enter a password that is at least 6 characters long'}

    #User already exists
    except EmailAlreadyExistsError:
        return {'result': -3, "message": 'Email is already taken, please choose another one'}


########################################
# Signs a user in with a given email/pword
# If exception, assume credentials wrong
########################################
@app.route('/signin', methods=['POST'])
def signin():
    #First, get the email and password
    email = request.form.get('email')
    password = request.form.get('password')

    #if email or password is blank, return an error
    if email is None or password is None: return {'result': -1, "message": 'Invalid username or password'}

    #Try to authenticate, if it failed just reload page with generic error code
    try:
        setUserSessionData(email, password)
        return {'result': 1, 'message': f'Successfully logged in under {email}'}

    #Exception caught - print the error and then reload the page with generic error
    except HTTPError as e:
        return {'result': -2, "message": 'Invalid username or password'}


########################################
# Signs a user out. Removes session data
########################################
@app.route('/signout', methods=['POST'])
def signout():
    removeSessionData()
    return redirect(url_for('home'))

########################################
# Creates a reset password URL and add
# that email to the queue to send out
# Also remove session data
########################################
@app.route('/resetPassword', methods=['POST'])
def resetPassword():
    #Get info and verifyi t
    email = request.form.get('email')
    if not email: return{'result': -1, 'message': 'Please enter an email before trying to reset your password'}

    #If good, log user out and reset password
    removeSessionData()
    settings = auth.ActionCodeSettings(url='https://meleehub.gg', handle_code_in_app=False)
    reset_url = auth.generate_password_reset_link(email, action_code_settings=settings)
    contents = "Hello, below is a link to reset your password for meleehub.gg\n\
If you did not request this email, please ignore it.\n\n\
" + reset_url
    gcs_worker.emailQ.put([contents, email])
    return {'result': 1, 'message': f'Successfully sent an email to {email} to reset your password'}



'''
Session
'''
########################################
# Sets the current session data
# Starts by signing a user in
# Next, gets the uid
# Also get the email associated
########################################
def setUserSessionData(email, password):
    #Set the user session so webpage knows the user is logged in
    user = firebase_db.auth().sign_in_with_email_and_password(email, password)
    
    #Get uid/email
    decoded_token = auth.verify_id_token(user['idToken'])
    session['uid'] = decoded_token['uid']
    session['recheckLog'] = True
    session['email'] = user['email']

    #Get the user data (userTier/TO)
    userData = getUserData(decoded_token['uid'])
    if not userData: 
        session['userTier'] = 0
        session['isTO'] = 0
        session['discordID'] = 0
        session['discordUsername'] = 0
    else:
        session['userTier'] = int(userData.split(',')[app.config['USER_TIER_IDX']])
        session['isTO'] = int(userData.split(',')[app.config['IS_TO_IDX']])
        session['discordID'] = int(userData.split(',')[app.config['DISCORD_ID_IDX']])
        session['discordUsername'] = userData.split(',')[app.config['DISCORD_USER_IDX']]

    #If user tier is -1, just set it to 0 for the session. -1 means just signed up, need to check patreon
    if session['userTier'] == -1: session['userTier'] = 0

########################################
# Updates the user session data
# Gets the uid/token as well as tier/TO status
########################################
def updateUserSessionData():
    try:
        if not 'uid' in session:
            session['userTier'] = 0
            session['isTO'] = 0
        else:
            userData = getUserData(session['uid'])
            session['userTier'] = int(userData.split(',')[1])
            session['isTO'] = int(userData.split(',')[2])
    except:
        session['userTier'] = 0
        session['isTO'] = 0
    
    #If user tier is -1, just set it to 0 for the session. -1 means just signed up, need to check patreon
    if session['userTier'] == -1: session['userTier'] = 0

########################################
# Removes session data (uid/email/tier/isTO)
########################################
def removeSessionData():
    if 'uid' in session: session.pop('uid')
    if 'email' in session: session.pop('email')
    session['isTO'] = 0
    session['userTier'] = 0
    session['recheckLog'] = True

########################################
# Gets user tier/TO status from firebase
########################################
def getUserData(UID):
    userData = db_worker.db.child('Users').child(UID).get().val()
    return userData


'''
Firebase
'''
########################################
# Updates firebase upload count for a user
# when that user passes upload checks
########################################
@app.route("/updateFirebase", methods=["POST"])
def updateFirebaseUploadCount():    
    #Get the number of files and the timestamp
    numFiles = int(request.form.get('numFiles'))
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dt%H%M%S")

    #Set the data and update by remote addr
    data = {timestamp: f'{numFiles},1'}
    db_worker.db.child('remoteAddrData').child(session['remote_addr'].replace('.', '_')).update(data)

    #If uid specified, then update there as well
    if 'uid' in session:
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%dt%H%M%S")
        data = {timestamp: f'{numFiles},1'}
        db_worker.db.child('UIDs').child(session['uid']).update(data)

    #Update session counts
    session['dailyUploads'] += numFiles
    session['weeklyUploads'] += numFiles
    session['totalUploads'] += numFiles

    return jsonify({'result': 1})
    
########################################
# Gets the activity from the last day
########################################
def getFirebaseActivityLastDay(remote_addr=None, uid=None):
    #If UID is specified, get data from that. If not, use the source IP
    if uid: 
        activity = db_worker.db.child('UIDs').child(uid).get().val()
    elif remote_addr: 
        activity = db_worker.db.child('remoteAddrData').child(remote_addr.replace('.', '_')).get().val()

    #Initialize data
    downloads, uploads, weeklyDownloads, weeklyUploads, totalDownloads, totalUploads = 0, 0, 0, 0, 0, 0
    daily_cutoff = datetime.timedelta(hours=24)
    weekly_cutoff = datetime.timedelta(weeks=1)
    now = datetime.datetime.utcnow()
    foundOldestDailyTimestamp = False
    foundOldestWeeklyTimestamp = False
    oldestDailyTimestamp = now
    oldestWeeklyTimestamp = now

    #Go through each item, check if timestamp was last 24 hours
    if activity:
        for k, v in activity.items():
            v_split = v.split(',')
            count = int(v_split[0])
            actionType = int(v_split[1])
            timestamp = datetime.datetime.strptime(k, "%Y%m%dt%H%M%S")

            if actionType == 0: #download
                totalDownloads += count
            elif actionType == 1: #upload
                totalUploads += count

            #If diff is less than 24 hours, count it
            if (now - timestamp < daily_cutoff):
                #Save the oldest timestamp to invalidate if that time shows up in the user session
                if not foundOldestDailyTimestamp:
                    oldestDailyTimestamp = timestamp

                if actionType == 0: #download
                    downloads += count
                elif actionType == 1:
                    uploads += count

            if (now - timestamp < weekly_cutoff):
                #Save the oldest timestamp to invalidate if that time shows up in the user session
                if not foundOldestWeeklyTimestamp:
                    oldestWeeklyTimestamp = timestamp

                if actionType == 0: #download
                    weeklyDownloads += count
                elif actionType == 1:
                    weeklyUploads += count
            
    return downloads, uploads, weeklyDownloads, weeklyUploads, totalDownloads, totalUploads, oldestDailyTimestamp, oldestWeeklyTimestamp


'''
Contact/Support
'''
########################################
# Sends an email to me
########################################
@app.route("/sendEmail", methods=["POST"])
#name, email, message
def sendEmail():    
    message = request.form.get('message')
    discordID = request.form.get('discordID')
    toSend = message + f'\nMy discord information is {discordID}'
    return redirect(f'mailto:meleehubinfo@gmail.com?subject=MeleeHub%20Support&body={toSend}')



# @app.route('/', defaults={'req_path': ''})
# @app.route('/<path:req_path>')
# def dir_listing(req_path):
#     BASE_DIR = os.path.join(os.getcwd(), 'static')

#     # Joining the base and the requested path
#     abs_path = os.path.join(BASE_DIR, req_path)

#     # Return 404 if path doesn't exist
#     if not os.path.exists(abs_path):
#         return abort(404)

#     # Check if path is a file and serve
#     if os.path.isfile(abs_path):
#         return send_file(abs_path)

#     # Show directory contents
#     files = os.listdir(abs_path)
#     return render_template('files.html', files=files)

    
if __name__ == "__main__":
    #threading.Thread(target=gcs_worker.monitor_data).start()
    #app.run(host="0.0.0.0", port=80, debug=False)
    serve(app, threads=(multiprocessing.cpu_count() * 2 + 1) - 3) # - 3 for 3 threads to monitor data in gcs_worker
