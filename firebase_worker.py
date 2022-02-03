import os
import re
from types import new_class
import zipfile
import copy
import time
import json
import string
import secrets
import datetime
import subprocess
import threading

from multiprocessing import Queue
from datetime import date

import pyrebase
import configparser

class Firebase_Worker:
    ########################################
    # Constructor for firebase worker
    # This class handles requests related to
    # firebase data
    ########################################
    def __init__(self):
        #Read config file into parser
        conf_reader = configparser.ConfigParser()
        conf_reader.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'configs', 'config.cfg'))

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
        self.db = firebase_db.database()
        
        #Lock for thread safe data
        self.lock = threading.RLock()
        self.firebase_data = self.Firebase_Data(self.db, self.lock)

        #UID for replace info
        self.currentUID = self.firebase_data.get_highest_uid()+1

    class Firebase_Data:
        ########################################
        # Constructor for firebase data
        # This class keeps track of actual data
        # in firebase
        ########################################
        def __init__(self, db, lock):
            self.generic_page_size = 2000
            self.filtered_page_size = 10000
            self.lock = lock
            self.db = db
            self.data = {}
            self.generic_data = {}
            self.tournaments = {}
            self.clips_data = {}
            self.tourneyQ = Queue()
            self.newItemsQ = Queue()
            self.current_idx = 0

            self.stream = self.db.child('tournaments').stream(self.tourneyStreamListener)

            self.charData = {0: "ALL",
                            1: "MARIO",
                            2: "FOX",
                            3: "CAPTAIN_FALCON",
                            4: "DONKEY_KONG",
                            5: "KIRBY",
                            6: "BOWSER",
                            7: "LINK",
                            8: "SHEIK",
                            9: "NESS",
                            10: "PEACH",
                            11: "POPO", 
                            12: "NANA",
                            13: "PIKACHU",
                            14: "SAMUS",
                            15: "YOSHI",
                            16: "JIGGLYPUFF",
                            17: "MEWTWO",
                            18: "LUIGI",
                            19: "MARTH",
                            20: "ZELDA", 
                            21: "YOUNG_LINK",
                            22: "DR_MARIO",
                            23: "FALCO",
                            24: "PICHU",
                            25: "GAME_AND_WATCH",
                            26: "GANONDORF",
                            27: "ROY"}

            self.stageData = {1: "ALL",
                            2: "FOUNTAIN_OF_DREAMS",
                            3: "POKEMON_STADIUM",
                            4: "PRINCESS_PEACHS_CASTLE",
                            5: "KONGO_JUNGLE",
                            6: "BRINSTAR",
                            7: "CORNERIA",
                            8: "YOSHIS_STORY",
                            9: "ONETT",
                            10: "MUTE_CITY",
                            11: "RAINBOW_CRUISE",
                            12: "JUNGLE_JAPES",
                            13: "GREAT_BAY",
                            14: "HYRULE_TEMPLE",
                            15: "BRINSTAR_DEPTHS",
                            16: "YOSHIS_ISLAND",
                            17: "GREEN_GREENS",
                            18: "FOURSIDE",
                            19: "MUSHROOM_KINGDOM",
                            20: "MUSHROOM_KINGDOM_II",
                            22: "VENOM",
                            23: "POKE_FLOATS",
                            24: "BIG_BLUE",
                            25: "ICICLE_MOUNTAIN",
                            26: "ICETOP",
                            27: "FLAT_ZONE",
                            28: "DREAM_LAND_N64",
                            29: "YOSHIS_ISLAND_N64",
                            30: "KONGO_JUNGLE_N64",
                            31: "BATTLEFIELD",
                            32: "FINAL_DESTINATION"}

            self.init_data()

        ########################################
        # Reads firebase replay data
        # This is a lot of data, so do this only
        # on load, otherwise use a queue to add
        # new items.
        # Also uses a "generic" dataset which is
        # for faster returns if the user hasn't 
        # specified filters
        ########################################
        def init_data(self):
            
            # Update the data
            try:
                retData = {}
                replays = self.db.child('replayData').get().val()
                if replays is None:
                    self.data = {}
                    self.generic_data = {}
                    return

                for k, v in replays.items():
                    data_split = v.split('|')
                    dataDict = {}

                    dataDict['uid'] = data_split[0]
                    dataDict['tourney'] = data_split[1]
                    dataDict['subTourney'] = data_split[2]
                    dataDict['notes'] = data_split[3]
                    dataDict['timestamp'] = data_split[4]
                    dataDict['duration'] = data_split[5]
                    dataDict['stage'] = self.map_stage_by_num(data_split[6])
                    for p in range(4):
                        dataDict[f'p{p}_char'] = self.map_character_by_num(data_split[(p*3) + 7])
                        dataDict[f'p{p}_code'] = data_split[(p*3) + 8]
                        dataDict[f'p{p}_name'] = data_split[(p*3) + 9]

                    dataDict['file'] = f'{data_split[1]}_{data_split[2]}_{k}'
                    video = data_split[-1]
                    if video == '0': 
                        dataDict['video'] = None
                    elif video == '1': 
                        video_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static', 'videos', data_split[1], data_split[2], 'Processed_' + k + '.mp4')
                        if os.path.isfile(video_path): dataDict['video'] = f'{data_split[1]}/{data_split[2]}/Processed_{k}.mp4'
                        else: dataDict['video'] = None
                    else:
                        dataDict['video'] = data_split[-1]
                    
                    retData[self.current_idx] = dataDict
                    self.current_idx += 1

                #Assign data
                self.data = retData
                retData = None

                # After getting data, create generic data dict of generic_page_size with the most recent items
                self.generic_data = list(self.data.values())[-self.generic_page_size:]
                self.generic_data = self.generic_data[::-1]

            except:
                self.data = {}
                self.generic_data = {}

        ########################################
        # Gets the current max UID
        ########################################
        def get_highest_uid(self):
            try: return max([int(v['uid'], 16) for v in self.data.values()])
            except: return -1

        ########################################
        # Updates replay data using a lock and queue
        ########################################
        def update_data(self):
            with self.lock:
                while not self.newItemsQ.empty():
                    item = self.newItemsQ.get()
                    k = list(item.keys())[0]
                    v = list(item.values())[0]

                    data_split = v.split('|')
                    dataDict = {}

                    dataDict['uid'] = data_split[0]
                    dataDict['tourney'] = data_split[1]
                    dataDict['subTourney'] = data_split[2]
                    dataDict['notes'] = data_split[3]
                    dataDict['timestamp'] = data_split[4]
                    dataDict['duration'] = data_split[5]
                    dataDict['stage'] = self.map_stage_by_num(data_split[6])
                    for p in range(4):
                        dataDict[f'p{p}_char'] = self.map_character_by_num(data_split[(p*3) + 7])
                        dataDict[f'p{p}_code'] = data_split[(p*3) + 8]
                        dataDict[f'p{p}_name'] = data_split[(p*3) + 9]

                    video_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static', 'videos', data_split[1], data_split[2], 'Processed_' + k + '.mp4')
                    if os.path.isfile(video_path): dataDict['video'] = f'{data_split[1]}/{data_split[2]}/Processed_{k}.mp4'
                    else: dataDict['video'] = None

                    dataDict['file'] = f'{data_split[1]}_{data_split[2]}_{k}'
                    self.data[self.current_idx] = dataDict
                    self.current_idx += 1

                #Update generic dataset as well
                self.generic_data = list(self.data.values())[:self.generic_page_size]
                self.generic_data = self.generic_data[::-1]


        
        ########################################
        # Update tournament data using a listener
        # When a new item comes in, put in on a queue
        ########################################
        def tourneyStreamListener(self, message):
            #If not initialized, do so
            if not self.tournaments:
                for t, subT in message["data"].items():
                    self.tournaments[t] = list(set(subT.split('|'))) #prevent duplicates
                
                #sort after done
                self.tournaments = {k: sorted(v) for k, v in self.tournaments.items()}

            #If not first time populating tourneys, append to queue and add all at once
            else:
                try:
                    for t, subT in message["data"].items():
                        self.tourneyQ.put({t: list(set(subT.split('|')))})
                except:
                    tourney = message['path'][1:]
                    self.tourneyQ.put({tourney: list(set(message["data"].split('|')))})

            
        ########################################
        # Updates the tournament data from the
        # queue. Sort data before return.
        ########################################
        def updateTourneyData(self):
            newTourneys = False
            while not self.tourneyQ.empty():
                with self.lock:
                    newTourneys = True
                    try:
                        item = self.tourneyQ.get()
                        t = list(item.keys())[0]
                        st_list = list(item.values())[0]

                        #Get items that already exist, if st doesn't then add it
                        if t in self.tournaments: 
                            existing_sts = self.tournaments[t]
                        else: 
                            existing_sts = []
                            self.tournaments[t] = []

                        for st in st_list:
                            if st not in existing_sts:
                                self.tournaments[t].append(st)

                    except:
                        pass
            
            #sort after done
            if newTourneys:
                self.tournaments = {k: sorted(v) for k, v in self.tournaments.items()}

            return newTourneys

        def updateAllTourneys(self):
            data = self.db.child('tournaments').get().val()
            newTourneyData = {}
            with self.lock:
                for k, v in data.items():
                    newTourneyData[k] = list(set(v.split('|')))

                self.tournaments = newTourneyData


        ########################################
        # Gets replays based on filters user has
        # specified. If there are none, just use
        # the generic data page.
        ########################################
        def get_replays(self, playerFilters, characterFilters, stageFilter, tourneyFilter, subTourneyFilter):            
            currentIdx = 0
            retItems = []
            
            #If not data, just return blank
            if not self.data: return {}

            for k in list(self.data.keys())[::-1]:
                v = self.data[k]
                #If there are no player filters then just continue with the data as is
                if playerFilters:
                    #Get all codes/names into one list
                    game_players = []
                    for p in range(4):
                        game_players.append(v[f'p{p}_code'].lower())
                        game_players.append(v[f'p{p}_name'].lower())

                    #If not all the specified filters are in the same list, then continue
                    if not all(any(p in g for g in game_players) for p in playerFilters):
                        #keysToReturn.append(idx)
                        continue

                #Go through character filters - if they don't all pass, remove the item from the return data
                if characterFilters:
                    #Get all codes/names into one list
                    game_players = []
                    for p in range(4):
                        game_players.append(v[f'p{p}_char'])

                    #If all the specified filters are in the same list, then add it
                    if not all(c in game_players for c in characterFilters):
                        continue
                
                #Go through each item, if stage doesn't match then remove it
                if stageFilter:
                    if stageFilter != v['stage']:
                        continue
                
                #Check if tourney filter matches
                if tourneyFilter:
                    if tourneyFilter != v['tourney']:
                        continue
                
                #Check if subtourney filter matches
                if subTourneyFilter:
                    if subTourneyFilter != v['subTourney']:
                        continue
                        
                retItems.append(self.data[k])

                #Get a max of 10,000 items
                currentIdx += 1
                if currentIdx >= self.filtered_page_size: break
            
            #Get related clips
            filteredClipsData = []
            filteredUIDs = [k['uid'] for k in retItems]
            for c in self.clips_data[::-1]:
                uid = c[1]
                if uid in filteredUIDs:
                    filteredClipsData.append(c)
                    if len(filteredClipsData) > self.filtered_page_size: break

            return retItems, filteredClipsData



        ########################################
        # Gets character data
        ########################################
        def get_character_data(self):
            return self.charData

        ########################################
        # Map character name by name
        ########################################
        def map_character_by_name(self, character):
            try:
                return [k for k, v in self.charData.items() if v == character][0]
            except:
                return -1

        ########################################
        # Map character name by idx
        ########################################
        def map_character_by_num(self, characterNum):
            if characterNum == 'N/A' or characterNum == '?': return characterNum
            try:
                return self.charData[int(characterNum)+1]
            except Exception as e:
                return -1

        ########################################
        # Get stage data
        ########################################
        def get_stage_data(self):
            return self.stageData
        
        ########################################
        # Map stage name by name
        ########################################
        def map_stage_by_name(self, stage):
            try:
                return [k for k, v in self.stageData.items() if v == stage][0]
            except:
                return -1

        ########################################
        # Map stage name by idx
        ########################################
        def map_stage_by_num(self, stageNum):
            if stageNum == '?': return stageNum
            try:
                return self.stageData[int(stageNum)]
            except Exception as e:
                return -1

    ########################################
    # Batch process new slp files
    # After sending through js file, update
    # firebase with new items
    ########################################
    def save_slp_files_nodejs(self, slp_file_list):
        #Create data for use in node js file
        paths = [f[0] for f in slp_file_list]
        slp_data = {}
        for i in slp_file_list:
            slp_data[i[1]] = [i[2], i[3], i[4], i[5]]

        #Run bulk process - if no results just return and delete files. Probably means corrupted slp files
        p = subprocess.Popen(['node', 'processSlippiFiles.js'] + paths, stdout=subprocess.PIPE)
        results = json.loads(p.stdout.read().decode('ascii', 'replace'))
        if not results: return

        #iterate over results
        for k, v in results.items():
            new_name = k.split('_')[-1][:-4] #Just get the timestamp part of the fname
            tourney, subTourney, video, notes = slp_data[k]

            #Use lock to increment UID
            with self.lock:
                save_str = "{:07x}|{}|{}|{}|{}|{}|{}".format(self.currentUID, tourney, subTourney, notes, v['timestamp'], v['duration'], v['stage'])
                self.currentUID += 1
                
            for p in range(4):
                try:
                    save_str += '|{}|{}|{}'.format(v[f'p{p}_char'], v[f'p{p}_code'], v[f'p{p}_name'])
                except:
                    save_str += '|?|?|?'

            save_str +=f'|{video}'

            #Store data in firebase
            data = {new_name: save_str}
            self.firebase_data.newItemsQ.put(data)
            self.db.child('replayData').update(data)