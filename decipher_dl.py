# -*- coding: utf-8 -*-

'''
For Educational Purposes Only.

-------------- Vdocipher Downloader -------------

first time run: 

1) pip install aiohttp sqlite3 requests json pytz datetime shlex
2) sudo apt install -y git cmake make build-essential; git clone https://github.com/axiomatic-systems/Bento4.git; cd Bento4; mkdir cmakebuild; cd cmakebuild/; cmake -DCMAKE_BUILD_TYPE=Release ..; make; sudo make install

Dependencies: yt-dlp, aria2c, mp4decrypt, ffmpeg
Usage: python decipher_dl.py -t "TOKEN"

For custom name add: -o "LUMD"
For custom resl add: -r "1/2/3" where 1 is highest and 3 is lowest available rsl

'''

import re
import json
import pytz
import sqlite3
import requests
import datetime
import asyncio, shlex
from aiohttp import ClientSession
from typing import Tuple, Union, List
import subprocess, os, argparse, base64

__version__ = 1.0
__author__ = "Daddy Yankee"

os.makedirs("Videos/", exist_ok=True)

parser = argparse.ArgumentParser()
parser.add_argument("-o",
                    '--output',
                    dest="name",
                    help="Specify output file name with no extension",
                    default=None,
                    required=False)
parser.add_argument("-t",
                    '--token',
                    dest="token",
                    help="Vdocipher Token",
                    required=True)
parser.add_argument("-r",
                    '--resl',
                    dest="resl",
                    help="Video Resolution",
                    default="1",
                    required=False)

args = parser.parse_args()


class Vdocipher:

    def __init__(self, token):
        self.token = token
        self.vid = self.decode_b64(
            self.decode_b64(self.token)["playbackInfo"])["videoId"]
        session = requests.Session()
        session.headers.update({
            "authority":
            "dev.vdocipher.com",
            "user-agent":
            "Dalvik/2.1.0 (Linux; U; Android 9;  Pixel 6)",
        })
        self.mpd_link, self.name = self.detail(session)
        self.pssh = self.parse_mpd(session)
        session.close()

    def detail(self, session):
        response = session.get(
            f"https://dev.vdocipher.com/api/meta/{self.vid}").json()
        mpd = response["dash"]["manifest"]
        title = self.c_name(response["title"]).rsplit(".", 1)[0]
        return mpd, title

    @staticmethod
    def decode_b64(data):
        return json.loads(base64.urlsafe_b64decode(data).decode())

    def c_name(self, name):
        newname = name.replace("'", "").replace("/", "-").replace(
            "%",
            "").replace('"', '').replace("[", "(").replace("]", ")").replace(
                "`", "").replace("\n", "").replace("\t", "").replace(
                    ":", "-").replace(":", "").replace("||", "")
        return newname

    def parse_mpd(self, session):
        resp = session.get(self.mpd_link)
        pssh = re.findall(r'pssh>(.*)</cenc', resp.text)[0]
        return pssh

    def get_date(self):
        tz = pytz.timezone('Asia/Kolkata')
        ct = datetime.datetime.now(tz)
        return ct.strftime("%d %b %Y - %I:%M%p")

    async def get_keys(self):
        keys = await self.get_from_db(self.pssh)
        if not keys:
            async with ClientSession() as session:
                async with session.post("https://api.newdomainhai.gq/free",
                                        data={"link": self.token}) as resp:
                    keys = await resp.json(content_type=None)
            try:
                keys = keys["KEY_STRING"]
            except (KeyError, ValueError):
                return 1
            await self.add_to_db(self.pssh, keys)
        return keys

    async def init_db(self):
        query = 'CREATE TABLE IF NOT EXISTS "DATABASE" ( "pssh" TEXT, "keys" TEXT, PRIMARY KEY("pssh") )'
        await self.async_db(query)

    async def add_to_db(self, pssh, keys):
        query = "INSERT or REPLACE INTO DATABASE VALUES (?, ?)"
        await self.async_db(query, (pssh, keys))

    async def get_from_db(self, pssh):
        query = "SELECT keys FROM DATABASE WHERE pssh = ?"
        result = await self.async_db(query, (pssh, ))
        keys = result[0][0] if result and len(result) > 0 else None
        return keys

    async def async_db(self, query, parameters=None):

        def executor():
            connection = sqlite3.connect(f"{self.dirPath}/database.db")
            cursor = connection.cursor()
            cursor.execute(query,
                           parameters) if parameters else cursor.execute(query)
            result = cursor.fetchall()
            connection.commit()
            cursor.close()
            connection.close()
            return result

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, executor)


class Download(Vdocipher):

    def __init__(self, name, resl, token):
        super().__init__(token)
        currentFile = __file__
        if name:
            self.name = name
        realPath = os.path.realpath(currentFile)
        self.dirPath = os.path.dirname(realPath)
        self.vid_format = f'bestvideo.{resl}/bestvideo.2/bestvideo'
        self.encrypt_video = self.dirPath + '/vid_enc.mp4'
        self.encrypt_audio = self.dirPath + '/aud_enc.m4a'
        self.decrypt_video = self.encrypt_video.replace('enc', 'dec')
        self.decrypt_audio = self.encrypt_audio.replace('enc', 'dec')
        self.merged = f"{self.dirPath}/Videos/{self.name} DL: {self.get_date()}.mkv"

    async def x(self):

        self.key = await self.get_keys()
        if self.key == 1:
            print("Could'nt Get decryption Keys.")
            return

        adtext = lambda text: text.rjust(30)

        print(adtext("[Downloading] Video ➡️"), self.name)
        returncode = await self.yt_dlp_drm()
        if returncode != 0:
            return 1

        print(adtext("[Decrypting] Video ➡️"), self.name)
        returncode = await self.decrypt()
        if returncode != 0:
            return 1

        print(adtext("[Merging] Video ➡️"), self.name)
        returncode = await self.merge()
        if returncode != 0:
            return 1

        print(adtext("[Cleaning Directory...]"))
        await self.delete()
        if returncode == 0:
            print(adtext("[Done] Video ➡️"), self.name)
            return self.merged

    async def subprocess_call(self, cmd: Union[str, List[str]]):
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        elif isinstance(cmd, (list, tuple)):
            pass
        else:
            return None, None
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

        stdout, stderr = await process.communicate()
        error = stderr.decode().strip()
        output = stdout.decode().strip()

        return output, error, process.returncode

    async def yt_dlp_drm(self) -> List[str]:
        xhr = []
        xhr.append(
            self.subprocess_call(
                f'yt-dlp -k --allow-unplayable-formats -f "{self.vid_format}" --fixup never "{self.mpd_link}" --external-downloader aria2c --external-downloader-args "-x 16 -s 16 -k 1M" -o "{self.encrypt_video}" --exec echo'
            ))

        xhr.append(
            self.subprocess_call(
                f'yt-dlp -k --allow-unplayable-formats -f ba --fixup never "{self.mpd_link}" --external-downloader aria2c --external-downloader-args "-x 16 -s 16 -k 1M" -o "{self.encrypt_audio}" --exec echo'
            ))
        await asyncio.gather(*xhr)
        return 0

    async def decrypt(self):
        _, _, returncode = await self.subprocess_call(
            f'mp4decrypt --show-progress {self.key} "{self.encrypt_audio}" "{self.decrypt_audio}"'
        )
        if returncode != 0: return 1

        _, _, returncode = await self.subprocess_call(
            f'mp4decrypt --show-progress {self.key} "{self.encrypt_video}" "{self.decrypt_video}"'
        )
        if returncode != 0: return 1
        return 0

    async def merge(self):
        _, _, returncode = await self.subprocess_call(
            f'ffmpeg -i "{self.decrypt_video}" -i "{self.decrypt_audio}" -reserve_index_space 512k -c copy "{self.merged}"'
        )
        if returncode != 0: return 1
        return 0

    async def delete(self):
        try:
            listx = [
                self.encrypt_video, self.encrypt_audio, self.decrypt_audio,
                self.decrypt_video
            ]
            for x in listx:
                try:
                    if os.path.isfile(x):
                        os.remove(x)
                except:
                    print("Failed to delete:- ", x)
                    pass

        except:
            pass


async def main(name, resl, token):
    try:
        if isinstance(resl, str):
            resl = int(resl)
    except:
        resl = 1
    x = Download(name, resl, token)
    await x.init_db()
    await x.x()


if __name__ == "__main__":
    toke = str(args.token)
    name = str(args.name)
    resl = str(args.resl)
    asyncio.run(main(name=name, resl=resl, token=toke))
