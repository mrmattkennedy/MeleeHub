import os
import sys
import time
import pytz
import shutil
import string
import zipfile
import hashlib
import smtplib
import datetime
import threading
import configparser
from multiprocessing import Queue
from email.mime.text import MIMEText

from google.cloud import storage
from firebase_worker import Firebase_Worker
import patreon_utils as patreon



class GCS_Worker:
    ########################################
    # Constructor for GCS_Worker
    # Loads in GCS credentials json
    # Creates objects for upload/download management
    ########################################
    def __init__(self, db_worker):
        self.service_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'configs', 'meleehub-credentials.json')

        #Read config file into parser
        self.conf_reader = configparser.ConfigParser()
        self.conf_reader.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'configs', 'config.cfg'))
        self.bucket_name = self.conf_reader.get('gcs', 'bucket_name')

        #Create storage client/bucket object
        self.storage_client = storage.Client.from_service_account_json(self.service_file_path)
        self.bucket = self.storage_client.bucket(self.bucket_name)

        #Set paths for local processing
        self.processed_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static', 'processed')
        self.unprocessed_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static', 'unprocessed')
        self.downloads_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static', 'downloads')
        self.videos_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static', 'videos')

        #Threading/progress objects
        self.currentProgress = {}
        self.emailQ = Queue()
        self.lock = threading.RLock()

        #Download manager/queue objects
        self.smallDownloadQ = Queue()
        self.emailDownloadQ = Queue()
        self.num_small_downloads = 0
        self.num_email_downloads = 0
        self.small_downloads_max = 5
        self.email_downloads_max = 10
        self.small_downloads_wait_time = 60*10
        self.email_downloads_wait_time = 60*10

        #Firebase auth/worker
        self.new_user = True
        self.num_users = 0
        self.db_worker = db_worker
        self.key_size = 8

        #Flag used for updating all patreon data
        self.updateAllUsers = False
        self.patreonQ = Queue()
        self.patreon_emails = patreon.get_emails()

        #Clips data
        self.clips_db = self.conf_reader.get('gcs', 'clips_fname')
        self.clips_data = []
        self.updateClipsData()

        #Start threads
        threading.Thread(target=self.monitor_data).start()
        threading.Thread(target=self.small_download_manager).start()
        threading.Thread(target=self.email_download_manager).start()

    def generate_upload_signed_url_v4(self, method, object_name=None, ext=None, tournament=None, subTournament=None, video=None, notes=None):
        """Generates a v4 signed URL for uploading a blob using HTTP PUT.

        Note that this method requires a service account key file. You can not use
        this if you are using Application Default Credentials from Google Compute
        Engine or from the Google Cloud SDK.
        """

        #Use content type, seems I don't need it, leaving in case that changes
        try:
            assert ext in ['.zip', '.slp']
            if ext == '.zip' and method == 'put': content_type = 'application/zip'
            elif ext == '.slp' and method == 'get': content_type = 'application/octet-stream'
        except:
            return -1
        
        #Create a random key for file upload name
        if method == 'put':
            random_data = os.urandom(128)
            extra_key = hashlib.md5(random_data).hexdigest()[:self.key_size]
            blob_name = f'unprocessed/{tournament}_{subTournament}_{video}_{notes}_' + datetime.datetime.utcnow().strftime("Unprocessed_%Y%m%dt%H%M%S%f-") + extra_key
          
        elif method == 'get':
            blob_name = f'downloads/{object_name}'

        #Create the signed URL and return
        blob = self.bucket.blob(blob_name)
        url = blob.generate_signed_url(
            version="v4",
            # This URL is valid for 5 minutes
            expiration=datetime.timedelta(minutes=60*24),
            # Allow PUT requests using this URL.
            method=method
        )
        return url


    ########################################
    # All this method does is download files
    # from the 'unprocessed' folder of the
    # GCS bucket.
    # Additionally, because some idiot (me)
    # made this, and doesn't fully understand
    # XHR requests and form data, there are
    # webkitformboundary tags on all uploads.
    # So manually remove those bytes and 
    # store the file locally
    ########################################
    def store_replays_locally(self):
        #For each file, download and process
        if not os.path.isdir(self.unprocessed_folder): os.mkdir(self.unprocessed_folder)
        for blob in self.storage_client.list_blobs(self.bucket_name, prefix='unprocessed'):
            if blob.name == 'unprocessed/': continue

            #Get contents and file name
            slp_contents = blob.download_as_string()
            fName = blob.name.split('/')[-1]

            #Remove beginning webkitformboundary bytes
            current_idx = 0
            for i in range(4):
                current_idx = slp_contents.index(b'\r\n', current_idx+2)
            slp_contents = slp_contents[current_idx+2:]

            #Remove ending webkitformboundarybytes
            end_idx = slp_contents.index(b'------')
            slp_contents = slp_contents[:end_idx]

            #Write to local file
            with open(os.path.join(self.unprocessed_folder, fName + '.slp'), 'wb') as f:
                f.write(slp_contents)

            #Delete the blob when done
            blob.delete()

    ########################################
    # This function processes files in the 
    # local 'unprocessed' folder. The reason
    # these functions are split is for optimization
    # of slippi.js batch processing.
    ########################################
    def process_downloaded_replays(self):
        dataWasPresent = False
        slpPaths = []

        #Get slp data
        for slp_file in os.listdir(self.unprocessed_folder):
            #Get data for slp replay
            dataWasPresent = True
            tourney = slp_file.split('_')[0]
            subTourney = slp_file.split('_')[1]
            video = slp_file.split('_')[2]
            notes = slp_file.split('_')[3]
            fName = os.path.basename(slp_file)

            #Append to list
            slpPaths.append([os.path.join(self.unprocessed_folder, slp_file), fName, tourney, subTourney, video, notes])
        
        #Store data in firebase if new data
        if slpPaths: self.db_worker.save_slp_files_nodejs(slpPaths)

        #Move files into zips and copy to processed folder instead
        for slp_file in os.listdir(self.unprocessed_folder):
            tourney = slp_file.split('_')[0]
            subTourney = slp_file.split('_')[1]
            new_name = 'Processed_' + slp_file.split('_')[-1][:-4]

            #Create path if necessary
            if not os.path.isdir(self.processed_folder): os.mkdir(self.processed_folder)
            if not os.path.isdir(os.path.join(self.processed_folder, tourney)): os.mkdir(os.path.join(self.processed_folder, tourney))
            if not os.path.isdir(os.path.join(self.processed_folder, tourney, subTourney)): os.mkdir(os.path.join(self.processed_folder, tourney, subTourney))

            #Write into zip
            new_zip = zipfile.ZipFile(os.path.join(self.processed_folder, tourney, subTourney, new_name + '.zip'), "w", zipfile.ZIP_DEFLATED)
            new_zip.write(os.path.join(self.unprocessed_folder, slp_file), new_name + '.slp')
            new_zip.close()

            #Delete old file
            os.remove(os.path.join(self.unprocessed_folder, slp_file))

        return dataWasPresent
    

    ########################################
    # Creates a single download .zip file
    # Uploads to GCS and sends the signed URL
    # back to user for downloading
    ########################################
    def create_download_specific_replays_from_local(self, replayList, currentTimeKey, email=False):
        #Create a downloads folder
        new_folder_name = datetime.datetime.utcnow().strftime("Download_%Y%m%dt%H%M%S%f")
        if not os.path.isdir(self.downloads_folder): os.mkdir(self.downloads_folder)
        tmp_download_folder = os.path.join(self.downloads_folder, new_folder_name)
        os.mkdir(tmp_download_folder)

        #Create a new zip file to upload
        new_zip_name = os.path.join(tmp_download_folder, f'{new_folder_name}.zip')
        zip_to_upload = zipfile.ZipFile(new_zip_name, 'w', zipfile.ZIP_DEFLATED)

        with self.lock:
            self.currentProgress[currentTimeKey] = 'Zipping files together'

        #Log data to firebase
        # timestamp = datetime.datetime.utcnow().strftime("%Y%m%dt%H%M%S")
        # data = {timestamp: f'{len(replayList)},0'}
        # self.db_worker.db.child('remoteAddrData').child(remote_addr.replace('.', '_')).update(data)

        #Next step is to download each file specified by user
        for i, replay_zipFile in enumerate(replayList):
            tourney = replay_zipFile.split('_')[0]
            subTourney = replay_zipFile.split('_')[1]
            blobName = 'Processed_' + replay_zipFile.split('_')[2]

            fileExists = False
            #Move zip file into folder to work with - idk if there is a lock on file resources or something that will cause errors while copying so just retry a lot
            while True:
                try:
                    if blobName.endswith('.zip'): replay_path = os.path.join(self.processed_folder, tourney, subTourney, blobName)
                    else: replay_path = os.path.join(self.videos_folder, tourney, subTourney, blobName)

                    #Check if file exists
                    if not os.path.exists(replay_path): break

                    slp_zip_path = os.path.join(tmp_download_folder, blobName)
                    shutil.copy(replay_path, slp_zip_path)
                    fileExists = True
                    break

                except Exception as e:
                    print(e)
                    time.sleep(0.01)
            

            if not fileExists: continue
            #After download, extract each slp file and delete the zip
            if blobName.endswith('.zip'):
                with zipfile.ZipFile(slp_zip_path, 'r') as zip_ref:
                    slp_file_from_zip = zip_ref.namelist()[0]
                    zip_ref.extractall(tmp_download_folder)
            else:
                slp_file_from_zip = blobName

            #Put file into zip and delete files
            name_in_zip = f'MeleeHub_{tourney}_{subTourney}_{slp_file_from_zip.split("_")[1]}'
            zip_to_upload.write(os.path.join(tmp_download_folder, slp_file_from_zip), name_in_zip)
            if blobName.endswith('.zip'): os.remove(slp_zip_path)
            os.remove(os.path.join(tmp_download_folder, slp_file_from_zip))

            #Update progress
            # self.currentProgress[currentTimeKey] = round(((i+1)/len(replayList)) * 100, 2)

        #After all slp files saved in zip, close and get size
        zip_to_upload.close()

        #Update info
        with self.lock: self.currentProgress[currentTimeKey] = 'Creating download link'

        #Change chunk size and retry
        blob = self.bucket.blob(f'downloads/{new_folder_name}.zip', chunk_size=1024*2048)
        blob.upload_from_filename(new_zip_name)

        #Get signed download URL
        get_url = self.generate_upload_signed_url_v4(object_name=f'{new_folder_name}.zip', method='get', ext='.zip')
        with self.lock: self.currentProgress[currentTimeKey] = get_url

        #Remove that folder
        shutil.rmtree(tmp_download_folder)

        #Put email in queue if specified
        if email: 
            contents = "Hello, below is the requested download from meleehub.gg\n\
The link will be available for 24 hours.\n\
Thank you for your continued support :)\n\n\
" + get_url
            self.emailQ.put([contents, email])


        #Update counters
        if not email: 
            with self.lock: self.num_small_downloads -= 1
        else:
            with self.lock: self.num_email_downloads -= 1

        #return get_url


    
    ########################################
    # Download new clips-db file
    ########################################
    def updateClipsData(self):
        try:
            with self.lock:
                blob = self.bucket.get_blob(self.clips_db)
                blob.download_to_filename(self.clips_db)

                with open(self.clips_db, 'r') as f:
                    self.db_worker.firebase_data.clips_data = [l.strip().split(',') for l in f]
        except:
            self.db_worker.firebase_data.clips_data = []


    ########################################
    # Sends all emails in the email queue
    # There are only 2 types of emails:
    # password resets and download links
    ########################################
    def sendEmails(self):
        while not self.emailQ.empty():
            #Get items and create MIMEText msg
            items = self.emailQ.get()
            msg = MIMEText(items[0])
            recipient = items[1]

            #Check if reset email or download email, change subject accordingly
            if 'reset' in items[0].lower(): msg['Subject'] = 'MeleeHub Password Reset'
            elif 'patrons' in items[0].lower(): msg['Subject'] = 'Thanks for your support to MeleeHub!'
            else: msg['Subject'] = 'MeleeHub Download Ready'

            #Set to/from fields
            msg['From'] = 'meleehubinfo@gmail.com'
            msg['To'] = recipient

            #Create smtp server
            s = smtplib.SMTP('smtp.gmail.com', 587)
            s.starttls()
            s.login("meleehubinfo@gmail.com", self.conf_reader.get('email', 'password'))

            #Send mail and quit
            s.sendmail('meleehubinfo@gmail.com', recipient, msg.as_string())
            s.quit()

    ########################################
    # Checks patreon emails. This sometimes
    # times out on the patreon side for some
    # reason, not sure why.
    ########################################
    def checkPatreonEmails(self):
        try:
            self.patreon_emails = patreon.get_emails()
        except:
            return

        #Get list of users from firebase
        while not self.patreonQ.empty():
            uid = self.patreonQ.get()
            
            #Get user data from uid
            user_data = self.db_worker.db.child('Users').child(uid).get().val()
            userDataSplit = user_data.split(',')
            email = userDataSplit[0]
            extraInfo = ','.join(userDataSplit[2:])

            #Get patreon info
            try:
                if email not in self.patreon_emails: newTier = 0 
                else: newTier = self.patreon_emails[email]
            except:
                continue
            if newTier > 0:
                contents = "Hello, I just wanted to say thank you so much for the support!\n\
This project is not cheap or easy and is entirely possible thanks to Patrons like yourself :)\n\
If you are having any issues on the website, please reach out with the contact information at the bottom of the home page, and I'll get back to you ASAP\n\n\
Thanks again!"
                self.emailQ.put([contents, email])

            #Update data in firebase
            data = {uid: f'{email},{newTier},{extraInfo}'}
            self.db_worker.db.child('Users').update(data)

        if self.updateAllUsers:
            users = self.db_worker.db.child('Users').get().val()
            self.num_users = len(users)
            for k, v in users.items():
                #Get data for user
                userDataSplit = v.split(',')
                email = userDataSplit[0]
                oldTier = userDataSplit[1]
                extraInfo = ','.join(userDataSplit[2:])

                #Get patreon info
                if email not in self.patreon_emails: newTier = 0 
                else: newTier = self.patreon_emails[email]

                if newTier > 0 and int(newTier) != int(oldTier):
                    contents = "Hello, I just wanted to say thank you so much for the support!\n\
    This project is not cheap or easy and is entirely possible thanks to Patrons like yourself :)\n\
    If you are having any issues on the website, please reach out with the contact information at the bottom of the home page, and I'll get back to you ASAP\n\n\
    Thanks again!"
                    self.emailQ.put([contents, email])

                #Update data in firebase
                data = {k: f'{email},{newTier},{extraInfo}'}
                self.db_worker.db.child('Users').update(data)

            self.updateAllUsers = False
                

    ########################################
    # Cleans up old keys used for download 
    # polling after 24 hours
    ########################################
    def checkOldKeys(self):
        keysToDelete = []
        now = datetime.datetime.utcnow()
        cutoff = datetime.timedelta(hours=24)
        with self.lock:
            for k in self.currentProgress.keys():
                if now - datetime.datetime.fromtimestamp(int(str(k)[:-3])) >= cutoff:
                    keysToDelete.append(k)

            for k in keysToDelete:
                self.currentProgress.pop(k, None)


    ########################################
    # Manages waiting downloads
    # Max of 5 at a time, or wait 5 minutes max.
    ########################################
    def small_download_manager(self):
        while True:
            try:
                #Get items from queue
                replayList, currentTimeKey, email = self.smallDownloadQ.get()

                count = 0
                #Wait until num of items < max
                while True:
                    with self.lock:
                        if self.num_small_downloads < self.small_downloads_max:
                            break
                    time.sleep(1)
                    count += 1

                    if count > self.small_downloads_wait_time: break
                
                #Create new thread to create download
                threading.Thread(target=self.create_download_specific_replays_from_local, args=(replayList, currentTimeKey, email)).start()
                with self.lock: self.num_small_downloads += 1

            except:
                pass

            finally:
                time.sleep(1)

    ########################################
    # Manages email downloads (usually large)
    # Max of 5 at a time, or wait 5 minutes max.
    ########################################
    def email_download_manager(self):
        while True:
            try:
                #Get items from queue
                replayList, currentTimeKey, email = self.emailDownloadQ.get()

                count = 0
                #Wait until num of items < max
                while True:
                    with self.lock:
                        if self.num_email_downloads < self.email_downloads_max:
                            break
                    time.sleep(1)
                    count += 1

                    if count > self.email_downloads_wait_time: break
                
                #Create new thread to create download
                threading.Thread(target=self.create_download_specific_replays_from_local, args=(replayList, currentTimeKey, email)).start()
                with self.lock: self.num_email_downloads += 1

            except:
                pass

            finally:
                time.sleep(1)
            


    ########################################
    # General maintenance worker
    # Keeps track of new replays
    # Keeps track of new tournament information
    # Checks on old keys for progress polling
    # Checks old downloads in GCS
    # Checks patreon emails
    ########################################
    def monitor_data(self):
        newDataPresent = False
        patreonCounter = 0
        clipsCounter = 0
        tourneyCounter = 0

        while True:
            #Download and process replays - swapped to 2 functions so I can batch run replays through nodejs slippi
            self.store_replays_locally()
            newDataPresent = self.process_downloaded_replays()
            if newDataPresent: self.db_worker.firebase_data.update_data()

            #Update tournaments
            newTourneys = self.db_worker.firebase_data.updateTourneyData()

            #Update all tournaments from firebase - this is to check if any tourneys were deleted
            tourneyCounter += 1
            if tourneyCounter % 100 == 0 and tourneyCounter > 0:
                self.db_worker.firebase_data.updateAllTourneys()
                tourneyCounter = 0
            
            #Check if any old downloads that need to be deleted
            cutoff = datetime.timedelta(hours=24)
            now = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
            for blob in self.storage_client.list_blobs(self.bucket_name, prefix='downloads'):
                if blob.name == 'downloads/': continue
                creation_dt = blob.time_created
                if now - creation_dt > cutoff:
                    blob.delete()
            
            
            #Update counter, update patreon emails
            patreonCounter += 1
            if (patreonCounter % 150 == 0 and patreonCounter > 0):# or not self.patreonQ.empty():
                if (patreonCounter % 150 == 0 and patreonCounter > 0): 
                    self.updateAllUsers = True
                    patreonCounter = 0
                    
                self.checkPatreonEmails()

            #Check if time to update clips db
            clipsCounter += 1
            if clipsCounter % 150 == 0 and clipsCounter > 0:
                self.updateClipsData()
                clipsCounter = 0

            #Check keys in currentProgress and delete if necessary
            self.checkOldKeys()
            
            #Send any emails in the queue
            self.sendEmails()

            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            msg = '\r{}\tReplays:\t{:07d} | Clips: {:07d} | Users: {:06d} | Keys: {:04d}'.format(current_time, len(self.db_worker.firebase_data.data), len(self.db_worker.firebase_data.clips_data), self.num_users, len(self.currentProgress))
            sys.stdout.write(msg)
            sys.stdout.flush()

            time.sleep(0.5)

if __name__ == '__main__':
    gcs = GCS_Worker(None)

    gcs.db_worker = Firebase_Worker()
    #gcs.store_replays_locally()
    #gcs.process_downloaded_replays()
    #gcs.test()
    gcs.new_user = True
    #gcs.checkPatreonEmails()
    #gcs.store_replays_locally()
    gcs.process_downloaded_replays()