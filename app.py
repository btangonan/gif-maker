#!/usr/bin/env python3
"""
GIF Maker — drag & drop MP4 → GIF converter
Run: python3 app.py
Then open: http://localhost:7878
"""

import http.server
import socketserver
import json
import math
import os
import re
import subprocess
import sys
import time
import threading
import uuid
import urllib.parse
from pathlib import Path

TOOL_PATH_PREFIX = "/opt/homebrew/bin:/usr/local/bin"
os.environ["PATH"] = f"{TOOL_PATH_PREFIX}:{os.environ.get('PATH', os.defpath)}"

PORT = int(os.environ.get("PORT", 7878))
HOST = os.environ.get("HOST", "127.0.0.1")
# Default sized for local use and photo batches (held in memory during parsing,
# so 500 MB is the practical ceiling). Override with MAX_UPLOAD_MB per host.
# NOTE: the public gif.tangonan.dev tunnel goes through Cloudflare, which caps
# requests at ~100 MB on Free/Pro plans — larger batches must use the local origin.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_JOBS = 500
MAX_CONCURRENT_CONVERSIONS = int(os.environ.get("MAX_CONCURRENT_CONVERSIONS", "1"))
MAX_DURATION_SECONDS = float(os.environ.get("MAX_DURATION_SECONDS", "90"))
MAX_OUTPUT_FRAMES = int(os.environ.get("MAX_OUTPUT_FRAMES", "1350"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_MIME_PREFIXES = ("video/", "application/octet-stream")
ALLOWED_ENCODERS = {"gifski", "libvips", "ffmpeg-high", "ffmpeg-med"}
ALLOWED_WIDTHS = {"original", "1000", "800", "640", "480", "320"}
ALLOWED_LOOPS = {0, 1, 2}
# Speed: form value -> time-stretch multiplier. >1 plays slower (every sampled
# frame is held longer); <1 plays faster (fewer source frames are sampled so
# the chosen fps stays the playback rate).
SPEED_OPTIONS = {
    "1/4": 0.25,
    "1/3": 1.0 / 3.0,
    "1/2": 0.5,
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
}
# Photo-series canvas: how the common frame size is derived.
ALLOWED_CANVAS = {"first", "bbox", "1:1", "16:9", "9:16"}
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Track job progress
jobs = {}
jobs_lock = threading.Lock()
conversion_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CONVERSIONS)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GIF Maker</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="shortcut icon" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
/* clash-display-600 embedded */
@font-face{font-family:'Clash Display';font-style:normal;font-weight:600;font-display:swap;src:url(data:font/woff2;base64,d09GMgABAAAAADu0AA8AAAAAsjQAADtTAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP0ZGVE0cGoEQG5RcHIduBmAAhyYRCAqCgjSBxXULhkIAATYCJAONAAQgBZAcB5UgG66PF9DbdlDcrapsSUC26+xg7HaCRMr70WcHatg4AJD7XbP//89IOsZwDBugmlX9XEJYZSGQQpg+SGCahTOxMBNpumiSHCEsq4pN+tVZQEztyhFIklh1kzrm43nZpx+LoIkM3BuVhXWaQpoXZabpc/uuA/4OP/9iwlTIiktGZoUj1OhJ7yl3yv8KQ5AVFWSEOcbeURvdLVH51aTzxST6NT81eSWTy/QjmvPfzO6FcBFt4vTw1I2aWaio6TcBh4qRqw8lNsPgAS4qF2Ienp9bT0asqBgIEjkQhFHSY8A2osaAjQVswChpyRGDsRFT0g/GgIGCSChiUeFhnjaiHhZWH156N+iujhPQhKTjj6fkHvLN7P4Pcn588dNqtUlTkHKNC8bbICJP+36c630n3ISM++pQDeigwAftB06btE0pxet6n4WbnvozbkKSnHFj4dYeICHPj+rK6jyrdkKzEQE9e7/uvV/okwNpFIDPYLRtV2zR2AWjYPitOe+Wbx6oaOyMnLErQzqgYGz+FRcDMXbTSt2Bc9JcRpjg+VxlNbi4p+72N+4Xn+Hf4vHvf+nS/7Une+a9lS5YY9V4UnSw2j3Q5SzLxCGS2lPrpAKALk1PVIbt+bVWd/7gZ/viT3DxIr2e2Jw/VBKN7nFrxZJYg1Qtc2WzTGdvJf/q7svWmfhhTRREkhFiR8luz55ud2b1eu2KbvWoM4HAoPt7g+DkPXiX9L/Sk86AqAc0AQYJEEZ26Njl0GHqzEFKFISh/f/W/LLdH4Yos+TGLgkPpICOXyMofavy3u+u1O/5yXCylD+EmVngFKRPupMskwKUTI5IjfGLaoVeZdc7IOHUGruRge/2ibyk428eIkXkCCI2iNj0CHbM37lM52IwUVJxKPrubz+tIfXWLTWlW6gKygMkcdas/xlJmbvGNBqufS1XWoygEE0sjbLALmgEQHfj1o8NB4BX33k+x+/8/8FvCAwzgCaANhgGEIYgDDUcY4TXCG+8IfA2eESVQiGoSUoRjUg9pulpRDQz3QStTQ+CBMAACAzACMCDIKleItKVgxhSrwyqlLCPzEoLEy1IJzsCoKLCGHdW+anbYA7/rTMIYBvZd/Z/ghXX/aUjWH9nIFjFLt8vB2BO/ne9Bs6pJ2A6AwE9rHw6DxMCdLCiiGlwWzXi/aQ8efooyi+MKFUv4EolAdcDawJoxQ7oloQjD2hJ5ZgKgWfYPMASrsKGZFvkPT1TeaILwFfsFuABn5286WbfjY//0f+AMwAQDAg9HjML5+iP8ViOHYjC+05JYBKqsBYasBnaJJ1uED0mewqnbKoBUzSrgAVaRljDTdjBfTjCU7hg1+ZXPNIL4B2/vPGX+TYpILJWAlKVVpAusAAghiHkT4oey9KQowKqqQ6VG238stIumxFlP8AQjrppwtbv/u3YQ9t74Rbs4oHOMeQZXOKNL9zb+/sY5Id9s5/2900DBYCiQ+gYgXZ4GIU45kZBFG9dHCplH39UjdSpR9bkoaODdYOl8JP/lCxTxjxCUGZ05zl60m6egwURdGq1U6vEoRzL8WFIxM5EqDJC0iK3h6RyS1UticnTyYnhBAOxgIGOM81yl1lFXSnUdAxLm9uyBcETsSc83edwP0e9VYPCROe/dprIdoyqCeMOa6Ja1So7tU4syVosy0ZTdecTrLA2LytMdhU0fBeGO8fCYkGjJY1GNtyg5sTmip+sVjvhGM5hILurSEElkH5pgfMtVjWyr92mvDvm7U09nmqVYyepXCGteEMd/Vnly7au5jzDApYEU8OrnENv65ea5PdqaOpVcW0450Y7Fkn/o49USJpqS6ytyomVMzm0nTwkfx9b1Vhr2PRgc9zWUIUO7BXKO7dEqJijiryma8xSLNUrbt/8jVUQIeh8xBH6vgtfJxiVchilq+DAMNCpVX+uUSukKU1wrDGr2wXzOP45hh7xkgBV1OFTT1uxxhuviPU/K+qXtFjwrvgLk0o87TdfbPqUF6pTDomAaMAm7MA+HMEpXMA13MEjvMC7v/MF4xeMvwikkMgiSUKSCiIrkAsoABQDFALKj6goUGmgCkDVgOoANQJqgakdpi4E9SKpH0lDSBpF0gQPOG6FcGeBRA4/+ZIXGOY9TUUmV22OattT0Fb0Hppds1bn+1h+6Uzr3iNHOPBWuJ2jXL18qrXUlZTDBU7lV77MXu7GW1roB1tdo7ReeJEmJNJKy099+6oxQkKFlUsA4emVRNh6foTLnPEmIhMxCeAJXTR16BQ3b7ZBGn+480jqYIRHYSUlqaKWBpppo5Me+hhkhHGmmGWBZdbYZId9jjiFqFxnTWFOkzuBIwFHUt/Z+g7Wd6K+ZzCMqb0JTy0ANzTeGxYNh8Zbw6y73UC5GoVoUydjuDBsDW1KLa4fnuWhvJHKXwaLmE79egD6fPwfBBgBGAeYApgFWABYtiAIPyz35u/JjrsR3lZudVrk+4RYzYohIBEBPSLfYrIJPUmqAME19kQ5t+uSVaX4JDW8fiN/jiDehAWg/7cZP6yX9hgOH/cSOA+jkF+SDKKpjeTT3IRh+7YatrDgGc4ZSYUqmYI66q/6JhJG+MTIrbDSKqmliTa6CBukpjs16FO5vhbHX5R+IVWW5namGskSp2kKQaVl5PiO6onSt5yTMErzJdcg/TT4y+Pt9njtx5NodAoWQyUwmCw2l0ckNoYOTh4gd/Qo5M92EVQpISKpXigcaU87L4IZBD2YZqYdgagOhhmyD+ZHO878xTtZKUNGVKXeHwhCLQwVRUmosBvZPoygvlxxNhxqaF7yGKo8g59vxnBhbDgO6BDk4N6b4EOwny8GInYw4lXpGAR9yqcuopGYpIVeBm/AFOKTi6topOzjfpAZRDMRzUdgqmPOoe0IetChp2E0RwhqirS/zIiSIL/iklRTTxOtdNBN2ADDUkmgpvogamPpU1N6VZQegtKtet1FrD6FT5BFZKozlOuEmjJFVd6fXogeGaEmRojNH7n281m4TpVeVuGG1zZAcpPGUwCeMS4Faj8ztVM4dq7OOg6qe9eaf0QL1jGlrxhxOqNV+MTSAAsBoH+7BqBRAYitEUCyWnVEyH87JY0DtFGBggAT2htjo6122uOgo3ELKZVpy/9N6jbyQi+Mwj7W4zLun5PN+i41p+bTorQYLUErqJXWqtCPQexqcqYx9pgadrDrm33+wARNR+tstt1u+xxxPLsTnLb8W0/dBgidUIV9LMdl3D7HmfFNSg7NowU0TfnYSi3qsv+2HbPs/zZfLC0uzM/NTE9NDnjXQ/4+r8MolexRK9pnUClkgpeKygMut85rkDv0XV0ZwtUhOlZx84QeSwl8UiBGCU/k/JT9/xYMMMIEMyywsrFzcMrBxc3Dy8cvIChKTproDarWaHV6gxEAIRhBMZwgKdpktlhtdofT5fZ4Tc3MAaoQiCQyhUqjM5gsSytrGzbHvgOHjhw7cerMuQuXMMBY9wgUhkjnsLl8nkAkEUtlCrlSpdFp9UaD1WKzV8xehqDCRqUP9mARAOi1HrQDwPv152M8+fwKAfDRhDIeAOg9VQQgtm3iunIr3uYFRUbqkKSkJDWccB0AnIhjcpKfPclOefhJNzDJ4SXLaJONMsVE00w3w1RzzAXMttgSi/wCmr4WaoDWPeRBhVki5kihD6Do12jRVKlXfN0gKMGKXo4hp6JWbIK1yBwY5+NGsmCqEbprGwVVaYFeKZDckBCSFtfIjdE5muUiEnvpPJQpZe5WkPMM7Lg2KmmjqVxgyxhs4FxIJ4qp3pwHbO1ANe5IRO0sSZhnUn0g6Qd/QZCh59NyaoEI9ixzKNKbAA4mRQ/MwYg+rv63OJfMkhHCLo9GlA5SMJs8A2Z2fJNmJ7upbjztOpAFOuTFFLZi3JXcDpyWw6qYLG5pitdqWhV3IbGnlndaWoe27x1ImbNuVr1av1l2rUotp5xusKPLbfhw0/ZmLmHW5orl6DZBlKRImkWObkkzDlFAQQpDARSKhcI9jsvBAQTgPgomTDINE5h8kmg0NWh4jhfskZVyEbIIDcJKDpL4EOIt6+CQCAOPOLSDOjJkyJDBN+F1RKcLxJuztkyqgs49FbncZ7oOt2KXHe1qZxGRVJKe3LcNZ204r3i14855kOen6UD7Xg9q5+QAxwFiMK5P7A3eDP0KlSWCVGjj1JQyoBHGoogbGPkXnqd0l4qK+mYHEM7K/NUMKrCGosNgTBG+ByOLtNZrbnStm5/fK799KuVl2RltdBq9ttKjNQs7UQSRj1LK6rciVwUnZSpu/WV3ifEQoo5gmH7NDWJJAl1DaWxEmQUVAb2rTzyODh+QKHUSi5T89S8WqvkEOTgsHl4ysjQ7PWzidJrcW7MtnsFYzqBUVfqGpDHpi9Hy0XGznvnYY5Zq1JCgGd0RT5D/iTApSg7ib22UFBo/rky6m0E2TafS6iZxI5ucv23v9mjkB9TPmVKqB+OgnIO31M1aiODh7wa6BoF4poTDzgXq+5DuYb5HzV1Wn+kvQ1ZHSinvAgDUOsTRLdCT7UQA+i7vm9CNqAm0Pxan+M9muOloUvW/OJFJOBRZm5bgAHxH1A7JmzmlEalSQyDVXdk8ZHqCzun3Jsh43xY8TFLC93UwJQRxLqPIDSc4qcpLJSpIcruV4GUFlzNQoSKUbDaaHWxvxVJxY5owJcMSi5HmcBEkUl3274YDg7tT1IIsqVzOcPKi8iAM1YPK4IqN5q6dA+UUIzDQdRQRZIkw906Z+z0is+tRAmp1jhEFU1S4IgGjGvGeUcPyICeUEOt251BBJHEIAeZPKQWr6mNjIUP4rsEboVbb8tYLkSzQpy3/ZDy5UKz8UONYFxkfzBLsUDz10WrApzwE9GuVkWKRy8GsJ8xoFe4xfU5Mkw59cDnJSp3SokStvSHhZEaBJnRbB7qjqWCSybJ6tWrEp0xpQVHltaaEGkSBwZeujqsePdfnyTJWoyFc4gK87TvyHhMbJyTrYiAgXD5fnsHZtWeQT8HF+gW0NOlSRqK8MQslZVvcn4yIbtAqkcbtVjm+VxEbD+Yr1kFKIijeZl2ZUWLYgrEDAjW4tY/HDKMq81XYZ6eLPbRTSVqC29jNKPRprhngOtjzmCXM8kbsykKhXPL+X4RRMklqwc9A9CFsHrL6wSJ4g6fviUgrb1Y020ygf34HYTQSPnB5dHl1ve3tIIa2hXiJYZRESyTutsgBhxz10XLIWZKjwF08p7M8LOO0zMJagkkkEU63U52rs/tlGpwC4xS0WGCRB0iBcgx99NmFR2E1yVw6UVY0vAugt176sjLCCn5Nu+mH2rJOYpCSarDFn8qcPLKLtD7HTwn+cZhyYnZTxMJHZARxa7fH1udXH47bn5t7NZ0N1FigONF0xdV6rtFhrbVRFds2WN2mWY6bLP1MyGOouqUYTP3k0YIpqI6QcJGcPso6HQeNMsDAVsx0VSgLBfskLAnDzKi9S0iHRq/51Hr7LU3FGCtiaG0ilFFlhFFdkFKb8NZ/rhmDex3QNKvOgUupSQ+8aXp7pM6c4uMhkOMbjVgzHZ01iTL3kl4TKCwRlbT12GWfC+E6lVmjA1/DSkH9YidCNPeTVYgm8toPUSLVEJiDJuI4KCogX71Ob7DjjFna7mqpABoJDVChhXEOFcYOZaR3iZvERsxTAZsNdpC47UgfiDRSHkcDE0iwj8Y9q7B64WDOk+yla/G9IS/xMmgSOJJqnz26OhJf63+Y7XWOZHIje/EglL5r0lIHE3vYPgzH1Nn398LrwEagHfTNtlB0S9eXN1FhUD8KdhqbyyVHSWHCjwvP2DYHntPn32DKiLkDBrjb0RSvu0j2+WJcHa6T6/tuzVFkgpZ3sL8d0EDJxYdeSHr06pcFfRzhMqYR5t6OqMKGufjCPHE9+1iHNqXR5KgF7+VyeWPOWa2vdlApO5h7fILYzsy61ncDKOr3RnAsSSlfifpyY3OUc0UMzEZtbM4+HCBmcHd4ev0W9NZccC/a81raHbf6FlpxFtRrlj0z15o2OKX4oEL7Eu/uzTN60N4TPaXf2IbU3Mx7B1Q3B7rCVNCX3Zy8sT2GhJQMtiAvf9qBlr1jCw+b4TAKxHyfX+/YxILMGdw+P5EnOPVwdFB5E7T6uSlN7O5aP2wG8wQvAE0rY8d7dUnVzjnSwrPSuIJ8XDgsfesx6Js31XvGfeNX4zP9an6vXKfBkqGKFmIO+wTPVCdaSRRsbWKNUcZ/KI2HxDh69pHNuovW2i28mAh3gWiBo9DrUsWT+GhSHBLWzODyF6hArOPTzLvsbXzGTNttdlVtzhnMEv5jo/rM0+22AwLB3AWC2QvpWnyUdAIG2L1Ept4EPncimPUgi7WCPrzos7AXLR069yLw+9DzXDQfhs85vX7vviYttu7vX+2HeeA+tPe1tO5zeM0v4JWKHjtYVQxoqgd6JKiKatQX6KMWVpxg4t6c7N4cvw48AFSi773PUp/7K6De8ufA9i4NYA7KYfCdK1csqgRAyfsVseOB5JtuT70yRvIcX6cXhl7o980TQ9f7fS2iljnF/Rp1clKnnMUhL+lGctF4iWIkR44e0+nmmFFDN/+iSur4wY9E4y2pzI/1zf01mkD3SdyCuwa1y09e4WlgB5AGCG0FrlX2SNLsdR5ujdXEpUXe8PNrq2KbG0M249kiw1rSvbyEqk9P7ATtZ16GuTl7mjRR5hX62ETt5mvA0xEvjY3XSmVN7VudV4q3jGH0Cs6kMj+bN9DB8xDVgtKhj9wVnY7yHTFfbgKy0ZMVAPq4d5gEWbkTjjYjaIBUwSkwpwyfAp8HzjWSdfYYFblY0+NQDPNnhTj+3MkKLtucqsbqJsXnxz+wp0qVkFV5DSmDp8xolqbIu2kGm10QLexyswm07UPWjXK7aEaXoeXuq5j/6F5aN7jTy4cjcIkOXcYD3IlYsWfrJCQkxrFRKcn83sdYTdQWye+pVBhTP3uEqMp1ZrSzcLpCL6v4GU6z+IepTePvPDrgSjM92FTYmo3JcP7zqVMJRnqMQok5Ti5QdfSAs3GmkNkzQGG430g0pUcqBKcL74u7KRPDwRdUUGdoQIowVPtTdZoz8sZDzhslnDZJbdFBphMFtf/aDhxJ1WkwlEB151/rgjsFa/gBR+D0T4qIKxwcK9ERWvMOxXLdu5VXpwW2EOmJ6ty08huoVuh6hR922xUWRSdOyGTVpY5a9pXulPGEijFwMh5DoRtK1TWL87IBbKQ0q1dNY37edeUp/9MfHPg0kismz4nFDUw1wvxYmRs7lt61eVqdCsQVZ0MwQ/B6ypFDhifZSGewktEFatMQsZS5B4ObTBoy4qFMfqH4iPo9o26xbc2IjTo5eKxQ/K7CwvcoLbevIp5bMkV9GKiuTKwpFcMJpn2Zh/kGW7IMdnTA04U4gwehNez1wdyxht0kOOpZNYuHCkI7y6xSELx70McmXQHi9Zikfq/3o1sJayB7VWLuKuS3BU1MxpCtKPv5phNb8M+M2fqfTvNwROfG53mbdtI4tBHtURlhQQanQPA4WyRZ0QDTB7OUH7PygjVFxLqxi10hQ2Bzto4akj3pndBN1awJLffW3zACLpwSo3PDHcdRhLnsGneDtu82OM8owwcQmVXiBryUFFT5u327w4HkHHCqebaZJt1v5WIz2ldeVMh0TP4HukXLnkYRnrDK1JPhqtKAs29YpR9f+5jVZG5SzlixdPSKNZUe8xqFHnM6OOUljonxYaL97jpc4tOUH5zunRdk+XF0g5UV+dXWx9MlnvRyZy1PBMwq68pLUm2f28ZsU4zMc24FIIHW4bcJcE2enPPhJtGcX27d3Vj1PIr1OqFLeXVYojQkqVBHF//4HGwZ/6/fPuvogIt+y/SE7BeljGJU6p9iKkSqsc+liJfFWbaGzwKSlNYjeIW5FXLNs/ymV7ciThv+8R2SW1UJyci+tr9FuTeZ1qhnkBndQ6AHsMmtvo/f6FrBXC6Sl/UhbLoWiUFFasfjnU/VhUTmJ1aWsS00g+UZNAA7ULaTuD3DOr9naFESslmCpLx0fUp3hERrWIZFHydFXjzzzVGuyzy4s2bfuCCz2tmo899RkInUOzLivTse777rRiyaTTN0yCDrdrgvmt0lDOehxKIYdsV+Bm+EwhGJZ6JvebreMTV1DNkU2BeyUGRRTL1CTosghN1CTT7RDEkI8yJ2G0Jyb34WCkDNYDCQXeHrt2IqK0+tlGsoZquvlO6z4krXdL9blOS3nxjRODG6nVeoMRr/LpEtD7M2DZ2Ydew6Ro/rBA+HHuYy9nLK8YTgmA/qjhy8+mNSDNh41InVsrUMWgyy1LJDyA/3D4MMPtOoufVI6x/NzB2LqwI2252F+aLjtvmt4lXPrnavrhYUXKRcPH6MOyi6gRO2wwqaWf/kL+56MgEpV8IqRlcWpipCGrsIlty4q2ZGfPdp/TnD7rDywmokQ5KYqZ5ZzFDsVHEKsE6K2DAxtBmcNrxqfCQ8NycfDebo0Ux6FzMhmiLC7crRw+mt7tJW7tPwT6GfrSw/hwa+OsqKCQRP2ppighzOjxHwQziskKjRwXCUn2JAmMe4UmnDfiepteV1+yV2B5tXzsOWNVdL61kX8E7r9i+wdngT0MavWLzntpDAuwsjboUhgUGJznV3Jw2Me/avzNwxF2qsj1+YVSLGOIVlmaKYnAnXNIVtsSOFo2eFD4vzxcUC3xyBrIffI5tdaRAvcWE6qj3SVKeeXJyvAG2v9gr2gieLmzmBJs1e3sVewEP0jk36nMTIVHfPENfdyg6nP4AIOzEMBPiPAIRCmyO87Z5ks8oGkEFJpFFT0k2H3Z44G9ucC6cFOXsotytnHpJIWxv3plBTuCxMq5XvWcsxNUUQi5AdKctX61FzFbFZQSZ2RPZi+USMr8UoJf6Bs0KPwp6+qh7xfnq8B4Hsp4SS6TQl9qWAcKh6KLXl/Fhnqjh1j+jBO9S1DcBG+D1EHEbYkc2ZVD87N/d/qcRQTUzvNgnMospa3K81Vu2f50wt4+em5x6uBHmIc7KjEydOnTzU0F/Kgw/C7e6SWKHBKXaozBwXakVtyrUjew81xxGs7Xf5W8cxSNYMMhY4j8Zadbpw6ZzvjBoUE0pDSYz0sBrjVkBBdB1PTKrrNkb5I4kkz+hDzNb2gwyKJ5FEQKK6DeuTjidCEBVvbG75f5z8Em/ubxytyCaZ29kSzRaIZrZ2RHPAQDT2STFghZxADrW7XYf2c7K+0yOjp2R5CSQbh51kG7pUyWAjaHFscctEeFVaJ7Bgmv7gnETiGoN0smR6DeBJ9UL5AkiY58+Dja3Yny+Mx5CZ03RAoEH2vx7Dykha4E4nqw6DzCMNMokoPTYoOGyNvP2QohbqzUj/CKizJick87gMXoiLvwsfnlD71R5r2hHWIM6XjewTyA5X86F4krYuN8mUN3n7xuTc1tNby4+WB4sy6mmBMc6z8INvouSyw7ERscbUCCzoP24uvW8pHfFpjyjR82l95NNqzUOBK8e623iZlAjJYSSCrsiICYzfk8TXqX1vE25qxsK++a/1p32utVWuPahEHFuY9liYPia90FalOqhKiPKh59BpG3RaDj3Kh+DJVZAOCgjdhL6ZcQ+3RpnOaMtoRkz0u1qA7dbtJpbVtonaegPMQVtM5zUFXMTB8Smv1amR7guNJfBBuGeMG7uAKW7qhVQ7hxc5pZymFrjVQfKREJKFJF2ZNbyWwB0hlTQ3GvYYhpNjqcXkAz0HRPskJLMbHEeceUN+STkzsm0IhFlQvW7zlb56hOxzBOV1pJN8rRuKkU9DWaY12Z5rsh0MlEJaatvez14JEpSiiLDM5odvTAVSoQxUIwYWpz3csgNDS1Ne/XWbNxg0RAP8W8sqqq/abKjee+k888LaBfx+b69usE+yzKvtgp+6AElZzkN3WdGJLOMf/Kevh3y+KC3x+Iw6/NBVYuLEWMIo0Ws313zikdsPnKOSK4hDHOwvLjxNno9YqOQI1FmR3UA+CWjte4EU0v1LXC/+C2QiZINdDSKoPDYsICU1NCC2HBI1DHSBzfva0rOXFJAXFc6A+idS6fHIcp02lFFbTvmT7PJBRm2EQ/rRbukTbrj9AsrNFsyvyAej5Ikr059QZz6twFYEm93UVxQ427lhPT9ZtexGQ4Ew3MqpnQugtVDcIEQJxFwxJET1AGPPv3T+4mcbZYPvDZrSTArf/1UMjupKJHXjTXUSyk8V5GWkZaaBRURUQpBvvkztvrbmrm/eHnJY+U4Yq7WgvKy8IMVSUgDX5+F5zZb4iHCs2agmDkw0dUP2cDQ+KTQ2p6yptKSiqWBUvwOBzPQjuZGD/d0IAXi34BCiqx9wQgi6JMUlXRJB6YGiJJUD8LiKgPX6BwEVcfADKkkHioASoqCyqaS0rCknNikUjUfYQ92SJvj2DnkYwd+tg+TmB/cjuXb4uwFHRA1UIyju2vd3e2WhimMX9jYJn2iChFDRrake7cKPfkgT8AoqJfKDUWFCep7dngDnC6Yy/mEAc8opL8vMqC7PDU/2n4eXSkZ+GpZLeCzIVjkkeCcpD36Z4X90e/bPGuRAOxzKKcCWRHbiq+4PRwdxE+ic1NwEHKTo20ckD+PBrBVUdB7YglaXgO4nYXINnHb9D71OSYmmmTY3v2ry9LmvE3Lj/DMFB2J3P2w1dcERQTR6PIVJg5MRCGJCAp3J2UNzhxR9Tf0IuoSfS4w5pUMIZGAyk8FNzY5PzsZbGBA0hAcTCLkj+4qKVbzdfcVFaXDokehjcMjjAAKYHYJ6mhqQBm0j+RVN38oac6mcUDRBKcuH5GIJWXSTyfd0dzwAc05547f44PyRvDUiGyQ9kCMcTTAGg0R6TnXxgeNJ7h25o7pnvV9MGCkyjB1BgZyxMTsdpbuAOaJSzIqDQQiTP/AetbraCxclaofVyoPK48r5QkYCDFI0eezvxsVofdvqheYgYwJ8icIY0MCfObsSwY9IgpL6+H0TFm9t6OCHTE0v1517LIh0Gf/fki3JQTgyMJUBpJMvfh88wEFCnKMgYLr+98Mem1qHkVYnQu4tBt8bbiJS+/DuzYP7fp+mfolrQFk0gPGzq7/DV/84LzwOrz6+OhGrP75HB+FAPBRdX77r8+8/dqRv2uxFWhWxXgz+oWcamukOrLSq759IwyPTFC4Jfwhen2Z5IFmKf4BATwybnRDFNRSZ7ti/w1RkyI1iJ7AxbUb6gRhaVg4yJ4uGCdQ3AuPcxtRGoLWuz0pkRBL2i0xksPQZamM2Mpuh3huDXyrdhMUmrkRtUxU9Q4MK77IsqyA9os7/KqkpsP0+3D/cdY6Hlmpr24FiblMiRz1XlJKqwnie2E1shmpWTrTPPEmis3IYquDaX0cNlfzuwYfEJWI3mycGOl8r+fhSB1pXzr7OBkGGRrum24mYqDVb4wP3wS8HJPr8n2vu8KvaH64k9kQeQkUcus95oe1hFf9O90++PpgpampqSqV7B5gjShqSqPIQwuwqwbVAR3Oh7piOSD3GMvK7PkWHEVAdV1jSmLXYlUAXbu2OSb085Wgr7gvE0KDj5crHLnimowmoneqJE2lofwRWIxEIFAZXLrjf9cGBYTw2HZmTLpfDKPfJ8ycuIS1pgJfEoPAogfAsRfcIByFd6BDhrpgFD+RRQDTKw8Y05Yd5SmOH1jZXue3PbKJIUU5GsOrDSB17/dibAF67WneI445G+dCn+POxraZWXdyvIRQeu5silJjUAaUmevlz+Vx/vLnJe5wkbO+dmskacpsyb3fDTFVVd107ZTRKGRz7mMiJ4fCVKIdjjTRMrbRVzcGG+jy/t7ZXW2TVMvu/tdoewKYQbHfdvc42DPrXqLrHzOK2HiJd2Y0eHBcW5Y3DZo8wdVy1JCoR4Go4PcF7NypDSXMUa31IQ3W3HhnvjdFTVc40s5SqK2QouLD8KCGRO7G+IQgFGirAMd4RPIdU/HPrkjncupTcB79JoW4IPPtr6eQSuBuecYdDwXiQkgGEinwY9DDyLSlWUeOj0UcNYw/w8jcglM9Vn3suRX93fHKAtM1d2mYgzcBfppydqjjlyfKcZkZT4ORgDM1bWj7uNxZCz1PBJLhHopsM3SXdRmLLUXo/pl9McBQKZegxmqNleNchxUqa4Xc5RgHEdrKiow0ygPnEtRqCzHAnAoIMWP96DLMjaUE7nazaW2lsHbv6AoJH670XatZQBcwzKzHByQSbYoemHNb2QtcKJoSCvnSkCkEr/Qvtcid5ZyrDRPvxb8p6hsrJdg6Dtuba2UdUtPXaXmG/8F7r+4X779Q2C5vRXFZUo/84pu4ZzisqSOR28sI9M6h7ia8z9M/X0c1/ba+rg9TF2+3M1CdpR6vtS1ns3mGxXTj5c+k/MLTJjUxVU1ZR4xbsU+k71yJtE15C2VBLq4KpOi7R1i4JtOlqIq0XzLNB2gZQ6TZCDJXXjLNWIJtIQ1MrkXwvn/9ubTeRFowVS5c4G0p3mK5KlziqqC2TMydDAaZ14DPjYCh+Z0V7PkNA80Q89JnrUmLUal1SxmjdKtCywaLMHS7XEKaO22ChYCH21VkjvS1JlTAYr/VIb8tnVa0/3RTgHlUCnBFJ13Z1xKOaRcoXBh/OUaqU00zDqXF1jU4vKSkujo1VYRxKo5du5gaqESK6T0gQMYRE8KSWt3XjxAxvcgDx+E0B7xVT0b00lRePv+9oeDokh0a75JbDoOX4rDsZtoGZddn5mjWYJq+Fakyv90LSk/Y0Yg8HOs3JSi1QjLJ9hqatSg6XVsBpl9XU3Ed9Z7ZjcYvpO4X0m3sbqgsKGwR7b85zFh4t4Kt8vJvBLx3DpYcFveJ9ieH1A0gES55DC47JYRacFx9zbrG2uonr47fYHzGxyIlKuuYDChx6LwjWHKZbtiMKHWQ1DetnZviVQy2pILOALulXm5SdqUzH6YvGcHbmZ8EZtLYumigkdM9B5xX0mWVKoOxgNUc260WRh7TysLL28EhmHbGKoLJK03ZHBUQoPtNRs0mV0Vg4pDR6zjU+fmS/kor2ykKMa4t91OJZv2qlsCL/ay33LxuUY/V9ywAKxYYrN6dlDtI3uZEp6soq6pz8bKSgMevPw55olQXpcLNm7UIsd5BdEKy5T/9FiPAd+uLlPoARGZ8cZBaFel4msgB3598cmoXN0JdpPRuRq9K2e8Afh36HwDWHo3ObsI+Dd2kR6Xu+nSbV9kxE3+5cEW2d/Ow0YdbeE9YlKHkmL+O0qUqAQC+U6HBV+KrZQCUgSSOD3yUebJe20oKsdjkGWtFj/a0cd/lbgVeOZsnau9NBBceQpYnprgetkbxn4izT78eFpboCjHE+tjl9glSW7hPJ1U2oxc5S/2x2jZibPUd69ifM8edAnKcInBA8ov2DhHwnP1ZuLUEyye5Api+OwCr6fDkhYKZlK2eO24Q8rl8KeUSw7rx49gLY7yA7L1jTnu6s0OaS9ywqi25D+HfPEqEAw/fFupbMZyNal0t1BgWMTs3VnRqCSNAuJWUCN5SaU9r0rbQxh8oNVe4ExsguweQuufgQpu1dfcBr0KqDT7DsJO18278mZhL1likg5qy46kHMIiqcMhEf7Ds3WuJJHugMpA7Xj6uDzEB76PVjZGtZFkJvc8gMOCbaPxoDz0B6wEqa8ZBtr/ncTaSq1m56QnKQutxN2OHgS3QE98hWr2usevqLA+u1GoxHzJFak9ObNfg0HhLevf57r8EdI6mmLR1VjnyB4gt5cR0SQvK4NJX+CoeycoJnlU1gQGC0djPj7JxNDhNn1iAGiRn8bVqxy4vJbsOZopv5IUivy89pa7K58nEVtF91cyMn5Tye1BF/8+5WQORXVD0trc6hpISi/RDH2vLafCHfiLyIT5JGuEpQSuiIVa6/PbkjGc49QAIv18lESu0UMHxm3vAgZZGkp5xA140bYiKlCYwSX8FKGMIxNnks81CJSrJvmkuVNT10UjSdYxpgm7QI5Ygj2+JX7ynZARycSuB65+/r9z//HCrfWMNnaf5JTIpaxyKicYi77Ttlw/VgDKc2kXqB6RV5hbOhtzYDazZ5vvD1g0IOZ4Rgm/5zQJXFueKBGUYrZmwSrft4UKDbzZrtRjh1FV73bJ7cn8qDQgmX1iARj3Nla6ubKExS4O340uxomuA+oIxDNMGSy7+/mBxGcSJkv1aGwYQr5BTM8sFipzAHrYeLw30gH5aKs7JedyXErEAW2Oz8FJEX4dvp25LXMsdcYDKTtGJFaN23jRjcs+3Rmtb7KhaNWtqkRJuLPJ5VoVtQROvx9r+I9lY3FGopYmTHFtfiB051PbWJDQUupryr5clHmVpstnDo5tS2kp1z1O61JiHLw7fhaKcX3oK2YPpxuExWq0KcFGYPJmJCI7wHXF3b3PuvLK1MgfS79XL1UepjpCZHgQfB+GSV243SONTFnuCNMpFSvxbCnT3BczraLo/wBGvId7tEfiddsAhWQ8kh6GVmGoheirh1NA4VoGHfdbvwOQSVo0pmqRWkk7HLd1y4Cb46DSo8W5LyXp9rYGkgonr9LF58759s8WqDK3lrYdJmscWnaEOJi5hDn95XD8hD2FBzLLXYHQktEU2w1HxXMGW7j8CaAZeJIKgSUNuTcVCcT8Yq0IocinxqGKwVqHNF+rUurQqUmenFyQGdeIYN2CAxg4wWzPHWEFecZFGl/dmFXodUqPGsnd1bl6R2lOI+L6i4MIcBppsWlByCI14sUHpVbyyjat4ddYnFIq4SSWGiD+Sel2fJ5JR33fWV5V4lEmemqJsyM2hpR4naN6nzemdszRK/ppNaswJbJmkGf3DIWlSwXCGoTrDiE4XEBdzonT7t7kK9N5xO2o2uli4eJfodQJ5KqvKqBQ1hYSFhdZVtlYU6Nl3YpXg1rpkYHBHMMafwGI90zH0mlZ5Y0Jw+pUNZRZq8nBh27gxLB/OSgfiNjZJPZT3v7eopwtS62d4hzUzbRPcsshOGQWEGcO2iBzfxQa46wcuLUl6XK/7PdP6oGL0O/w50o4ZN6xFYxdULLj/tOATMRMMpMZbjlByZSkqcRffmK5cUJrfCFE5qnGTJiAxG2M97JBRR0mCmGlgH0RtdDy1Z8Xa7HhmUa1gqP3BjTIZIXW1pl0G47gTL1JPfY22IPX2YFW0aPTnA4RgYY0yGyXNNM+dvmLOFFdkcPaSs7FvV3MhRtcgepkohpU5RZ6Noa2OXqCvFmIqNyIzwidjDlbqnz6cvsw/DGdS5Q3fMO6uiW2y5eQsxX5BJoSGnsITH5RWbXwCqr0mZJCSBqYw8N5+W3p+q2NWEZ4kyq0CamckZIbZooZUVITOjYktvS1TWkA1n+bszCG4urtqWUYrW8zH30dMVCzr/qG3ju8OhObLZwR7oQxTQknGy3FEM1yFqzXJFzX9WYP1IsfkvndyzRnpk0HokcRroIKynU3Sfsre0rUijNojIlTRuOXcDFdxfdN6kLPxyHbr0FsHVOmRhatAO5VamJ51NO7MCk5F/oUVfm/6INKpDtmuRKyHDdQpmMorLLAV0wNhOAqbJ3NlB96AIFsB4FpvI/KFJqHxniRNeIGBhbuLnIgxFk0xCk2Jay7c3UO+JbWN3p+2Qq47IymufwHIjXbcuvVIzvzG91lRXZOklFQjFunUiiwfapWUc4Knx0EYiz3yyWj85ux36agVr2GkkuTnHU/hMSROxWUH4NGZY+N1D+olZr7Hwuyz0w7OQ0rP/yCBujMrJdfBCh8LBQQlqCNBTA+RcB4bdLAIrM9ca6NCDGqiMecYBEL6cBs7NtDAQIIxjA2dzC0HwXCsgaPgySFhcUZA0fgv6+dUWhh9u2o79httrOOXG5oOXsZKX8+NXrubHorwiUD1I7cNSqX0g7CpyIwP5BBSsyy7UrCm2Mzc+1UF4y40cX/U0n+wrWx8nk+r25RhLmO+uFuitUi1Lrq+ELC6XPSG7Zx+S2CV5ryiYie7ZJIe8HpETqayjm0CkZNTp7G93E/k8IswfiOE8ieueabdvHN2vVI3ziY0gzElrca/lIz/ZjldyAjngpfa6X9AP+gddmY7qjzUOj9bik3aT0kfbAWEbZ1r29DyW5n0CfUBI0pdBneXEe/BA9auarw1iD4hH+aOHDxwe449twsNp7n2Se2K3gVlvSrjQLfP2iQ4XrgHPl+p2UxpbPLkIf5VtV7uyW17jr4+WiV/Ui/9GWZMjB7RXphj9cROgd5DGcpCkBuJk/pKARcAYl3WUyx7jsI8+g0Wa22DNI52xNsAr/JcviHrw0zDKjLwgXqgezd3BS2bGKKmrKcawuEa8k3nVoT/14Chzw/9YKroYFeB2tbXzWpyVd8Wkfb2vVp6Oh06ueW6JR0leuWbtYWThpHAIBN/FX6ZjhTBrYcJlPEFNfjs7ZAcbZjzgTxKH+T/3DwMbavP8eSDtrXSJLkO548vyrchGW0ZotZPquhUuO4Uf4e4ugkw7Igav9UTFyOQFbYelXp2G4flgg12qFla6r3T0CoMxsWCjFwRUsnbZhAXy6124c/xthEqWo01oEL/BmTsLHivP8z1QuxNP7yleDja8yde7iydOB28Z5bEHsVlb0nmiFRaoo+cevlMv/5BQiDO2vzB3iVJiCqTcmySpYPz53U02vkRy5HPj4YgCNaTGqTttRvsHcksby54Ygs2/cNcORCGjbKdJdF+Bqo/GGess6kRPkPAy2ukcC9Y0oGDO6slxdAZV5DeKuRHN/GYEHDTNQPByizRf2EPA5WAj7iRBSXnPSTZh8daaLi6fObtyHSJ0ul7i4E9jjyFrKmSyVKg7BXK8m53dndlUa+nGOGXnE9g6DZyDqjowsBs62A52NfAQ82lYrpgYKNEJQPPKcZxiLc20UzcIcn4nMDOcRYh9HK4ujS3oXaLqoOUoUXfGxK8GKkO4KLi26oUNvb2ZfMgqWhFhH/qHwEacMmQm51xAciUKURdFFwFu20NLsSWwz1uQSVw8+FH1FRJD5HUBpJkHM3afrz24Zvt5Zn3G9vUsv/bn9QfXwe/UADR9f8uzOhfZql5bcFSWjvj2ra+hhwkxJdtz/tft+8SG6cEN0rfe+N+qBHKPDd3l1Nf1dxUbD1QX4iOGFUCJikTGNRzOdsox9iz8md01rgTxJ010Glgo26FMURkXFe+uR/dLb/CmkMqTuNvD2yUWPkrrAl8jqLyFI0EtbCjEr4EilG96HlXMYh+9S+9h8f3E2/cKtlyoxUKjuO/3UMjnNdaz8HWhJjmmz3u/5G2L6AyM/RD0KDM/F9tvl7JVGTjt0vvs/u1uwdgK5en9Eh+RlMEbPpWrlStNbS0JvOR0NR7FGcmTA63sm+TLvSwricBsoKJgU1ugXlHDRCeuHMRwUxNbA2Ie8IDLaPKltzRH4jm9EAqDol5yW37TGVpjeTsqqn9g/K5w7TkHBpe3vPl8juJvc7o5/crCgBY+d0RcfcMZOWjSRNYlRo0R7wToLlyBZlmaE7Fdfmk2g8UZtKjP14sT47jFu50fOyqyQs/vEjXanEGA1OVCHVbY1lzUOtc5re4iHotKuQGcvI5bu9vNdjPZnB3J8khoKitnAmBMFx9hTuiVlWBu3Ds3Sf5rHTm4Zo8e4LIGxss/SmSxdQAfj2jlLcQc7kVll+XzHZdyF0bmLvOMeYBeBtm3+JAUhSYbgVz1fyu+3OIVUFlrAGUp1t/hJdIgxBSODlEp+f7rE7/mhpEnfjSwMytxm8itAqwV9jemvndYWjXwfF4EawjrgAmFPTl4BI6pIAwrDKsEAHhWGVYqezTM7j9vg7/Am+CPrKPAKsspKxfWmz+68ojPrwrmnBKpE+2p6PSKijJylqpRSa7U+CqZ18fJsAAk9rQ1EQC3Yhwra/T4wTNuM+2cJGqePA3izRFDl6+LV4/zXkwE12jSdoIF2YZs+1LPEylnRFReQeVOYot9ShapTtPz39PrHrVRQST3477iH066HMoKdVbOKWFORjq4P/quczoo+z1Zpm5+d9AGbEf04F20akpUNUt3u0qIV5JgV7sow0R35LNPsojpO/XosbRvPKi8Rp9juL26sWoggNapLAIAwAAIBKCCq1VEJRthaEkDEk9wec4zIgi8gJZgXkKhobwCEy3ndVDoIB+BgjXg9XC0kDcg2BVqHFvC0ib89vBm+N8w3sqkm3zZNnrdZgIkIwH0g8QT8trJM8z4gxeoEDgvoVJvXoEvFbwOKm3lI9Ahk7weCQ3lDSjdet6ISn3Om+jVkHgzir/avJXvdRTSH3mbJ6sdAZfrlJhAqIZMjEyMIYoMwWAZxNbJUYiIa+R+pc6gZSr5mZEGrTKFjgw9py2KGIB3uqQ99P2gKcRoCMQBB9AYLLv/lICYHlT1hAuYroEEVgkhC0wlP2jbQTao1Da6eJSAgIy9YdBFsQ1NWWgC7QHWqEBDNbQEVwHybgGMDYyMjL2gsIksL/KTYZscS79tvEej8YuLD6oXxVZGR+lv82GJLhSEIdAA2NfLtgrDtdshgYYARARPF5sJBCZvjGBIrYQRhNLtHUM4P/F+ClFzEnidd8K4I2TkSmjUTotdH8C3H1AqqC1xXfrsleeGhpgYXU+KfPlib3+XFDyeKsVExjVX/RGCPnC8q/bzeh8IR+8XfApo2EITiIpCGBwymkNftWYIqMw8lFyJNyhv1iRQgdEaloogHDVxXRx4UE8QhGy0LoPCGYqvBknMTiz9vCMcrrO4NVBHQ7yqQEVFBSleFF5VVshdfZ0L4fhQCCydHenKzYQqUNwoGAIXE8zKrPaYdnCtzBMAYUHusu6KDV5NdQWUzA46sAk/Gw1iTmSFxURDQFpU3VYZgF5NoI9SdLcAOXwJEfoL9RDW0vsH9h4kc9gvrQS3g2upF9dbQr0pW6fYYs/opivkdmHOymAnKDW31wtFxHFeaTWWjyeh7FW7cKRuxMtgZCr3LcrhLx0G1qEbk1/ooSveKVX5COQVoU6I/2+Sb8Nta6b7wGmVB3Txz0q39v8RTo7e449xD7hXYnKAXfbzT3tgI6E6kDdEmkgNxcxQq90339Vb9lW3E7b87oc+oy5bNYbD816yb1J8dsUN11z3q7dSfXfTLSfx/NPqvrvuSfPTRw0yMLFUIvMoRyFXqjRqW60fSux0rty49olMlVv3BL6ZH3wyFWAwmsyWMmWVrDZ72dCWg8V0crg8vkAoEkukslKktq9QqtQarU5vMAIgBCOleRrFcIKkaJPZYrXZHX3wovOC1L/OpmbmFgQiiUzplPFAGp3BZFlaWdv0jwyfvOzn2Hfg0JFjJ06dOXfhEubyEJQvEGJNB4kl0l55bSAMlyuUKrXGVuudzs6Vazdu3bmHI5AotJe3j6+fPwaLwxOIJDKl0yacc96KM866qMYSsWG/mDNvJpVGZyTx2aBmHQ5ktmDxQsrEmT4D+AKhSCyRyuQKpUqt0er0BqPJbLHa7A6ny+2xkM7XPHNvUBD6q1LU/+9ndDyfpkV1bqMND8Wp+1AHdcQjIUF4GCpokgalen7zop6HRFakvU2ympONiuqKFX3eKIYLr+BHyVzcCbxtQVzIzU5tAkuLlMClDxXKm2SwUQEkYZTOi7UkkWvgIvUJQka6ts+mLdegWMsiXMJEJrvFycKuPSr1MNcNsmmQK5WwM5uiMr3ZFRs7x4eiPlikVfEuUYnRFHKNI6hj00oNJvMSo5O4JxIcbJLIdLIRS7oAmqy2zM10y2wmm8WBkHVANcit6tm5zWL5a7JWeK9dcd7LXNxk+U4A10XaSre1W2lbs2UANwxsVaw3QLlUMxK219TDPBeiXgbQplXrihPbWnW1zbE1dsfe2By20QInzBktaGal1qmUWxPkjlW9jUe4HpjbjeuRSxfA4+qxuyJ1XEP77KJ8KmQM4ZiCoFnVr6i0YbkEqdumU/XsZrvWMUE49YKmdJR3ikNpTvVScoKVyamIYwEyjFT1jmNAVxj5rLTwfmhDWHPnEeCJCB3CslP4jmmxfQDRVCGpHzpDinITR33M/l692rxYAglsjOO5K2361PS4BkuNNdK8zdrAvBWv40E5A9jO1QPts21IHsgcku0qgILLsDSARzRqN1ePYmiHiA2Gx/OoQogNM6d5h7AeTKu6Q6GcfkID/kUbqP4eptwMtFxJiO3Z0T/BXgGjwiZCUGtYk4flUaRD5LNgHutZzBSZAI0705HGJuJ97exO20IPjPKZvZiHmYdAvYmrEM6Y421RUxgpWyc4RWiQkfYORq/SOWxyp6EzEAPVCEI2t5BKyhhZGzji+sJoNDZxWqDYLwA=) format('woff2');}
/* end clash-display-600 */
  :root {
    --bg-primary: #0a0a0a;
    --bg-secondary: #141414;
    --bg-tertiary: #1a1a1a;
    --accent-primary: #c8ff00;
    --accent-secondary: #ff6b6b;
    --accent-success: #4ade80;
    --text-primary: #e4e4e7;
    --text-secondary: #a1a1aa;
    --text-muted: #71717a;
    --border-color: #2a2a2a;
    --cell-hover: rgba(200, 255, 0, 0.15);
    --shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
    --radius: 8px;
    --transition: 0.2s ease;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 48px 24px 24px;
    overflow-x: hidden;
  }

  .app {
    width: 100%;
    max-width: 620px;
  }

  h1 {
    font-family: 'Clash Display', 'Archivo', Arial, sans-serif;
    font-size: 2rem;
    font-weight: 600;
    text-transform: none;
    letter-spacing: -0.01em;
    color: var(--accent-primary);
    margin-bottom: 6px;
  }

  .subtitle {
    color: var(--text-secondary);
    font-size: 0.95rem;
    font-weight: 400;
    margin-bottom: 28px;
  }

  /* Drop zone */
  .drop-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border: 2px dashed var(--border-color);
    border-radius: var(--radius);
    padding: 48px 24px;
    text-align: center;
    cursor: pointer;
    transition: all var(--transition);
    background: var(--bg-secondary);
    position: relative;
  }

  .drop-zone:hover, .drop-zone.drag-over {
    border-color: var(--accent-primary);
    background: var(--cell-hover);
  }

  .drop-zone.has-file {
    border-color: var(--accent-primary);
    border-style: solid;
    background: var(--cell-hover);
  }

  .drop-icon {
    display: none;
  }

  .drop-label {
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .drop-zone:hover .drop-label,
  .drop-zone.drag-over .drop-label {
    color: var(--accent-primary);
  }

  .drop-hint {
    font-size: 0.8rem;
    color: var(--text-muted);
  }

  .file-info {
    display: none;
    align-items: center;
    gap: 10px;
    font-size: 0.9rem;
  }

  .file-info.visible { display: flex; justify-content: center; }

  .file-name {
    font-weight: 600;
    color: var(--accent-primary);
  }

  .file-size { color: var(--text-muted); font-size: 0.8rem; }

  input[type="file"] {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }

  /* Options */
  .options {
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    padding: 20px;
    margin-top: 16px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .option-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .option-group.full { grid-column: 1 / -1; }

  label {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  select, input[type="number"] {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 0.9rem;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    width: 100%;
    outline: none;
    transition: border-color var(--transition);
  }

  select:focus, input[type="number"]:focus {
    border-color: var(--accent-primary);
  }

  .time-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .time-row input { width: 100%; }

  /* Slider row */
  .slider-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .slider-row input[type="range"] {
    flex: 1;
    -webkit-appearance: none;
    height: 4px;
    background: var(--border-color);
    border-radius: 2px;
    border: none;
    padding: 0;
    cursor: pointer;
  }

  .slider-row input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent-primary);
    cursor: pointer;
  }

  .slider-val {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent-primary);
    min-width: 36px;
    text-align: right;
  }

  /* Convert button */
  .convert-btn {
    width: 100%;
    margin-top: 16px;
    padding: 14px;
    background: var(--accent-primary);
    color: var(--bg-primary);
    border: 1px solid var(--accent-primary);
    border-radius: var(--radius);
    font-family: 'Inter', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    cursor: pointer;
    transition: all var(--transition);
    letter-spacing: 0.01em;
  }

  .convert-btn:hover:not(:disabled) { background: transparent; color: var(--accent-primary); }
  .convert-btn:active:not(:disabled) { transform: scale(0.98); }
  .convert-btn:disabled { background: var(--bg-tertiary); border-color: var(--border-color); color: var(--text-muted); cursor: not-allowed; }

  /* Progress */
  .progress-section {
    display: none;
    margin-top: 16px;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    padding: 20px;
  }

  .progress-section.visible { display: block; }

  .progress-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 10px;
  }

  .progress-bar-wrap {
    background: var(--bg-primary);
    border-radius: 6px;
    height: 6px;
    overflow: hidden;
  }

  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent-primary), var(--accent-success));
    border-radius: 6px;
    width: 0%;
    transition: width 0.3s;
  }

  .progress-bar.indeterminate {
    width: 40% !important;
    animation: slide 1.2s ease-in-out infinite;
  }

  @keyframes slide {
    0%   { margin-left: -40%; }
    100% { margin-left: 100%; }
  }

  /* Result */
  .result-section {
    display: none;
    margin-top: 16px;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    padding: 20px;
    text-align: center;
  }

  .result-section.visible { display: block; animation: flash-success 0.6s ease; }

  .result-section img {
    max-width: 100%;
    max-height: 320px;
    border-radius: 6px;
    margin-bottom: 14px;
    border: 1px solid var(--border-color);
  }

  .result-section img.checkerboard {
    background: repeating-conic-gradient(#e0e0e0 0% 25%, #fff 0% 50%) 0 0 / 16px 16px;
  }

  .result-meta {
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-muted);
    margin-bottom: 14px;
  }

  .download-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 10px 24px;
    background: var(--accent-primary);
    color: var(--bg-primary);
    border-radius: var(--radius);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    transition: all var(--transition);
    border: 1px solid var(--accent-primary);
  }

  .download-btn:hover { background: transparent; color: var(--accent-primary); }

  .error-msg {
    color: var(--accent-secondary);
    font-size: 0.85rem;
    font-weight: 500;
    margin-top: 8px;
  }

  .reset-btn {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    border-radius: var(--radius);
    padding: 8px 16px;
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    margin-top: 10px;
    transition: all var(--transition);
  }

  .reset-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); background: var(--bg-primary); }

  /* Animations */
  @keyframes flash-success {
    0%, 100% { box-shadow: none; }
    50% { box-shadow: 0 0 20px var(--accent-success); }
  }

  /* Responsive */
  @media (max-width: 600px) {
    body { padding: 12px; }
    .options { grid-template-columns: 1fr; }
    h1 { font-size: 1.5rem; }
  }
</style>
</head>
<body>
<div class="app">
  <h1>GIF Maker</h1>
  <p class="subtitle">Drop a video or series of photos to make a GIF.</p>

  <!-- Drop Zone -->
  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept="video/mp4,video/*,image/*" multiple>
    <span class="drop-icon" id="dropIcon"></span>
    <div class="drop-label" id="dropLabel">Drop a video or photos, or click to browse</div>
    <div class="drop-hint" id="dropHint">Multiple photos → GIF frames · mp4 mov webm png jpg webp · max __MAX_UPLOAD_MB__ MB</div>
    <div class="file-info" id="fileInfo">
      <span class="file-name" id="fileName"></span>
      <span class="file-size" id="fileSize"></span>
    </div>
  </div>

  <!-- Options -->
  <div class="options">
    <div class="option-group">
      <label id="fpsLabel">FPS</label>
      <div class="slider-row">
        <input type="range" id="fps" min="1" max="30" step="1" value="15">
        <span class="slider-val" id="fpsVal">15</span>
      </div>
    </div>

    <div class="option-group">
      <label>Width</label>
      <select id="width">
        <option value="original">Original</option>
        <option value="1000">1000px</option>
        <option value="800">800px</option>
        <option value="640" selected>640px</option>
        <option value="480">480px</option>
        <option value="320">320px</option>
      </select>
    </div>

    <div class="option-group" id="canvasGroup" style="display:none">
      <label>Canvas</label>
      <select id="canvas">
        <option value="first" selected>First photo</option>
        <option value="bbox">Largest bounding box</option>
        <option value="1:1">Square (1:1)</option>
        <option value="16:9">Widescreen (16:9)</option>
        <option value="9:16">Vertical (9:16)</option>
      </select>
    </div>

    <div class="option-group">
      <label>Start (sec)</label>
      <input type="number" id="startTime" placeholder="0" min="0" step="0.1">
    </div>

    <div class="option-group">
      <label>End (sec)</label>
      <input type="number" id="endTime" placeholder="full" min="0" step="0.1">
    </div>

    <div class="option-group">
      <label>Encoder</label>
      <select id="encoder">
        <option value="ffmpeg-high">ffmpeg (2-pass palette)</option>
        <option value="gifski">Gifski (best quality)</option>
        <option value="libvips" selected>libvips</option>
        <option value="ffmpeg-med">ffmpeg</option>
      </select>
    </div>

    <div class="option-group">
      <label>Loop</label>
      <select id="loop">
        <option value="0" selected>Forever</option>
        <option value="1">Play once</option>
        <option value="2">Twice</option>
      </select>
    </div>

    <div class="option-group">
      <label>Speed</label>
      <select id="speed">
        <option value="1/4">4x faster</option>
        <option value="1/3">3x faster</option>
        <option value="1/2">2x faster</option>
        <option value="1" selected>Normal</option>
        <option value="2">2x slower</option>
        <option value="3">3x slower</option>
        <option value="4">4x slower</option>
      </select>
    </div>

    <div class="option-group">
      <label>Transparent</label>
      <select id="transparent">
        <option value="0" selected>Off</option>
        <option value="1">On</option>
      </select>
    </div>
  </div>

  <button class="convert-btn" id="convertBtn" disabled>Select a video or photos</button>

  <!-- Progress -->
  <div class="progress-section" id="progressSection">
    <div class="progress-label" id="progressLabel">Converting…</div>
    <div class="progress-bar-wrap">
      <div class="progress-bar indeterminate" id="progressBar"></div>
    </div>
  </div>

  <!-- Result -->
  <div class="result-section" id="resultSection">
    <img id="resultGif" src="" alt="Result GIF">
    <div class="result-meta" id="resultMeta"></div>
    <a class="download-btn" id="downloadBtn" href="#" download>Download GIF</a>
    <br>
    <button class="reset-btn" id="resetBtn">Make another</button>
  </div>
</div>

<script>
let selectedFile = null;
let selectedImages = null;  // Array of File when an image series is chosen
let jobId = null;
let pollTimer = null;

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const dropIcon = document.getElementById('dropIcon');
const dropLabel = document.getElementById('dropLabel');
const dropHint = document.getElementById('dropHint');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const convertBtn = document.getElementById('convertBtn');
const progressSection = document.getElementById('progressSection');
const progressLabel = document.getElementById('progressLabel');
const progressBar = document.getElementById('progressBar');
const resultSection = document.getElementById('resultSection');
const resultGif = document.getElementById('resultGif');
const resultMeta = document.getElementById('resultMeta');
const downloadBtn = document.getElementById('downloadBtn');
const resetBtn = document.getElementById('resetBtn');

const fps = document.getElementById('fps');
const fpsVal = document.getElementById('fpsVal');
const fpsLabel = document.getElementById('fpsLabel');

// The same slider drives FPS (video) and Seconds-per-photo (image series).
function renderRateVal() {
  fpsVal.textContent = selectedImages ? fps.value + 's' : fps.value;
}
function setRateControl(mode) {
  const canvasGroup = document.getElementById('canvasGroup');
  if (mode === 'images') {
    fpsLabel.textContent = 'Seconds per photo';
    fps.min = '0.25'; fps.max = '10'; fps.step = '0.25'; fps.value = '1';
    canvasGroup.style.display = '';  // photo-only control
  } else {
    fpsLabel.textContent = 'FPS';
    fps.min = '1'; fps.max = '30'; fps.step = '1'; fps.value = '15';
    canvasGroup.style.display = 'none';
  }
  renderRateVal();
}
fps.addEventListener('input', renderRateVal);
const MAX_UPLOAD_MB = __MAX_UPLOAD_MB__;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

// Drag & drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) handleFiles(fileInput.files);
});

// Route a FileList: a single video → video mode; one or more images → series.
function handleFiles(fileList) {
  const files = Array.from(fileList);  // preserve drop/selection order
  const allImages = files.every(f => f.type.startsWith('image/'));
  if (files.length > 1 || (allImages && files.length >= 1)) {
    if (!allImages) {
      clearSelection();
      showError('Mixed selection. Drop one video, or only images.');
      return;
    }
    setImages(files);
  } else {
    setFile(files[0]);
  }
}

function setImages(files) {
  const total = files.reduce((sum, f) => sum + f.size, 0);
  if (total > MAX_UPLOAD_BYTES) {
    clearSelection();
    showError(`Images too large. Max upload is ${MAX_UPLOAD_MB} MB total.`);
    return;
  }
  selectedFile = null;
  selectedImages = files;
  setRateControl('images');
  dropZone.classList.add('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = 'none';
  dropHint.style.display = 'none';
  fileInfo.classList.add('visible');
  fileName.textContent = `${files.length} images`;
  fileSize.textContent = formatBytes(total);
  convertBtn.disabled = false;
  convertBtn.textContent = 'Convert to GIF →';
  resultSection.classList.remove('visible');
}

function setFile(file) {
  if (file.size > MAX_UPLOAD_BYTES) {
    clearSelection();
    showError(`File too large. Max upload is ${MAX_UPLOAD_MB} MB.`);
    fileInput.value = '';
    return;
  }
  selectedImages = null;
  selectedFile = file;
  setRateControl('video');
  dropZone.classList.add('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = 'none';
  dropHint.style.display = 'none';
  fileInfo.classList.add('visible');
  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);
  convertBtn.disabled = false;
  convertBtn.textContent = 'Convert to GIF →';
  resultSection.classList.remove('visible');
}

function clearSelection() {
  selectedFile = null;
  selectedImages = null;
  setRateControl('video');
  fileInput.value = '';
  dropZone.classList.remove('has-file');
  dropIcon.textContent = '';
  dropLabel.style.display = '';
  dropHint.style.display = '';
  fileInfo.classList.remove('visible');
  fileName.textContent = '';
  fileSize.textContent = '';
  convertBtn.disabled = true;
  convertBtn.textContent = 'Select a video or photos';
}

function formatBytes(b) {
  if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
  return (b/(1024*1024)).toFixed(1) + ' MB';
}

// Convert
convertBtn.addEventListener('click', async () => {
  if (!selectedFile && !selectedImages) return;

  convertBtn.disabled = true;
  convertBtn.textContent = 'Converting…';
  progressSection.classList.add('visible');
  progressLabel.textContent = selectedImages ? 'Uploading images…' : 'Uploading video…';
  progressBar.classList.remove('indeterminate');
  progressBar.style.width = '0%';
  resultSection.classList.remove('visible');

  const formData = new FormData();
  if (selectedImages) {
    selectedImages.forEach(f => formData.append('images', f));  // order preserved
    formData.append('seconds_per_photo', fps.value);  // slider is seconds/photo here
    formData.append('canvas', document.getElementById('canvas').value);
  } else {
    formData.append('video', selectedFile);
    formData.append('fps', fps.value);
  }
  formData.append('width', document.getElementById('width').value);
  formData.append('start', document.getElementById('startTime').value || '');
  formData.append('end', document.getElementById('endTime').value || '');
  formData.append('encoder', document.getElementById('encoder').value);
  formData.append('loop', document.getElementById('loop').value);
  formData.append('speed', document.getElementById('speed').value);
  formData.append('transparent', document.getElementById('transparent').value);

  try {
    // Upload via XHR (not fetch) so we get real upload-progress events and a
    // hard timeout — a stalled upload becomes visible and retryable instead of
    // an infinite indeterminate spinner.
    const uploadRes = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/convert');
      xhr.timeout = 15 * 60 * 1000;  // 15 min ceiling for a large upload
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        const pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = pct + '%';
        progressLabel.textContent = pct < 100
          ? (selectedImages ? 'Uploading images… ' : 'Uploading video… ') + pct + '%'
          : 'Processing upload…';
      };
      xhr.onload = () => resolve({ status: xhr.status, body: xhr.responseText });
      xhr.onerror = () => reject(new Error('Upload failed — check your connection and try again.'));
      xhr.ontimeout = () => reject(new Error('Upload timed out. Try a smaller clip or check your connection.'));
      xhr.send(formData);
    });

    if (uploadRes.status !== 200) {
      const friendly = {
        413: `File too large. Max upload is ${MAX_UPLOAD_MB} MB.`,
        503: 'Server is busy with another conversion. Try again in a minute.',
        502: 'Server is unreachable right now. Try again shortly.',
        504: 'The server took too long to respond. Try again.',
      };
      let serverMsg;
      try { serverMsg = JSON.parse(uploadRes.body).error; } catch (_) {}
      throw new Error(serverMsg || friendly[uploadRes.status] || `Server error (${uploadRes.status}). Please try again.`);
    }
    const data = JSON.parse(uploadRes.body);
    if (data.error) throw new Error(data.error);
    jobId = data.job_id;
    progressBar.classList.add('indeterminate');
    progressLabel.textContent = 'Converting… (this may take a moment)';
    pollJob();
  } catch(e) {
    showError(e.message);
  }
});

function pollJob() {
  let pollFails = 0;
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/status/' + jobId);
      if (!res.ok) throw new Error('status ' + res.status);
      const data = await res.json();
      pollFails = 0;

      if (data.status === 'done') {
        clearInterval(pollTimer);
        showResult(data);
      } else if (data.status === 'error') {
        clearInterval(pollTimer);
        showError(data.error);
      } else if (data.status === 'unknown') {
        clearInterval(pollTimer);
        showError('Conversion status expired. Please try again.');
      } else {
        if (data.step) progressLabel.textContent = data.step;
      }
    } catch(e) {
      // Tolerate transient blips — the conversion keeps running server-side.
      if (++pollFails >= 5) {
        clearInterval(pollTimer);
        showError('Lost contact with the server while converting. Please try again.');
      }
    }
  }, 800);
}

function showResult(data) {
  progressSection.classList.remove('visible');
  resultSection.classList.add('visible');
  resultGif.src = data.url + '?t=' + Date.now();
  if (data.transparent) {
    resultGif.classList.add('checkerboard');
  } else {
    resultGif.classList.remove('checkerboard');
  }
  const encoderLabel = {'gifski':'Gifski','ffmpeg-high':'ffmpeg (2-pass)','libvips':'libvips','ffmpeg-med':'ffmpeg'}[data.encoder] || data.encoder;
  const sf = data.speed_factor;
  const speedLabel = !sf || sf === 1 ? '' : sf > 1 ? ` · ${sf}x slower` : ` · ${Math.round(1 / sf)}x faster`;
  resultMeta.textContent = `${data.width}×${data.height} · ${data.size} · ${data.frames} frames · ${data.fps} fps${speedLabel} · ${encoderLabel}`;
  downloadBtn.href = data.url;
  downloadBtn.download = data.filename;
  convertBtn.disabled = false;
  convertBtn.textContent = 'Convert Again';
}

function showError(msg, canRetry = Boolean(selectedFile || selectedImages)) {
  progressSection.classList.remove('visible');
  // Clear any existing error before inserting a new one
  document.querySelectorAll('.error-msg').forEach(el => el.remove());
  const err = document.createElement('div');
  err.className = 'error-msg';
  err.textContent = msg;
  convertBtn.parentNode.insertBefore(err, convertBtn.nextSibling);
  convertBtn.disabled = !canRetry;
  convertBtn.textContent = canRetry ? 'Try Again' : 'Select a video or photos';
  setTimeout(() => err.remove(), 8000);
}

resetBtn.addEventListener('click', () => {
  clearSelection();
  resultSection.classList.remove('visible');
  resultGif.classList.remove('checkerboard');
  progressSection.classList.remove('visible');
});
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    # Drop stalled connections instead of parking a handler thread (and up to
    # MAX_UPLOAD_BYTES of buffered body) forever on a half-open socket. This is a
    # per-recv inactivity timeout, so a slow-but-progressing upload is unaffected.
    timeout = 120

    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/index.html":
            html = HTML.replace("__MAX_UPLOAD_MB__", str(MAX_UPLOAD_MB))
            self._send(200, "text/html", html.encode())

        elif path == "/healthz":
            # Report liveness plus whether the single conversion slot is occupied,
            # so an external watchdog can catch an alive-but-wedged process that
            # KeepAlive (which only restarts dead processes) would miss.
            free = conversion_slots.acquire(blocking=False)
            if free:
                conversion_slots.release()
            with jobs_lock:
                njobs = len(jobs)
            self._json(200, {"ok": True, "busy": not free, "jobs": njobs})

        elif path == "/favicon.svg":
            svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#0a0a0a"/><text x="16" y="26" font-family="\'Inter\', system-ui, -apple-system, sans-serif" font-size="30" font-weight="900" fill="#c8ff00" text-anchor="middle">G</text></svg>'
            self._send(200, "image/svg+xml", svg.encode())

        elif path.startswith("/status/"):
            job_id = path.split("/")[-1]
            with jobs_lock:
                job = jobs.get(job_id, {"status": "unknown"})
            self._json(200, job)

        elif path.startswith("/output/"):
            fname = path.split("/")[-1]
            fpath = OUTPUT_DIR / fname
            if fpath.exists() and fpath.suffix == ".gif":
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/gif")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, "text/plain", b"Not found")
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/convert":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "Invalid Content-Length."})
                return
            if content_length > MAX_UPLOAD_BYTES:
                self._json(413, {"error": f"File too large. Max upload is {MAX_UPLOAD_MB} MB."})
                return
            if content_length <= 0:
                self._json(400, {"error": "Empty upload."})
                return
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(content_length)

            # Parse multipart
            try:
                params = parse_multipart(body, content_type)
                params = validate_params(params)
            except Exception as e:
                self._json(400, {"error": str(e)})
                return

            if not conversion_slots.acquire(blocking=False):
                self._json(503, {"error": "Another conversion is running. Please try again shortly."})
                return

            # Own the slot until the worker thread takes over. Any early exit here
            # (busy-evict 503, response-write failure, client abort) must release it,
            # or a dropped connection permanently wedges the single conversion slot.
            slot_owned = True
            try:
                job_id = str(uuid.uuid4())[:8]
                with jobs_lock:
                    if len(jobs) >= MAX_JOBS:
                        evictable = [k for k, v in list(jobs.items())
                                     if isinstance(v, dict) and v.get("status") in ("done", "error")]
                        for k in evictable[:50]:
                            gif = OUTPUT_DIR / f"{k}.gif"
                            gif.unlink(missing_ok=True)
                            jobs.pop(k, None)
                    if len(jobs) >= MAX_JOBS:
                        self._json(503, {"error": "Server is busy. Please try again shortly."})
                        return  # finally releases the slot
                    jobs[job_id] = {"status": "queued", "step": "Queued…"}

                # Start the worker, which now owns the release via its finally block,
                # then acknowledge. A broken pipe on the ack no longer leaks the slot.
                t = threading.Thread(target=run_conversion, args=(job_id, params, True), daemon=True)
                t.start()
                slot_owned = False
                try:
                    self._json(200, {"job_id": job_id})
                except OSError:
                    pass  # client hung up after the job started; conversion continues
            finally:
                if slot_owned:
                    conversion_slots.release()

        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self._send(code, "application/json", body)


def parse_multipart(body: bytes, content_type: str) -> dict:
    """Simple multipart/form-data parser."""
    import email
    from email import policy

    # Extract boundary
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[9:].strip('"')
            break

    if not boundary:
        raise ValueError("No boundary found")

    result = {}
    delim = ("--" + boundary).encode()
    parts = body.split(delim)

    for part in parts[1:]:
        if part.strip() in (b"", b"--", b"--\r\n"):
            continue
        part = part.lstrip(b"\r\n")
        if b"\r\n\r\n" not in part:
            continue
        headers_raw, content = part.split(b"\r\n\r\n", 1)
        # Strip exactly the trailing CRLF that precedes the next boundary marker
        if content.endswith(b"\r\n"):
            content = content[:-2]

        headers_str = headers_raw.decode("utf-8", errors="replace")
        name = None
        filename = None
        part_content_type = ""
        for line in headers_str.splitlines():
            if "Content-Disposition" in line:
                # Extract quoted values directly. Splitting on ";" corrupts any
                # filename that itself contains a semicolon (e.g.
                # "add_grain;_preserve.png" -> "add_grain"), dropping its
                # extension and failing later type validation.
                name_match = re.search(r'(?:^|;\s*)name="((?:[^"\\]|\\.)*)"', line)
                if name_match:
                    name = name_match.group(1)
                fn_match = re.search(r'(?:^|;\s*)filename="((?:[^"\\]|\\.)*)"', line)
                if fn_match:
                    filename = fn_match.group(1)
            elif line.lower().startswith("content-type:"):
                part_content_type = line.split(":", 1)[1].strip().lower()

        if name:
            if filename:
                entry = {
                    "filename": filename,
                    "content_type": part_content_type,
                    "data": content,
                }
                # Multiple files under the same field name (e.g. image series)
                # accumulate into a list, preserving multipart part order.
                if name in result:
                    existing = result[name]
                    if not isinstance(existing, list):
                        existing = [existing]
                    existing.append(entry)
                    result[name] = existing
                else:
                    result[name] = entry
            else:
                result[name] = content.decode("utf-8", errors="replace").strip()

    return result


def _parse_int(value, default, minimum=None, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _parse_float(value, default, minimum=None, maximum=None):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _parse_speed_factor(value) -> float:
    key = str(value).strip() if value is not None else ""
    if not key:
        return 1.0
    if key in SPEED_OPTIONS:
        return SPEED_OPTIONS[key]
    # Numeric spellings of a preset ("2.0", "0.5") are accepted too.
    parsed = _parse_float(key, default=None)
    if parsed is not None:
        for factor in SPEED_OPTIONS.values():
            if abs(parsed - factor) < 1e-6:
                return factor
    raise ValueError("Unsupported speed option")


def _parse_time(value, label):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"{label} time must be a number of seconds")
    if parsed < 0:
        raise ValueError(f"{label} time must be 0 or greater")
    return str(parsed)


def validate_params(params: dict) -> dict:
    video_data = params.get("video")
    images = params.get("images")
    if images is not None and not isinstance(images, list):
        images = [images]  # parser yields a dict for a single file

    has_video = isinstance(video_data, dict)
    has_images = bool(images)
    if has_video == has_images:
        raise ValueError("Upload either one video or a series of images")

    # Options common to both modes
    width_opt = (params.get("width", "640") or "640").strip()
    if width_opt not in ALLOWED_WIDTHS:
        raise ValueError("Unsupported width option")

    loop = _parse_int(params.get("loop", "0"), default=0)
    if loop not in ALLOWED_LOOPS:
        raise ValueError("Unsupported loop option")

    transparent = params.get("transparent", "0") == "1"
    speed_factor = _parse_speed_factor(params.get("speed", "1"))

    if has_images:
        if len(images) > MAX_OUTPUT_FRAMES:
            raise ValueError(f"Too many images. Max is {MAX_OUTPUT_FRAMES} frames.")
        total_bytes = 0
        for img in images:
            if not isinstance(img, dict):
                raise ValueError("Invalid image upload")
            ext = Path(img.get("filename") or "").suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
                raise ValueError(f"Unsupported image type. Use one of: {allowed}")
            ctype = (img.get("content_type") or "").lower()
            if not ctype.startswith("image/"):
                raise ValueError("Unsupported image content type")
            total_bytes += len(img.get("data", b""))
        if total_bytes > MAX_UPLOAD_BYTES:
            raise ValueError(f"Images too large. Max upload is {MAX_UPLOAD_MB} MB.")
        # Photos: user picks seconds-per-photo; fps is its inverse (gifski accepts
        # fractional fps, so e.g. 2s/photo -> 0.5 fps holds each frame for 2s).
        seconds_per_photo = _parse_float(
            params.get("seconds_per_photo", "1"), default=1.0, minimum=0.25, maximum=10.0
        )
        fps = round(1.0 / (seconds_per_photo * speed_factor), 4)
        canvas = (params.get("canvas", "first") or "first").strip()
        if canvas not in ALLOWED_CANVAS:
            raise ValueError("Unsupported canvas option")
        # Image series are assembled with gifski (purpose-built for frame lists).
        return {
            "mode": "images",
            "images": images,
            "fps": fps,
            "width": width_opt,
            "canvas": canvas,
            "encoder": "gifski",
            "loop": loop,
            "speed_factor": speed_factor,
            "transparent": transparent,
        }

    # Video mode
    filename = video_data.get("filename") or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported video type. Use one of: {allowed}")

    content_type = (video_data.get("content_type") or "application/octet-stream").lower()
    if not content_type.startswith(ALLOWED_MIME_PREFIXES):
        raise ValueError("Unsupported upload content type")

    if len(video_data.get("data", b"")) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large. Max upload is {MAX_UPLOAD_MB} MB.")

    encoder = (params.get("encoder", "libvips") or "libvips").strip()
    if encoder not in ALLOWED_ENCODERS:
        raise ValueError("Unsupported encoder option")

    fps = _parse_int(params.get("fps", "15"), default=15, minimum=1, maximum=30)

    start = _parse_time(params.get("start", ""), "Start")
    end = _parse_time(params.get("end", ""), "End")
    if start and end and float(end) <= float(start):
        raise ValueError("End time must be greater than start time")

    return {
        "mode": "video",
        "video": video_data,
        "fps": fps,
        "width": width_opt,
        "start": start,
        "end": end,
        "encoder": encoder,
        "loop": loop,
        "speed_factor": speed_factor,
        "transparent": transparent,
    }


def loop_values(ui_loop: int) -> tuple[int, int]:
    """Return loop values for ffmpeg/libvips and gifski."""
    # UI: 0 = forever, 1 = play once, 2 = play twice.
    # ffmpeg/libvips store extra loops after the first play; gifski uses
    # -1 for no repeat and positive values for additional repeats.
    ffmpeg_loop = {0: 0, 1: -1, 2: 1}.get(ui_loop, 0)
    gifski_repeat = {0: 0, 1: -1, 2: 1}.get(ui_loop, 0)
    return ffmpeg_loop, gifski_repeat


def probe_duration(input_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError("Invalid or unsupported video file")
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        raise ValueError("Could not read video duration")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Could not read video duration")
    return duration


def _probe_image_size(path: str, label: str) -> tuple[int, int]:
    """Return (width, height) of an image via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        raise RuntimeError(f"Could not read dimensions of image '{label}'")


def _canvas_dims(canvas: str, sizes: list) -> tuple[int, int]:
    """Common (width, height) for a photo series, from the chosen canvas mode.
    `sizes` is a list of (w, h) in upload order (sizes[0] = first photo)."""
    max_w = max(w for w, _ in sizes)
    max_h = max(h for _, h in sizes)
    if canvas == "bbox":
        return max_w, max_h
    if canvas in ("1:1", "16:9", "9:16"):
        longest = max(max_w, max_h)
        if canvas == "1:1":
            return longest, longest
        short = max(1, round(longest * 9 / 16))
        return (longest, short) if canvas == "16:9" else (short, longest)
    return sizes[0]  # "first" (default)


def enforce_clip_limits(source_duration: float, start: str, end: str, fps: float):
    start_s = float(start) if start else 0.0
    end_s = float(end) if end else source_duration
    if start_s >= source_duration:
        raise ValueError("Start time is beyond the end of the video")
    clip_duration = min(end_s, source_duration) - start_s
    if clip_duration <= 0:
        raise ValueError("Selected clip has no duration")
    if clip_duration > MAX_DURATION_SECONDS:
        raise ValueError(f"Clip is too long. Max duration is {MAX_DURATION_SECONDS:g} seconds.")
    estimated_frames = math.ceil((clip_duration * fps) - 1e-9)
    if estimated_frames > MAX_OUTPUT_FRAMES:
        raise ValueError(f"Clip has too many frames. Max output is {MAX_OUTPUT_FRAMES} frames.")
    return clip_duration, estimated_frames


def _video_filter(fps, width_opt, speed_factor=1.0):
    """Build the ffmpeg video filter chain for sampled GIF frames.

    ``fps`` is the source sampling rate (see ``_sample_fps``). With a
    ``speed_factor`` the timeline is stretched first and then resampled at the
    playback rate (sample rate / factor), so the stream's declared frame rate
    matches its timestamps. Sampling first and compressing afterwards leaves
    the two disagreeing, and ffmpeg drops frames to reconcile them (2x faster
    came out with 24 frames instead of 45 on the direct ffmpeg encoders).
    """
    if width_opt == "original":
        scale = "scale=iw:ih"
    else:
        scale = f"scale={width_opt}:-2:flags=lanczos"
    if speed_factor != 1.0:
        filters = [f"setpts={speed_factor}*PTS", f"fps={_clean_fps(fps / speed_factor)}"]
    else:
        filters = [f"fps={fps}"]
    filters.append(scale)
    return ",".join(filters)


def _clean_fps(value):
    """Round to 4 decimals and drop a trailing .0 so ffmpeg reads fps=15, not 15.0."""
    value = round(value, 4)
    return int(value) if float(value).is_integer() else value


def _playback_fps(fps, speed_factor):
    """GIF playback rate. Slowing down holds each frame longer, so the rate
    drops; speeding up keeps the chosen fps and samples fewer frames instead."""
    return round(fps / max(1.0, speed_factor), 4)


def _sample_fps(fps, speed_factor):
    """Rate at which source frames are pulled. Slowdown samples at the chosen
    fps; speed-up decimates (15 fps at 2x faster reads 7.5 source frames per
    second and plays them back at 15)."""
    return _clean_fps(fps * min(1.0, speed_factor))


def _frame_delay_ms(fps, speed_factor):
    return max(10, round(1000 / _playback_fps(fps, speed_factor)))


def _finalize_output(job_id, output_path, output_name, fps, encoder, transparent, speed_factor=1.0):
    """Probe the finished GIF and publish the done status (shared by all modes)."""
    gif_bytes = os.path.getsize(output_path)
    size_str = f"{gif_bytes/1024:.0f} KB" if gif_bytes < 1024*1024 else f"{gif_bytes/1024/1024:.1f} MB"

    w, h, frames_count = "?", "?", "?"
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-count_packets",
             "-show_entries", "stream=width,height,nb_read_packets",
             "-of", "csv=p=0", output_path],
            capture_output=True, text=True, timeout=30
        )
        parts_out = probe.stdout.strip().split(",")
        if len(parts_out) >= 2:
            w, h = parts_out[0], parts_out[1]
        if len(parts_out) >= 3 and parts_out[2].strip():
            frames_count = parts_out[2].strip()
    except Exception:
        pass  # GIF already encoded; a hung/failed probe shouldn't fail the job

    with jobs_lock:
        if job_id not in jobs:  # job evicted/expired mid-run — discard output
            if os.path.exists(output_path):
                os.unlink(output_path)
            return
        jobs[job_id] = {
            "status": "done",
            "url": f"/output/{output_name}",
            "filename": output_name,
            "size": size_str,
            "width": w,
            "height": h,
            "frames": frames_count,
            "fps": fps,
            "encoder": encoder,
            "speed_factor": speed_factor,
            "transparent": transparent,
        }


def run_conversion(job_id: str, params: dict, release_slot: bool = False):
    import tempfile
    import shutil

    def update(step, **extra):
        with jobs_lock:
            jobs[job_id] = {"status": "running", "step": step, **extra}

    input_path = None
    palette_path = None
    frames_dir = None
    trimmed_path = None
    try:
        # ── Image series → GIF ────────────────────────────────────────────────
        if params.get("mode") == "images":
            fps = params["fps"]
            width_opt = params["width"]
            transparent = params["transparent"]
            _, gifski_repeat = loop_values(params["loop"])
            output_name = f"{job_id}.gif"
            output_path = str(OUTPUT_DIR / output_name)

            update("Preparing images…")
            frames_dir = tempfile.mkdtemp()  # cleaned by finally (rmtree)

            # Pass 1: write each source and probe its size — needed to size the
            # canvas before encoding (gifski rejects mismatched frame sizes).
            srcs = []  # (src_path, filename)
            sizes = []
            for i, img in enumerate(params["images"]):
                src_suffix = Path(img["filename"]).suffix.lower() or ".png"
                src_path = os.path.join(frames_dir, f"src{i:05d}{src_suffix}")
                with open(src_path, "wb") as sf:
                    sf.write(img["data"])
                sizes.append(_probe_image_size(src_path, img["filename"]))
                srcs.append((src_path, img["filename"]))

            tw, th = _canvas_dims(params["canvas"], sizes)
            # Crop-to-fill: scale to cover the canvas, then center-crop overflow,
            # so every frame is exactly tw×th. format=rgba keeps source alpha.
            fmt = "format=rgba," if transparent else ""
            vf = (f"{fmt}scale={tw}:{th}:force_original_aspect_ratio=increase:"
                  f"flags=lanczos,crop={tw}:{th}")

            # Pass 2: transcode each source to a uniform PNG frame (gifski's
            # multi-image input is PNG-only; sequential names preserve order).
            frame_paths = []
            for i, (src_path, fname) in enumerate(srcs):
                frame_path = os.path.join(frames_dir, f"frame{i:05d}.png")
                r = subprocess.run(
                    ["ffmpeg", "-y", "-i", src_path, "-vf", vf, "-frames:v", "1", frame_path],
                    capture_output=True, text=True, timeout=60
                )
                os.unlink(src_path)
                if r.returncode != 0:
                    raise RuntimeError(
                        f"Could not read image '{fname}':\n{r.stderr[-400:]}"
                    )
                frame_paths.append(frame_path)

            update("Encoding with Gifski…")
            gifski_cmd = [
                "gifski",
                "--no-sort",  # preserve given (drop) order, don't re-sort
                "--fps", str(fps),
                "--quality", "90",
                "--repeat", str(gifski_repeat),
                "-o", output_path,
            ]
            if width_opt != "original":
                gifski_cmd += ["-W", width_opt]
            gifski_cmd += frame_paths
            result = subprocess.run(gifski_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"Gifski failed:\n{result.stderr[-800:]}")

            _finalize_output(job_id, output_path, output_name, fps, "gifski",
                             params["transparent"], params["speed_factor"])
            return

        update("Saving uploaded video…")

        video_data = params.get("video")
        if not video_data or not isinstance(video_data, dict):
            raise ValueError("No video file received")

        suffix = Path(video_data["filename"]).suffix.lower() or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(video_data["data"])
            input_path = f.name

        # Options
        fps = params["fps"]
        width_opt = params["width"]
        start = params["start"]
        end = params["end"]
        encoder = params["encoder"]
        loop = params["loop"]
        transparent = params["transparent"]
        speed_factor = params["speed_factor"]
        playback_fps = _playback_fps(fps, speed_factor)
        sample_fps = _sample_fps(fps, speed_factor)
        ffmpeg_loop, gifski_repeat = loop_values(loop)
        source_duration = probe_duration(input_path)
        clip_duration, estimated_frames = enforce_clip_limits(source_duration, start, end, sample_fps)

        # ffmpeg single-pass cannot produce transparent GIFs; auto-upgrade
        if transparent and encoder == "ffmpeg-med":
            encoder = "ffmpeg-high"

        output_name = f"{job_id}.gif"
        output_path = str(OUTPUT_DIR / output_name)

        vf_sample = _video_filter(sample_fps, width_opt)
        vf_playback = _video_filter(sample_fps, width_opt, speed_factor)

        # ffmpeg time-range args
        time_args = []
        if start:
            time_args += ["-ss", start]
        if end:
            if start:
                time_args += ["-t", str(clip_duration)]
            else:
                time_args += ["-to", end]
        elif start:
            time_args += ["-t", str(clip_duration)]

        # ── Gifski ────────────────────────────────────────────────────────────
        if encoder == "gifski":
            import glob as globmod
            frames_dir = tempfile.mkdtemp()
            update("Extracting frames…")
            frame_pattern = os.path.join(frames_dir, "frame%05d.png")
            extract_cmd = [
                "ffmpeg", "-y", *time_args,
                "-i", input_path,
                "-vf", vf_sample,
                frame_pattern,
            ]
            r = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(f"Frame extraction failed:\n{r.stderr[-800:]}")
            frames = sorted(globmod.glob(os.path.join(frames_dir, "frame*.png")))
            if not frames:
                raise RuntimeError("No frames extracted from video")

            update("Encoding with Gifski…")
            gifski_cmd = [
                "gifski",
                "--no-sort",
                "--fps", str(playback_fps),
                "--quality", "90",
                "--repeat", str(gifski_repeat),
                "-o", output_path,
            ]
            gifski_cmd += frames
            result = subprocess.run(gifski_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"Gifski failed:\n{result.stderr[-800:]}")

        # ── libvips ───────────────────────────────────────────────────────────
        elif encoder == "libvips":
            import glob as globmod
            frames_dir = tempfile.mkdtemp()
            update("Extracting frames…")
            frame_pattern = os.path.join(frames_dir, "frame%05d.png")
            pix_fmt_args = ["-pix_fmt", "rgba"] if transparent else []
            extract_cmd = [
                "ffmpeg", "-y", *time_args,
                "-i", input_path,
                "-vf", vf_sample,
                *pix_fmt_args,
                frame_pattern
            ]
            r = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(f"Frame extraction failed:\n{r.stderr[-800:]}")

            frames = sorted(globmod.glob(os.path.join(frames_dir, "frame*.png")))
            if not frames:
                raise RuntimeError("No frames extracted from video")

            update(f"Encoding {len(frames)} frames with libvips…")

            # Use pyvips to set page-height + delay metadata correctly.
            # The vips CLI arrayjoin → gifsave path fails when total stacked
            # height (frame_h × N) exceeds the GIF canvas limit of 65535px.
            # pyvips lets us set these fields explicitly before saving.
            import pyvips
            images = [pyvips.Image.new_from_file(f, access="sequential") for f in frames]
            joined = pyvips.Image.arrayjoin(images, across=1)
            delay_ms = _frame_delay_ms(fps, speed_factor)
            joined.set_type(pyvips.GValue.array_int_type, "delay", [delay_ms] * len(images))
            joined.set_type(pyvips.GValue.gint_type, "page-height", images[0].height)
            joined.set_type(pyvips.GValue.gint_type, "loop", ffmpeg_loop)
            joined.gifsave(output_path, effort=7, dither=1.0)

        # ── ffmpeg high (2-pass palette) ──────────────────────────────────────
        elif encoder == "ffmpeg-high":
            update("Generating color palette…")
            palette_path = str(OUTPUT_DIR / f"{job_id}_palette.png")
            reserve = "1" if transparent else "0"
            r = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path,
                 "-vf", f"{vf_sample},palettegen=stats_mode=diff:reserve_transparent={reserve}", palette_path],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode != 0:
                raise RuntimeError(f"Palette generation failed:\n{r.stderr[-800:]}")

            update("Rendering GIF…")
            alpha_opt = ":alpha_threshold=128" if transparent else ""
            result = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path, "-i", palette_path,
                 "-lavfi", f"{vf_playback} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle{alpha_opt}",
                 "-loop", str(ffmpeg_loop), output_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                raise RuntimeError(f"GIF conversion failed:\n{result.stderr[-800:]}")

        # ── ffmpeg standard ───────────────────────────────────────────────────
        else:
            update("Rendering GIF…")
            result = subprocess.run(
                ["ffmpeg", "-y", *time_args, "-i", input_path,
                 "-vf", vf_playback, "-loop", str(ffmpeg_loop), output_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                raise RuntimeError(f"GIF conversion failed:\n{result.stderr[-800:]}")

        # ── Gather output info ────────────────────────────────────────────────
        _finalize_output(job_id, output_path, output_name, playback_fps, encoder, transparent, speed_factor)

    except Exception as e:
        with jobs_lock:
            jobs[job_id] = {"status": "error", "error": str(e)}
    finally:
        if input_path and os.path.exists(input_path):
            try: os.unlink(input_path)
            except OSError: pass
        if palette_path and os.path.exists(palette_path):
            try: os.unlink(palette_path)
            except OSError: pass
        if frames_dir and os.path.exists(frames_dir):
            try: shutil.rmtree(frames_dir)
            except OSError: pass
        if trimmed_path and os.path.exists(trimmed_path):
            try: os.unlink(trimmed_path)
            except OSError: pass
        if release_slot:
            conversion_slots.release()


class GifMakerServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Thread-per-request server so status polling doesn't block uploads."""
    allow_reuse_address = True
    daemon_threads = True


def _cleanup_loop():
    """Background thread: delete GIFs and job entries older than 1 hour, atomically."""
    while True:
        time.sleep(1800)  # run every 30 minutes
        cutoff = time.time() - 3600
        # Identify expired files outside the lock (disk I/O should not block job state)
        expired = []
        for fpath in list(OUTPUT_DIR.iterdir()):
            if fpath.suffix == ".gif":
                try:
                    if fpath.stat().st_mtime < cutoff:
                        expired.append(fpath)
                except OSError:
                    pass
        # Delete files outside the lock, collect job IDs to evict
        evict_ids = []
        for fpath in expired:
            try:
                fpath.unlink()
                evict_ids.append(fpath.stem)
            except OSError:
                pass
        # Single lock acquisition to batch-evict all job entries
        if evict_ids:
            with jobs_lock:
                for job_id in evict_ids:
                    jobs.pop(job_id, None)


def main():
    threading.Thread(target=_cleanup_loop, daemon=True).start()

    print(f"\n  GIF Maker running at http://{HOST}:{PORT}")
    is_local = sys.stdout.isatty()
    if is_local:
        import webbrowser
        print(f"  Press Ctrl+C to stop\n")
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    try:
        with GifMakerServer((HOST, PORT), Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n  Stopped.")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n  Port {PORT} is already in use.")
            print(f"  Try: lsof -ti :{PORT} | xargs kill\n")
        else:
            raise


if __name__ == "__main__":
    main()
