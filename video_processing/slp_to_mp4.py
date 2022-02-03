#!/usr/bin/env python3
import os, sys, json, subprocess, time, shutil, uuid, multiprocessing, psutil, glob
from pathlib import Path
from slippi import Game
from config import Config
from dolphinrunner import DolphinRunner
from ffmpegrunner import FfmpegRunner

VERSION = '1.0.0'
USAGE = """\
slp-to-mp4 {}
Convert slippi files to mp4 videos

USAGE: slp-to-mp4.py REPLAY_FILE [OUT_FILE]

Notes:
OUT_FILE can be a directory or a file name ending in .mp4, or omitted.
e.g.
This will create my_replay.mp4 in the current directory:
 $ slp-to-mp4.py my_replay.slp

This will create my_video.mp4 in the current directory:
 $ slp-to-mp4.py my_replay.slp my_video.mp4

This will create videos/my_replay.mp4, creating the videos directory if it doesn't exist
 $ slp-to-mp4.py my_replay.slp videos

See README.md for details
""".format(VERSION)

FPS = 60
MIN_GAME_LENGTH = 1 * FPS
DURATION_BUFFER = 70 * 3              # Record for 70 additional frames

# Paths to files in (this) script's directory
SCRIPT_DIR, _ = os.path.split(os.path.abspath(__file__))
if sys.platform == "win32":
    THIS_CONFIG = os.path.join(SCRIPT_DIR, 'config_windows.json')
else:
    THIS_CONFIG = os.path.join(SCRIPT_DIR, 'config.json')
OUT_DIR = os.path.join(SCRIPT_DIR, 'out')


combined_files = []


def is_game_too_short(num_frames, remove_short):
    return num_frames < MIN_GAME_LENGTH and remove_short


def get_num_processes(conf):
    if conf.parallel_games == "recommended":
        return psutil.cpu_count(logical=False)
    else:
        return int(conf.parallel_games)


def clean():
    for folder in glob.glob("User-*"):
        shutil.rmtree(folder)
    for file in glob.glob("slippi-comm-*"):
        os.remove(file)

# Evaluate whether file should be run. The open in dolphin and combine video and audio with ffmpeg.
def record_file_slp(slp_file, outfile):
    conf = Config()

    # Parse file with py-slippi to determine number of frames
    # slippi_game = Game(slp_file)
    js_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'getNumFrames.js')
    p = subprocess.Popen(['node', js_path, slp_file], stdout=subprocess.PIPE)
    out = p.stdout.read()
    num_frames = int(out.decode('ascii', 'replace').strip()) + DURATION_BUFFER
    #num_frames = slippi_game.metadata.duration + DURATION_BUFFER

    if is_game_too_short(num_frames, conf.remove_short):
        print("Warning: Game is less than 30 seconds and won't be recorded. Override in config.")
        return

    DOLPHIN_USER_DIR = os.path.join(conf.dolphin_dir, 'User')
    # Dump frames
    with DolphinRunner(conf, DOLPHIN_USER_DIR, SCRIPT_DIR, uuid.uuid4()) as dolphin_runner:
        video_file, audio_file = dolphin_runner.run(slp_file, num_frames)

        # Encode
        ffmpeg_runner = FfmpegRunner(conf.ffmpeg)
        ffmpeg_runner.run(video_file, audio_file, outfile)


def main(slp_file, final_dir):

    #slp_file = os.path.abspath(sys.argv[1])
    clean()
    os.makedirs(OUT_DIR, exist_ok=True)

    # Handle all the outfile argument possibilities
    outfile = ''
    outfile, _ = os.path.splitext(os.path.basename(slp_file))
    outfile += '.mp4'
    #outfile = os.path.join(OUT_DIR, outfile)
    outfile = os.path.join(final_dir, outfile)
    
    #Remove original slp file
    record_file_slp(slp_file, outfile)
    os.remove(slp_file)

    #Decrement number of threads
    # with lock: num_threads -= 1


if __name__ == '__main__':
    main('C:\\Users\\kenne\\Documents\\Repositories\\Smash-MeleeHub-GCP\\website\\video_processing\\test.slp', 'aaa')
