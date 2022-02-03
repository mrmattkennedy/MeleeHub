import os
import threading
import time
import configparser

import slp_to_mp4
import zipfile
import pyrebase


class VideoProcessor:
    def __init__(self):
        self.current_dir = os.path.dirname(os.path.realpath(__file__))
        self.videos_dir = os.path.join(self.current_dir, os.pardir, 'static', 'videos')
        self.processed_folder = os.path.join(self.current_dir, os.pardir, 'static', 'processed')
        if not os.path.isdir(self.videos_dir): os.mkdir(self.videos_dir)

        self.processing_threads = []
        #self.lock = threading.RLock()
        self.max_threads = 5
        self.active_threads = 0
        self.thread_pool = [None]*self.max_threads

        self.get_replay_list()

    def get_replay_list(self):
        #Read config file into parser
        conf_reader = configparser.ConfigParser()
        conf_reader.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'configs', 'config.cfg'))

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
        firebase_db = pyrebase.initialize_app(config)
        db = firebase_db.database()
        
        #Get all replays that have specified video creation
        replayList = db.child('replayData').get().val()
        self.replaysToProcess = []
        for k, v in replayList.items():
            if v[-1] == '1':
                self.replaysToProcess.append(f'Processed_{k}.zip')


    def process_videos(self):
        for dir_tuple in os.walk(self.processed_folder):
            #Find if depth matches where .slp files are, if so process
            parent_dirs = dir_tuple[0].replace('/', '\\')
            if len(parent_dirs.split('\\')) == 8:
                #Get paths related to current directory in walk
                full_parent_path = os.path.join(self.current_dir, os.pardir, parent_dirs)
                tourney = parent_dirs.split('\\')[-2]
                subTourney = parent_dirs.split('\\')[-1]

                #Check if folders exist
                if not os.path.isdir(os.path.join(self.videos_dir, tourney)): os.mkdir(os.path.join(self.videos_dir, tourney))
                if not os.path.isdir(os.path.join(self.videos_dir, tourney, subTourney)): os.mkdir(os.path.join(self.videos_dir, tourney, subTourney))

                #Check if video exists for each file
                for slp_file in dir_tuple[2]:
                    video_path = os.path.join(self.videos_dir, tourney, subTourney, slp_file[:-4] + '.mp4')
                    slp_file_path = os.path.join(self.current_dir, 'processing', slp_file[:-4] + '.slp')

                    #If not a video associated and not in the queue directory to process, then process it
                    if slp_file in self.replaysToProcess and not os.path.isfile(video_path) and not os.path.isfile(slp_file_path):
                        #Process file if no associated video file
                        zip_path = os.path.join(full_parent_path, slp_file)

                        #Extract slp file to processing folder
                        with zipfile.ZipFile(zip_path) as z:
                            z.extractall(os.path.join(self.current_dir, 'processing'))

                        #Wait until thread is available
                        thread_spot_found = False
                        while not thread_spot_found:
                            for i in range(len(self.thread_pool)):
                                if not self.thread_pool[i] or not self.thread_pool[i].is_alive():
                                    self.thread_pool[i] = threading.Thread(target=slp_to_mp4.main, args=(slp_file_path, os.path.join(self.videos_dir, tourney, subTourney)))
                                    self.thread_pool[i].start()
                                    thread_spot_found = True
                                    break
                            
                            if thread_spot_found: break
                            time.sleep(1)

                        #Increment counter and start thread
                        # with self.lock: self.active_threads += 1
                        


if __name__ == '__main__':
    vp = VideoProcessor()
    vp.process_videos()
