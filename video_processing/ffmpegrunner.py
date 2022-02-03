import subprocess

class FfmpegRunner:
    def __init__(self, ffmpeg_bin):
        self.ffmpeg_bin = ffmpeg_bin

    def combine(self, concat_file, outfile):
        cmd = [
            self.ffmpeg_bin,
            '-safe', '0',
            '-f', 'concat',             # Set input stream to concatenate
            '-i', concat_file,          # use a concatenation demuxer file which contains a list of files to combine
            '-c', 'copy',               # copy audio and video
            outfile
            ]
        #print(' '.join(cmd))
        proc_ffmpeg = subprocess.Popen(args=cmd)
        proc_ffmpeg.wait()

    def run(self, video_file, audio_file, outfile):

        cmd = [
            'ffmpeg',
            '-hide_banner', '-loglevel', 'error',
            '-y',                   # overwrite output file without asking
            '-i', audio_file,       # 0th input stream: audio
            '-i', video_file,  # 1st input stream: video
            '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
            '-vcodec', 'libx264',
            '-c:a', 'aac',
            '-filter:a', "volume=0.25",
            '-b:v', '1500k',
            outfile
        ]

        #print(' '.join(cmd))
        proc_ffmpeg = subprocess.Popen(args=cmd)
        proc_ffmpeg.wait()