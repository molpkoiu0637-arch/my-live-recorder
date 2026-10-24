
import os, re, requests, subprocess, threading, uuid
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
RECORD_DIR = "/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs = {}

def get_html():
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "<h1>BIGO V22 SINGAPORE OK</h1>"

HEADERS = {"User-Agent":"Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36","Referer":"https://www.bigo.tv/"}

def resolve_any_url(url):
    log=""
    url=url.strip()
    if re.match(r"^\d+$", url):
        url=f"https://www.bigo.tv/th/{url}"
        log+=f"ID -> {url}\n"
    if not url.startswith("http"):
        if re.match(r"^[A-Za-z0-9_\.]+$", url):
            url=f"https://www.bigo.tv/{url}"
            log+=f"username -> {url}\n"
    if "slink" in url or "onelink" in url:
        try:
            s=requests.Session()
            r=s.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            log+=f"slink {r.status_code} -> {r.url}\n"
            if "bigo.tv" in r.url and "slink" not in r.url and "onelink" not in r.url:
                return r.url, log
            m=re.search(r"https://www\.bigo\.tv/sid/[^\"\'\s<>\\]+", r.text)
            if m:
                return m.group(0).replace("\\u002F","/").split('"')[0], log+"found sid\n"
            return r.url, log
        except Exception as e:
            return url, log+f"err {e}\n"
    if "bigo.tv" in url and "/sid/" not in url:
        try:
            r=requests.get(url, headers=HEADERS, timeout=12)
            log+=f"GET user page {r.status_code}\n"
            m=re.search(r"https://www\.bigo\.tv/sid/[^\"\'\s<>\\]+", r.text.replace("\\u002F","/"))
            if m:
                sid=m.group(0).replace("\\u002F","/").split('"')[0]
                return sid, log+f"user->sid {sid[:100]}\n"
        except Exception as e:
            log+=f"user err {e}\n"
    return url, log

def get_hls(sid_url):
    log=""
    try:
        r=requests.get(sid_url, headers=HEADERS, timeout=15)
        log+=f"GET sid {r.status_code} len {len(r.text)}\n"
        txt=r.text.replace("\\u002F","/")
        m3us=re.findall(r"https?://[^\"\'\s<>]+\.m3u8[^\"\'\s<>]*", txt)
        m3us=list(dict.fromkeys(m3us))
        log+=f"found {len(m3us)} m3u8\n"
        if m3us:
            return m3us[0].split('"')[0], log
        mm=re.search(r"/sid/(\d+)", sid_url)
        if mm:
            site_id=mm.group(1)
            api=f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}"
            rr=requests.get(api, headers=HEADERS, timeout=10)
            log+=f"API {rr.status_code}\n"
            if ".m3u8" in rr.text:
                m=re.search(r"https?://[^\"\'\s<>]+\.m3u8[^\"\'\s<>]*", rr.text)
                if m:
                    return m.group(0), log+"FOUND API\n"
    except Exception as e:
        log+=f"err {e}\n"
    return None, log

@app.route("/")
def home():
    return get_html()

@app.route("/api/start", methods=["POST"])
def api_start():
    data=request.json
    raw=data.get("url","")
    mm=re.search(r"https?://[^\s]+", raw)
    raw_url=mm.group(0).strip(')"\'\'') if mm else raw.strip()
    resolved, slog = resolve_any_url(raw_url)
    mm2=re.search(r"/sid/(\d+)", resolved)
    site_id=mm2.group(1) if mm2 else "unknown"
    if site_id=="unknown":
        mm3=re.search(r"/th/(\d+)", resolved)
        if mm3: site_id=mm3.group(1)
    out=os.path.join(RECORD_DIR, f"{uuid.uuid4().hex[:8]}.mp4")
    job_id=uuid.uuid4().hex[:8]
    jobs[job_id]={"id":job_id,"resolved":resolved,"siteid":site_id,"status":"starting","log":slog,"time":datetime.now().strftime("%H:%M:%S"),"file":out}
    def run():
        try:
            jobs[job_id]["status"]="recording"
            log=slog+f"\nResolved: {resolved}\nSiteID: {site_id}\n"
            hls, plog = get_hls(resolved)
            log+=plog
            if hls:
                log+=f"\nFOUND HLS SINGAPORE {hls[:100]}\n"
                jobs[job_id]["log"]=log
                cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy","-t","10800",out]
                proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-10000:]
                proc.wait()
                jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
            else:
                log+="\nไม่เจอ HLS - อาจไม่ได้ไลฟ์อยู่\n"
                jobs[job_id]["log"]=log
                cmd=["yt-dlp","-f","best","-o",out, resolved]
                proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-10000:]
                proc.wait()
                jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id})

@app.route("/api/list")
def api_list():
    return jsonify(list(jobs.values())[::-1])

if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000)
